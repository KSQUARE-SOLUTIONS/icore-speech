"""Speech-to-text benchmark: same clips, several models, WER/CER/RTF side by side.

Usage:
    uv run --group dev python -m evaluation.run_benchmark \
        --manifest evaluation/manifest.csv --models large-v3-turbo small

manifest.csv columns: audio_path,reference
  audio_path  path relative to the manifest file
  reference   the human-checked transcript (never the model's own output)

Writes a CSV per run to evaluation/results/ and prints a summary table.
"""

import argparse
import csv
import statistics
import time
from datetime import datetime
from pathlib import Path

import jiwer

from app.config import Settings
from app.stt.engine import SttEngine
from app.text.arabic_normalizer import clean_whitespace, normalize_arabic

RESULTS_DIR = Path(__file__).parent / "results"


def read_manifest(path: Path) -> list[tuple[Path, str]]:
    with path.open(encoding="utf-8") as handle:
        return [(path.parent / row["audio_path"], row["reference"]) for row in csv.DictReader(handle)]


def error_rates(references: list[str], hypotheses: list[str]) -> dict[str, float]:
    raw_refs = [clean_whitespace(r) for r in references]
    raw_hyps = [clean_whitespace(h) for h in hypotheses]
    norm_refs = [normalize_arabic(r) for r in references]
    norm_hyps = [normalize_arabic(h) for h in hypotheses]
    return {
        "wer_raw": jiwer.wer(raw_refs, raw_hyps),
        "wer_normalized": jiwer.wer(norm_refs, norm_hyps),
        "cer_normalized": jiwer.cer(norm_refs, norm_hyps),
    }


def benchmark(model: str, clips: list[tuple[Path, str]], language: str, base: Settings) -> dict:
    engine = SttEngine(base.model_copy(update={"stt_model": model}))
    load_started = time.perf_counter()
    engine.load()
    load_seconds = time.perf_counter() - load_started

    rows, hypotheses, audio_total, processing_total, latencies = [], [], 0.0, 0.0, []
    for audio_path, reference in clips:
        result = engine.transcribe(audio_path, language)
        hypotheses.append(result.text)
        audio_total += result.audio_seconds
        processing_total += result.processing_ms / 1000
        latencies.append(result.processing_ms)
        rows.append({"model": model, "audio_path": str(audio_path), "reference": reference, "hypothesis": result.text,
                     "audio_seconds": result.audio_seconds, "processing_ms": result.processing_ms})

    summary = {
        "model": model,
        "clips": len(clips),
        **error_rates([r for _, r in clips], hypotheses),
        "rtf": processing_total / audio_total if audio_total else 0.0,
        "latency_p50_ms": statistics.median(latencies),
        "latency_p95_ms": sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)],
        "load_seconds": load_seconds,
    }
    return {"summary": summary, "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--models", nargs="+", default=["large-v3-turbo"])
    parser.add_argument("--language", default="ar")
    args = parser.parse_args()

    clips = read_manifest(args.manifest)
    base = Settings()
    runs = [benchmark(model, clips, args.language, base) for model in args.models]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    detail_path = RESULTS_DIR / f"{stamp}-detail.csv"
    with detail_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(runs[0]["rows"][0]))
        writer.writeheader()
        for run in runs:
            writer.writerows(run["rows"])

    summary_path = RESULTS_DIR / f"{stamp}-summary.csv"
    summaries = [run["summary"] for run in runs]
    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)

    print(f"\n{'model':<24}{'clips':>6}{'WER raw':>10}{'WER norm':>10}{'CER norm':>10}{'RTF':>7}{'p50 ms':>9}")
    for s in summaries:
        print(f"{s['model']:<24}{s['clips']:>6}{s['wer_raw']:>10.1%}{s['wer_normalized']:>10.1%}"
              f"{s['cer_normalized']:>10.1%}{s['rtf']:>7.2f}{s['latency_p50_ms']:>9.0f}")
    print(f"\nDetail:  {detail_path}\nSummary: {summary_path}")


if __name__ == "__main__":
    main()
