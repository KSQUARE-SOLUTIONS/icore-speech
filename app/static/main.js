import {
  byId, bindTokenInput, setStatus, startBusyStatus, errorMessage, formatClock, MicrophoneRecorder,
} from "/static/common.js";

const VOICE_STORAGE_KEY = "icore-speech-voice";
const authHeaders = bindTokenInput(byId("api-token"));

// ---------------------------------------------------------------- tabs
const tabs = ["listen", "speak", "voices", "dictionary"];
function showTab(name) {
  for (const tab of tabs) {
    byId(`tab-${tab}`).setAttribute("aria-selected", String(tab === name));
    byId(`panel-${tab}`).hidden = tab !== name;
  }
}
tabs.forEach((tab) => byId(`tab-${tab}`).addEventListener("click", () => showTab(tab)));
byId("go-to-voices").addEventListener("click", () => showTab("voices"));
byId("go-to-dictionary").addEventListener("click", () => showTab("dictionary"));

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
// Who is being spoken to: marks "you" endings server-side (ايدك -> ايدِك for a woman).
const ADDRESSEE_STORAGE_KEY = "icore-speech-addressee";
let addressee = "auto";
try { addressee = localStorage.getItem(ADDRESSEE_STORAGE_KEY) || "auto"; } catch {}
const addresseeButtons = [...document.querySelectorAll("[data-addressee]")];
function renderAddressee() {
  addresseeButtons.forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.addressee === addressee)));
}
addresseeButtons.forEach((button) => button.addEventListener("click", () => {
  addressee = button.dataset.addressee;
  try { localStorage.setItem(ADDRESSEE_STORAGE_KEY, addressee); } catch {}
  renderAddressee();
}));
renderAddressee();

// Returns { blob, headers } for `text` in the selected voice; throws with a readable message.
async function requestSpeech(text, format = "mp3") {
  const response = await fetch("/v1/speak", {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ text, language: byId("speak-language").value, voice: selectedVoice, format, addressee }),
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return { blob: await response.blob(), headers: response.headers };
}

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
    const { blob, headers } = await requestSpeech(speakText.value, format);
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
    const processing = (Number(headers.get("X-Processing-Ms")) / 1000).toFixed(1);
    setStatus(speakStatus, `${headers.get("X-Voice")} · صوت ${headers.get("X-Audio-Seconds")} ث · اتولّد في ${processing} ث`);
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

// ---------------------------------------------------------------- pronunciation dictionary
const fixStatus = byId("fix-status");
const fixPlayer = byId("fix-player");
let fixAudioUrl = null;

async function playWord(word, message) {
  const stop = startBusyStatus(fixStatus, message);
  try {
    const { blob } = await requestSpeech(word);
    stop();
    if (fixAudioUrl) URL.revokeObjectURL(fixAudioUrl);
    fixAudioUrl = URL.createObjectURL(blob);
    fixPlayer.src = fixAudioUrl;
    fixPlayer.hidden = false;
    fixPlayer.play().catch(() => {});
    setStatus(fixStatus, `ده نطق «${word}» بصوت ${selectedVoice}.`);
  } catch (error) {
    stop();
    setStatus(fixStatus, error.message, true);
  }
}

async function loadFixes() {
  const response = await fetch("/v1/pronunciations", { headers: authHeaders() });
  const list = byId("fix-list");
  if (!response.ok) return list.replaceChildren(Object.assign(document.createElement("li"), { className: "empty", textContent: await errorMessage(response) }));
  const fixes = (await response.json()).pronunciations;
  if (!fixes.length) return list.replaceChildren(Object.assign(document.createElement("li"), { className: "empty", textContent: "لسه مفيش تصليحات." }));
  list.replaceChildren(...fixes.map((fix) => {
    const item = document.createElement("li");
    item.className = "voice-card";
    const body = document.createElement("div");
    body.className = "voice-body";
    const line = document.createElement("strong");
    line.append(document.createTextNode(fix.word), Object.assign(document.createElement("span"), { className: "fix-arrow", textContent: "←" }), document.createTextNode(fix.spoken));
    body.append(line, Object.assign(document.createElement("p"), { textContent: fix.source === "local" ? "متضافة من الصفحة" : "أساسية في الريبو" }));
    const listen = Object.assign(document.createElement("button"), { type: "button", className: "ghost", textContent: "اسمع" });
    listen.addEventListener("click", () => playWord(fix.word, "بيولّد…"));
    item.append(body, listen);
    if (fix.source === "local") {
      const remove = Object.assign(document.createElement("button"), { type: "button", className: "ghost danger", textContent: "امسح" });
      remove.addEventListener("click", async () => {
        const result = await fetch(`/v1/pronunciations/${encodeURIComponent(fix.word)}`, { method: "DELETE", headers: authHeaders() });
        if (!result.ok) return setStatus(fixStatus, await errorMessage(result), true);
        setStatus(fixStatus, `اتمسح تصليح «${fix.word}».`);
        loadFixes();
      });
      item.append(remove);
    }
    return item;
  }));
}

byId("fix-listen-before").addEventListener("click", () => {
  const word = byId("fix-word").value.trim();
  if (!word) return setStatus(fixStatus, "اكتب الكلمة الأول.", true);
  playWord(word, "بيولّد النطق الحالي…");
});

byId("fix-save").addEventListener("click", async () => {
  const word = byId("fix-word").value.trim();
  const spoken = byId("fix-spoken").value.trim();
  if (!word || !spoken) return setStatus(fixStatus, "اكتب الكلمة والطريقة اللي تتقري بيها.", true);
  const response = await fetch(`/v1/pronunciations/${encodeURIComponent(word)}`, {
    method: "PUT",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ spoken }),
  });
  if (!response.ok) return setStatus(fixStatus, await errorMessage(response), true);
  await loadFixes();
  playWord(word, "اتحفظ، بيولّد النطق الجديد…");
});

byId("api-token").addEventListener("change", loadFixes);
loadFixes();
