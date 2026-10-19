// Helpers shared by the local pages: token storage, API calls, status lines, microphone recording.

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
  element.classList.remove("busy");
}

// Shows "message · 7 ث" ticking every second until the returned stop() is called.
export function startBusyStatus(element, message) {
  const started = performance.now();
  element.classList.remove("error");
  element.classList.add("busy");
  const render = () => {
    element.textContent = `${message} ${Math.round((performance.now() - started) / 1000)} ث`;
  };
  render();
  const timer = setInterval(render, 1000);
  return () => {
    clearInterval(timer);
    element.classList.remove("busy");
  };
}

export async function errorMessage(response) {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    // FastAPI validation errors: [{ loc: ["body", "field"], msg: "..." }, ...]
    if (Array.isArray(body.detail)) return body.detail.map((e) => `${e.loc?.at(-1)}: ${e.msg}`).join(" · ");
    return JSON.stringify(body.detail);
  } catch {
    return response.status === 401 ? "التوكن غلط أو ناقص: حطه من الإعدادات." : `HTTP ${response.status}`;
  }
}

export function formatClock(seconds) {
  const whole = Math.floor(seconds);
  return `${String(Math.floor(whole / 60)).padStart(2, "0")}:${String(whole % 60).padStart(2, "0")}`;
}

// Records from the microphone. `onStop` receives { blob, filename, seconds } when recording ends;
// `onLevel` (optional) receives the input loudness 0..1 about 30 times a second while recording.
export class MicrophoneRecorder {
  constructor(onStop, onLevel = null) {
    this.onStop = onStop;
    this.onLevel = onLevel;
    this.recorder = null;
    this.startedAt = 0;
  }

  get isRecording() {
    return this.recorder?.state === "recording";
  }

  get elapsedSeconds() {
    return this.isRecording ? (performance.now() - this.startedAt) / 1000 : 0;
  }

  async start() {
    // The browser's call processing is on by default: automatic gain control turns the level
    // down a second or two into speech, so the start of a take came out much louder than the
    // rest. Voice references and training clips need the microphone as it is.
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { autoGainControl: false, noiseSuppression: false, echoCancellation: false },
    });
    const chunks = [];
    const stopMeter = this.onLevel ? this.#meter(stream) : () => {};
    this.recorder = new MediaRecorder(stream);
    this.recorder.addEventListener("dataavailable", (event) => chunks.push(event.data));
    this.recorder.addEventListener("stop", () => {
      stopMeter();
      stream.getTracks().forEach((track) => track.stop());
      const type = this.recorder.mimeType || "audio/webm";
      const extension = type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
      const seconds = (performance.now() - this.startedAt) / 1000;
      this.onStop({ blob: new Blob(chunks, { type }), filename: `recording.${extension}`, seconds });
    });
    this.startedAt = performance.now();
    this.recorder.start();
  }

  stop() {
    if (this.isRecording) this.recorder.stop();
  }

  #meter(stream) {
    const context = new AudioContext();
    const analyser = context.createAnalyser();
    analyser.fftSize = 512;
    context.createMediaStreamSource(stream).connect(analyser);
    const samples = new Float32Array(analyser.fftSize);
    let frame = 0;
    const tick = () => {
      analyser.getFloatTimeDomainData(samples);
      const rms = Math.sqrt(samples.reduce((sum, value) => sum + value * value, 0) / samples.length);
      this.onLevel(Math.min(1, rms * 4));
      frame = requestAnimationFrame(tick);
    };
    tick();
    return () => {
      cancelAnimationFrame(frame);
      this.onLevel(0);
      context.close();
    };
  }
}
