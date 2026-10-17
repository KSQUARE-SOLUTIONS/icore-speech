// Helpers shared by the local pages: token storage, API errors, status lines, microphone recording.

const TOKEN_STORAGE_KEY = "icore-speech-token";

export function byId(id) {
  return document.getElementById(id);
}

export function bindStoredInput(input, storageKey) {
  try { input.value = localStorage.getItem(storageKey) || ""; } catch {}
  input.addEventListener("change", () => {
    try { localStorage.setItem(storageKey, input.value.trim()); } catch {}
  });
}

export function bindTokenInput(input) {
  bindStoredInput(input, TOKEN_STORAGE_KEY);
  return () => ({ Authorization: `Bearer ${input.value.trim()}` });
}

export function setStatus(element, message, isError = false) {
  element.textContent = message;
  element.classList.toggle("error", isError);
}

export async function errorMessage(response) {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    // FastAPI validation errors: [{ loc: ["body", "field"], msg: "..." }, ...]
    if (Array.isArray(body.detail)) return body.detail.map((e) => `${e.loc?.at(-1)}: ${e.msg}`).join(" · ");
    return JSON.stringify(body.detail);
  } catch {
    return `HTTP ${response.status}`;
  }
}

// Records from the microphone. `onStop` receives { blob, filename } when recording ends.
export class MicrophoneRecorder {
  constructor(onStop) {
    this.onStop = onStop;
    this.recorder = null;
  }

  get isRecording() {
    return this.recorder?.state === "recording";
  }

  async start() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const chunks = [];
    this.recorder = new MediaRecorder(stream);
    this.recorder.addEventListener("dataavailable", (event) => chunks.push(event.data));
    this.recorder.addEventListener("stop", () => {
      stream.getTracks().forEach((track) => track.stop());
      const type = this.recorder.mimeType || "audio/webm";
      const extension = type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
      this.onStop({ blob: new Blob(chunks, { type }), filename: `recording.${extension}` });
    });
    this.recorder.start();
  }

  stop() {
    if (this.isRecording) this.recorder.stop();
  }
}
