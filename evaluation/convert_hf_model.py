"""Convert a Hugging Face Whisper checkpoint (e.g. a fine-tuned Egyptian model) to the
CTranslate2 format faster-whisper loads, so it can join the benchmark.

Needs transformers + torch (`uv sync --extra chatterbox` already installs them).

Usage:
    uv run python -m evaluation.convert_hf_model MAdel121/whisper-small-egyptian-arabic

The converted model lands in models/whisper/<name>-ct2/; pass that path to --models or
ICORE_STT_MODEL.
"""

import argparse
import shutil
from pathlib import Path

from app.config import get_settings


def convert(repo_id: str, quantization: str) -> Path:
    import ctranslate2
    from huggingface_hub import hf_hub_download
    from transformers import AutoTokenizer

    output_dir = get_settings().models_dir / "whisper" / f"{repo_id.split('/')[-1]}-ct2"
    if output_dir.exists():
        shutil.rmtree(output_dir)

    ctranslate2.converters.TransformersConverter(repo_id).convert(str(output_dir), quantization=quantization)
    # faster-whisper reads tokenizer.json; fine-tuned repos often ship only the slow-tokenizer files.
    AutoTokenizer.from_pretrained(repo_id).save_pretrained(str(output_dir / "_tokenizer"))
    shutil.move(str(output_dir / "_tokenizer" / "tokenizer.json"), output_dir / "tokenizer.json")
    shutil.rmtree(output_dir / "_tokenizer")
    shutil.copy(hf_hub_download(repo_id, "preprocessor_config.json"), output_dir / "preprocessor_config.json")
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("repo_id")
    parser.add_argument("--quantization", default="float16")
    args = parser.parse_args()
    print(convert(args.repo_id, args.quantization))


if __name__ == "__main__":
    main()
