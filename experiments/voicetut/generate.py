"""Listening test for VoiceTut-TTS (OmniVoice fine-tuned on ~380 h of Egyptian podcasts).

Runs in its own environment (experiments/voicetut/.venv) because OmniVoice pins its own
torch/transformers. Clones a voice from voices/<speaker>.wav + .txt and renders the same
colloquial sentences used for the Chatterbox comparison.

Usage (from the repo root):
    experiments/voicetut/.venv/bin/python experiments/voicetut/generate.py karim
"""

import argparse
import time
from datetime import datetime
from pathlib import Path

import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
SENTENCES = [
    "يا عم الحاج، الحاجة دي غالية قوي، مفيش حاجة أرخص شوية؟",
    "أنا لسه صاحي من النوم، استناني خمس دقايق وأنا نازل لك على طول.",
    "بقولك إيه، ما تيجي نتغدى سوا النهارده؟ أنا عازمك.",
    "الموبايل فصل شحن وأنا في الشارع، فمقدرتش أرد عليك.",
    "متقلقش خالص، الموضوع ده سهل، وهتلاقيه خلصان بكرة إن شاء الله.",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("speaker")
    parser.add_argument("--model", default=str(ROOT / "models" / "voicetut"))
    parser.add_argument("--device", default=None, help="mps / cpu / cuda (auto when omitted)")
    parser.add_argument("--steps", type=int, default=32)
    args = parser.parse_args()

    from voicetut_tts import VoiceTutTTS

    reference = ROOT / "voices" / f"{args.speaker}.wav"
    reference_text = reference.with_suffix(".txt").read_text(encoding="utf-8")
    out_dir = ROOT / "evaluation" / "results" / f"voicetut-{datetime.now():%Y%m%d-%H%M%S}"
    out_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    if args.device == "mps":
        # Loading straight onto MPS segfaults in transformers' tensor materialisation, so load on
        # CPU and move everything except the audio tokenizer (it does not support MPS).
        tts = VoiceTutTTS.from_pretrained(args.model, device="cpu")
        tokenizer = tts.model.audio_tokenizer
        tts.model.audio_tokenizer = None
        tts.model.to("mps")
        tts.model.audio_tokenizer = tokenizer
    else:
        tts = VoiceTutTTS.from_pretrained(args.model, device=args.device)
    print(f"loaded in {time.perf_counter() - started:.0f}s", flush=True)

    for index, sentence in enumerate(SENTENCES, start=1):
        started = time.perf_counter()
        wav_path = out_dir / f"voicetut__{args.speaker}__{index}.wav"
        tts.synthesize(sentence, ref_audio=str(reference), ref_text=reference_text,
                       num_step=args.steps, output=str(wav_path))
        audio, rate = sf.read(wav_path)
        mp3_path = wav_path.with_suffix(".mp3")
        sf.write(mp3_path, audio, rate, format="MP3")
        wav_path.unlink()
        print(f"{mp3_path.name}: {len(audio) / rate:.1f}s audio in {time.perf_counter() - started:.0f}s", flush=True)
    print(out_dir)


if __name__ == "__main__":
    main()
