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
// A person can have several recordings, one per tone (karim, karim-excited, ...): the server
// lists each with its `person` and `tone`, and /v1/speak takes voice=<person> + tone.
const TONE_STORAGE_KEY = "icore-speech-tone";
const TONE_SCRIPTS = {
  "": { mood: "على طبيعتك", text: "بص يا سيدي، أنا هحكيلك عن حاجة بسيطة بتفرق معايا في الشغل كل يوم. مش حاجة صعبة خالص، بس محتاجة تركيز شوية." },
  excited: { mood: "متحمس", text: "يا جماعة مش مصدق! الفكرة اشتغلت من أول مرة! ده أحلى خبر سمعته السنة دي كلها، بجد أنا مبسوط جدًا!" },
  angry: { mood: "متعصب", text: "لا بقى، كده كتير! أنا قلت الكلام ده مية مرة ومحدش بيسمع. مش هينفع نكمّل بالشكل ده تاني!" },
  calm: { mood: "هادي", text: "خد نفس براحة… مفيش حاجة مستعجلة. هنمشي خطوة خطوة، وكل حاجة هتبقى تمام، صدقني." },
  serious: { mood: "بتتكلم جد", text: "الموضوع ده مهم ولازم نتكلم فيه بوضوح. القرار اللي هناخده النهارده هيأثر على الشغل كله الفترة الجاية." },
  sad: { mood: "زعلان", text: "بصراحة الأيام دي صعبة شوية… كنت متوقع حاجات كتير وماحصلتش. بس إن شاء الله هنعدّيها." },
};
let voices = [];
let tones = {};
let selectedVoice = null;
let selectedTone = "";
try {
  selectedVoice = localStorage.getItem(VOICE_STORAGE_KEY);
  selectedTone = localStorage.getItem(TONE_STORAGE_KEY) || "";
} catch {}

function rememberVoice(person, tone) {
  selectedVoice = person;
  selectedTone = tone ?? "";
  try {
    localStorage.setItem(VOICE_STORAGE_KEY, selectedVoice);
    localStorage.setItem(TONE_STORAGE_KEY, selectedTone);
  } catch {}
}

const toneLabel = (tone) => (tone ? tones[tone] ?? tone : "عادي");
const allTones = () => ["", ...Object.keys(tones)];

// Renders a row of tone buttons ("" = the normal tone) into `container`.
function renderToneSwitch(container, toneIds, selected, onPick) {
  container.replaceChildren(...toneIds.map((tone) => {
    const button = Object.assign(document.createElement("button"), { type: "button", textContent: toneLabel(tone) });
    button.setAttribute("role", "radio");
    button.setAttribute("aria-pressed", String(tone === selected));
    button.addEventListener("click", () => onPick(tone));
    return button;
  }));
}

async function loadVoices() {
  const response = await fetch("/v1/voices", { headers: authHeaders() });
  if (!response.ok) {
    byId("voice-grid").replaceChildren(Object.assign(document.createElement("p"), {
      className: "empty", textContent: await errorMessage(response),
    }));
    return;
  }
  ({ voices, tones } = await response.json());
  renderVoiceGrid();
  renderVoiceList();
  renderCloneTone();
}

function voicesForLanguage(language) {
  const seen = new Map();
  for (const voice of voices) if (voice.language === language && !seen.has(voice.id)) seen.set(voice.id, voice);
  return [...seen.values()].sort((a, b) => Number(b.cloned) - Number(a.cloned));
}

// Groups the voices of a language by person: [{ id, cloned, description, tones: Map(tone -> voice) }].
function peopleForLanguage(language) {
  const people = new Map();
  for (const voice of voicesForLanguage(language)) {
    const person = people.get(voice.person) ?? { id: voice.person, cloned: voice.cloned, description: voice.description, tones: new Map() };
    person.tones.set(voice.tone ?? "", voice);
    people.set(voice.person, person);
  }
  return [...people.values()];
}

function renderVoiceGrid() {
  const people = peopleForLanguage(byId("speak-language").value);
  if (!people.some((person) => person.id === selectedVoice)) selectedVoice = people[0]?.id ?? null;
  byId("voice-grid").replaceChildren(...people.map((person) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "voice-option";
    button.setAttribute("aria-pressed", String(person.id === selectedVoice));
    const label = person.cloned
      ? person.tones.size > 1 ? `مستنسخ · ${person.tones.size} نبرات` : "مستنسخ"
      : person.description.includes("female") ? "ست" : person.description.includes("male") ? "راجل" : "";
    button.append(document.createTextNode(person.id), Object.assign(document.createElement("small"), { textContent: label }));
    button.addEventListener("click", () => {
      rememberVoice(person.id, selectedTone);
      renderVoiceGrid();
    });
    return button;
  }));
  renderSpeakTone(people.find((person) => person.id === selectedVoice));
}

// Tone row under the voice grid: only the tones this person has recorded.
function renderSpeakTone(person) {
  const recorded = person ? allTones().filter((tone) => person.tones.has(tone)) : [];
  if (!recorded.includes(selectedTone)) selectedTone = recorded[0] ?? "";
  byId("speak-tone-field").hidden = recorded.length < 2;
  byId("speak-tone-person").textContent = person ? `· ${person.id}` : "";
  renderToneSwitch(byId("speak-tone"), recorded, selectedTone, (tone) => {
    rememberVoice(selectedVoice, tone);
    renderSpeakTone(person);
  });
}

// One card per cloned person: a chip per recorded tone (× deletes it) and a dashed chip per missing
// tone that sets the recording form up for it.
function renderVoiceList() {
  const cloned = peopleForLanguage("ar").filter((person) => person.cloned);
  const list = byId("voice-list");
  if (!cloned.length) {
    list.replaceChildren(Object.assign(document.createElement("li"), { className: "empty", textContent: "لسه مفيش أصوات مستنسخة." }));
  } else {
    list.replaceChildren(...cloned.map((person) => {
      const item = document.createElement("li");
      item.className = "voice-card";
      const avatar = Object.assign(document.createElement("span"), { className: "voice-avatar", textContent: person.id[0] });
      const chips = document.createElement("div");
      chips.className = "tone-chips";
      for (const tone of allTones()) {
        const voice = person.tones.get(tone);
        if (voice) {
          const chip = Object.assign(document.createElement("span"), { className: "tone-chip", textContent: toneLabel(tone) });
          const remove = Object.assign(document.createElement("button"), { type: "button", textContent: "×" });
          remove.setAttribute("aria-label", `امسح نبرة ${toneLabel(tone)}`);
          remove.addEventListener("click", () => deleteVoice(voice.id));
          chip.append(remove);
          chips.append(chip);
        } else {
          const add = Object.assign(document.createElement("button"), { type: "button", className: "tone-chip missing", textContent: `+ ${toneLabel(tone)}` });
          add.addEventListener("click", () => prepareRecording(person.id, tone));
          chips.append(add);
        }
      }
      const body = document.createElement("div");
      body.className = "voice-body";
      body.append(Object.assign(document.createElement("strong"), { textContent: person.id }), chips);
      const use = Object.assign(document.createElement("button"), { type: "button", className: "ghost", textContent: "جرّبه" });
      use.addEventListener("click", () => {
        rememberVoice(person.id, selectedVoice === person.id ? selectedTone : "");
        renderVoiceGrid();
        showTab("speak");
      });
      item.append(avatar, body, use);
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
    body: JSON.stringify({ text, language: byId("speak-language").value, voice: selectedVoice, tone: selectedTone || null, format, addressee }),
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
let cloneTone = "";

function renderCloneTone() {
  renderToneSwitch(byId("clone-tone"), allTones(), cloneTone, (tone) => {
    cloneTone = tone;
    renderCloneTone();
  });
  const script = TONE_SCRIPTS[cloneTone] ?? { mood: toneLabel(cloneTone), text: "" };
  byId("clone-mood").textContent = script.mood;
  byId("clone-script").textContent = script.text;
}
renderCloneTone();

// From a "+ tone" chip: fill in the person and tone, ready to record.
function prepareRecording(person, tone) {
  byId("clone-name").value = person;
  cloneTone = tone;
  renderCloneTone();
  setStatus(cloneStatus, `سجّل «${person}» وهو ${TONE_SCRIPTS[tone]?.mood ?? toneLabel(tone)}.`);
  byId("clone-record").scrollIntoView({ behavior: "smooth", block: "center" });
  byId("clone-record").focus({ preventScroll: true });
}

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
  form.append("tone", cloneTone);
  cloneButton.disabled = true;
  const stop = startBusyStatus(cloneStatus, "بيجهّز الصوت…");
  try {
    const response = await fetch("/v1/voices", { method: "POST", headers: authHeaders(), body: form });
    if (!response.ok) throw new Error(await errorMessage(response));
    const voice = await response.json();
    stop();
    byId("clone-text").value = voice.reference_text;
    setStatus(cloneStatus, `اتسجّل «${voice.person}» بنبرة ${toneLabel(voice.tone)} (${voice.seconds} ث). جرّبه من قسم «نطق».`);
    rememberVoice(voice.person, voice.tone);
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
