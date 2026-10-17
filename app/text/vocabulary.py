"""Per-domain vocabularies passed to Whisper as context (`initial_prompt`).

Context nudges spelling of names and terms; it does not guarantee them, and a long or
off-topic prompt can bias the transcript, so keep each list short and specific.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

VOCABULARY_DIR = Path(__file__).parent / "vocabularies"
_DOMAIN = re.compile(r"^[a-z0-9_-]{1,32}$")


class UnknownDomainError(ValueError):
    pass


@lru_cache
def available_domains() -> tuple[str, ...]:
    return tuple(sorted(p.stem for p in VOCABULARY_DIR.glob("*.json")))


@lru_cache
def prompt_for(domain: str) -> str | None:
    if not _DOMAIN.match(domain) or domain not in available_domains():
        raise UnknownDomainError(f"Unknown domain '{domain}'.")
    terms = json.loads((VOCABULARY_DIR / f"{domain}.json").read_text(encoding="utf-8"))["terms"]
    return "، ".join(terms) if terms else None
