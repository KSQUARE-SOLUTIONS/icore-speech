import {
  byId, bindTokenInput, setStatus, startBusyStatus, errorMessage, formatClock, MicrophoneRecorder,
} from "/static/common.js";

const VOICE_STORAGE_KEY = "icore-speech-voice";
const authHeaders = bindTokenInput(byId("api-token"));

// ---------------------------------------------------------------- tabs
const tabs = ["listen", "speak", "voices"];
function showTab(name) {
  for (const tab of tabs) {
    byId(`tab-${tab}`).setAttribute("aria-selected", String(tab === name));
    byId(`panel-${tab}`).hidden = tab !== name;
  }
}
tabs.forEach((tab) => byId(`tab-${tab}`).addEventListener("click", () => showTab(tab)));
byId("go-to-voices").addEventListener("click", () => showTab("voices"));

// ---------------------------------------------------------------- server health
async function checkHealth() {
  const chip = byId("health");
  try {
    const health = await (await fetch("/health")).json();
    chip.dataset.state = "ok";
    byId("health-text").textContent = `${health.stt.model} · ${health.tts.engine}`;
  } catch {
    chip.dataset.state = "down";
    byId("health-text").textContent = "السيرفر مش شغال";
  }
}
checkHealth();

// ---------------------------------------------------------------- shared helpers
// Wires a big record button + clock to a MicrophoneRecorder; onRecorded gets { blob, filename, seconds }.
function bindRecordButton(button, clock, statusElement, onRecorded, maxSeconds = 600) {
  let clockTimer = 0;
  const recorder = new MicrophoneRecorder(
    (recording) => {
      clearInterval(clockTimer);
      button.classList.remove("recording");
      clock.classList.remove("live");
      button.setAttribute("aria-label", "ابدأ التسجيل");
      onRecorded(recording);
    },
    (level) => button.style.setProperty("--level", level.toFixed(2)),
  );
  button.addEventListener("click", async () => {
    if (recorder.isRecording) return recorder.stop();
    try {
      await recorder.start();
    } catch (error) {
      return setStatus(statusElement, `مقدرش أفتح المايك: ${error.message}. افتح الصفحة في Chrome أو Safari.`, true);
    }
    button.classList.add("recording");
    clock.classList.add("live");
    button.setAttribute("aria-label", "وقّف التسجيل");
    setStatus(statusElement, "بيسجّل… دوس تاني لما تخلص.");
    clockTimer = setInterval(() => {
      clock.textContent = formatClock(recorder.elapsedSeconds);
      if (recorder.elapsedSeconds >= maxSeconds) recorder.stop();
    }, 200);
  });
}

function bindDropZone(zone, input, onFile) {
  input.addEventListener("change", () => input.files[0] && onFile(input.files[0]));
  zone.addEventListener("dragover", (event) => { event.preventDefault(); zone.classList.add("dragging"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragging"));
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("dragging");
    const file = event.dataTransfer.files[0];
    if (file) onFile(file);
  });
}

// ---------------------------------------------------------------- speech to text
const transcribeStatus = byId("transcribe-status");
const transcribeResult = byId("transcribe-result");
const copyButton = byId("copy-transcript");

async function transcribe(blob, filename) {
  const form = new FormData();
  form.append("file", blob, filename);
  form.append("language", byId("transcribe-language").value);
  form.append("timestamps", byId("transcribe-timestamps").checked);
  if (byId("transcribe-domain").value) form.append("domain", byId("transcribe-domain").value);
  showTab("listen");
  transcribeResult.textContent = "";
  byId("transcribe-meta").replaceChildren();
  copyButton.hidden = true;
  const stop = startBusyStatus(transcribeStatus, "بيفرّغ…");
  try {
    const response = await fetch("/v1/transcribe", { method: "POST", headers: authHeaders(), body: form });
    if (!response.ok) throw new Error(await errorMessage(response));
    const data = await response.json();
    stop();
    renderTranscript(data);
    setStatus(transcribeStatus, "");
  } catch (error) {
    stop();
    setStatus(transcribeStatus, error.message, true);
  }
}

function renderTranscript(data) {
  if (data.segments?.length) {
    const list = document.createElement("ol");
    list.className = "segments";
    for (const segment of data.segments) {
      const item = document.createElement("li");
      const time = document.createElement("time");
      time.textContent = formatClock(segment.start);
      item.append(time, document.createTextNode(segment.text));
      list.append(item);
    }
    transcribeResult.replaceChildren(list);
  } else {
    transcribeResult.textContent = data.text || "(مفيش كلام اتعرف عليه)";
  }
  copyButton.hidden = !data.text;
  copyButton.onclick = async () => {
    await navigator.clipboard.writeText(data.text);
    copyButton.textContent = "اتنسخ ✓";
    setTimeout(() => (copyButton.textContent = "انسخ"), 1500);
  };
  const meta = [
    data.model_version,
    `اللغة ${data.language}`,
    `الصوت ${data.audio_seconds} ث`,
    `التفريغ ${(data.processing_ms / 1000).toFixed(1)} ث`,
  ];
  byId("transcribe-meta").replaceChildren(...meta.map((text) => Object.assign(document.createElement("span"), { textContent: text })));
}

bindRecordButton(byId("record-button"), byId("record-timer"), transcribeStatus, ({ blob, filename }) => transcribe(blob, filename));
bindDropZone(byId("transcribe-drop"), byId("transcribe-file"), (file) => transcribe(file, file.name));

// ---------------------------------------------------------------- voices (shared by speak + voices tabs)
let voices = [];
let selectedVoice = null;
try { selectedVoice = localStorage.getItem(VOICE_STORAGE_KEY); } catch {}

async function loadVoices() {
  const response = await fetch("/v1/voices", { headers: authHeaders() });
  if (!response.ok) {
    byId("voice-grid").replaceChildren(Object.assign(document.createElement("p"), {
      className: "empty", textContent: await errorMessage(response),
    }));
    return;
  }
  voices = (await response.json()).voices;
  renderVoiceGrid();
  renderVoiceList();
}

function voicesForLanguage(language) {
  const seen = new Map();
  for (const voice of voices) if (voice.language === language && !seen.has(voice.id)) seen.set(voice.id, voice);
  return [...seen.values()].sort((a, b) => Number(b.cloned) - Number(a.cloned));
}

function renderVoiceGrid() {
  const options = voicesForLanguage(byId("speak-language").value);
  if (!options.some((voice) => voice.id === selectedVoice)) selectedVoice = options[0]?.id ?? null;
  byId("voice-grid").replaceChildren(...options.map((voice) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "voice-option";
    button.setAttribute("aria-pressed", String(voice.id === selectedVoice));
    const label = voice.cloned ? "مستنسخ" : voice.description.includes("female") ? "ست" : voice.description.includes("male") ? "راجل" : "";
    button.append(document.createTextNode(voice.id), Object.assign(document.createElement("small"), { textContent: label }));
    button.addEventListener("click", () => {
      selectedVoice = voice.id;
      try { localStorage.setItem(VOICE_STORAGE_KEY, voice.id); } catch {}
      renderVoiceGrid();
    });
    return button;
  }));
}

function renderVoiceList() {
  const cloned = voicesForLanguage("ar").filter((voice) => voice.cloned);
  const list = byId("voice-list");
  if (!cloned.length) {
    list.replaceChildren(Object.assign(document.createElement("li"), { className: "empty", textContent: "لسه مفيش أصوات مستنسخة." }));
  } else {
    list.replaceChildren(...cloned.map((voice) => {
      const item = document.createElement("li");
      item.className = "voice-card";
      const avatar = Object.assign(document.createElement("span"), { className: "voice-avatar", textContent: voice.id[0] });
      const body = document.createElement("div");
      body.className = "voice-body";
      body.append(Object.assign(document.createElement("strong"), { textContent: voice.id }),
        Object.assign(document.createElement("p"), { textContent: voice.description }));
      const use = Object.assign(document.createElement("button"), { type: "button", className: "ghost", textContent: "جرّبه" });
      use.addEventListener("click", () => {
        selectedVoice = voice.id;
        renderVoiceGrid();
        showTab("speak");
      });
      const remove = Object.assign(document.createElement("button"), { type: "button", className: "ghost danger", textContent: "امسح" });
      remove.addEventListener("click", () => deleteVoice(voice.id));
      item.append(avatar, body, use, remove);
      return item;
    }));
  }
  const builtIn = voicesForLanguage("ar").filter((voice) => !voice.cloned).length;
  byId("builtin-count").textContent = builtIn ? `وفيه كمان ${builtIn} صوت جاهز في قسم «نطق».` : "";
}

async function deleteVoice(voiceId) {
  if (!confirm(`تمسح صوت «${voiceId}»؟ مش هينفع ترجّعه.`)) return;
  const response = await fetch(`/v1/voices/${encodeURIComponent(voiceId)}`, { method: "DELETE", headers: authHeaders() });
  if (!response.ok) return setStatus(byId("clone-status"), await errorMessage(response), true);
  setStatus(byId("clone-status"), `اتمسح «${voiceId}».`);
  loadVoices();
}

byId("api-token").addEventListener("change", loadVoices);
byId("speak-language").addEventListener("change", renderVoiceGrid);
loadVoices();

// ---------------------------------------------------------------- text to speech
const speakStatus = byId("speak-status");
const speakButton = byId("speak-button");
const speakPlayer = byId("speak-player");
const speakDownload = byId("speak-download");
const speakTranscribe = byId("speak-transcribe");
const speakText = byId("speak-text");
let audioUrl = null;
let generatedSpeech = null;

const updateCounter = () => (byId("speak-counter").textContent = `${speakText.value.length} / ${speakText.maxLength}`);
speakText.addEventListener("input", updateCounter);
updateCounter();

speakTranscribe.addEventListener("click", () => {
  if (generatedSpeech) transcribe(generatedSpeech.blob, generatedSpeech.filename);
});

speakButton.addEventListener("click", async () => {
  const format = byId("speak-format").value;
  speakButton.disabled = true;
  const stop = startBusyStatus(speakStatus, "بيولّد الصوت…");
  try {
    const response = await fetch("/v1/speak", {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ text: speakText.value, language: byId("speak-language").value, voice: selectedVoice, format }),
    });
    if (!response.ok) throw new Error(await errorMessage(response));
    const blob = await response.blob();
    generatedSpeech = { blob, filename: `speech.${format}` };
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    audioUrl = URL.createObjectURL(blob);
    speakPlayer.src = audioUrl;
    speakPlayer.hidden = false;
    speakPlayer.play().catch(() => {});
    speakDownload.href = audioUrl;
    speakDownload.download = generatedSpeech.filename;
    speakDownload.hidden = false;
    speakTranscribe.hidden = false;
    stop();
    const processing = (Number(response.headers.get("X-Processing-Ms")) / 1000).toFixed(1);
    setStatus(speakStatus, `${response.headers.get("X-Voice")} · صوت ${response.headers.get("X-Audio-Seconds")} ث · اتولّد في ${processing} ث`);
  } catch (error) {
    stop();
    setStatus(speakStatus, error.message, true);
  } finally {
    speakButton.disabled = false;
  }
});

// ---------------------------------------------------------------- clone a voice
const cloneStatus = byId("clone-status");
const cloneButton = byId("clone-button");
const clonePreview = byId("clone-preview");
let cloneSample = null;
let clonePreviewUrl = null;

function setCloneSample(blob, filename) {
  cloneSample = { blob, filename };
  if (clonePreviewUrl) URL.revokeObjectURL(clonePreviewUrl);
  clonePreviewUrl = URL.createObjectURL(blob);
  clonePreview.src = clonePreviewUrl;
  clonePreview.hidden = false;
  cloneButton.disabled = false;
  setStatus(cloneStatus, "اسمع العينة، ولو تمام دوس «استنسخ الصوت».");
}

bindRecordButton(byId("clone-record"), byId("clone-timer"), cloneStatus, ({ blob, filename, seconds }) => {
  if (seconds < 5) return setStatus(cloneStatus, "التسجيل قصير. محتاجين 10 ثواني على الأقل.", true);
  setCloneSample(blob, filename);
}, 30);
bindDropZone(byId("clone-drop"), byId("clone-file"), (file) => setCloneSample(file, file.name));

cloneButton.addEventListener("click", async () => {
  const name = byId("clone-name").value.trim().toLowerCase();
  if (!/^[a-z0-9][a-z0-9_-]{1,31}$/.test(name)) return setStatus(cloneStatus, "اكتب اسم إنجليزي صغير، حرفين على الأقل (مثلًا sara).", true);
  if (!byId("clone-consent").checked) return setStatus(cloneStatus, "لازم صاحب الصوت يوافق الأول.", true);
  if (!cloneSample) return setStatus(cloneStatus, "سجّل أو ارفع عينة الأول.", true);

  const form = new FormData();
  form.append("file", cloneSample.blob, cloneSample.filename);
  form.append("name", name);
  form.append("consent", "true");
  form.append("reference_text", byId("clone-text").value);
  cloneButton.disabled = true;
  const stop = startBusyStatus(cloneStatus, "بيجهّز الصوت…");
  try {
    const response = await fetch("/v1/voices", { method: "POST", headers: authHeaders(), body: form });
    if (!response.ok) throw new Error(await errorMessage(response));
    const voice = await response.json();
    stop();
    byId("clone-text").value = voice.reference_text;
    setStatus(cloneStatus, `اتعمل صوت «${voice.id}» (${voice.seconds} ث). جرّبه من قسم «نطق».`);
    selectedVoice = voice.id;
    try { localStorage.setItem(VOICE_STORAGE_KEY, voice.id); } catch {}
    await loadVoices();
  } catch (error) {
    stop();
    setStatus(cloneStatus, error.message, true);
  } finally {
    cloneButton.disabled = !cloneSample;
  }
});
