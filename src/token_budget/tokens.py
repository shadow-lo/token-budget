"""Token counting: a fast offline estimate, or tiktoken if requested."""

import codecs
from typing import Callable, Optional

CHARS_PER_TOKEN = 4
CHUNK = 64 * 1024

# Nominal context windows. Check your provider's docs; they change often.
MODEL_LIMITS = {
    "claude": 200_000,
    "gpt": 128_000,
    "gemini": 1_000_000,
}


def estimate(chars: int) -> int:
    """Rough token estimate: ~4 characters per token, rounded up."""
    return -(-chars // CHARS_PER_TOKEN)


def get_exact_counter() -> Callable[[str], int]:
    """Return a tiktoken-based counter or raise RuntimeError if not installed."""
    try:
        import tiktoken  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "--exact needs tiktoken: pip install 'token-budget[exact]'"
        ) from exc
    enc = tiktoken.get_encoding("cl100k_base")
    return lambda text: len(enc.encode(text, disallowed_special=()))


def count_file(path: str, exact: Optional[Callable[[str], int]] = None) -> int:
    """Count tokens in a file, reading it in chunks.

    Undecodable bytes are replaced, so non-UTF-8 files never raise. Raises
    OSError if the file cannot be read.
    """
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    chars = 0
    tokens = 0
    with open(path, "rb") as fh:
        while True:
            raw = fh.read(CHUNK)
            text = decoder.decode(raw, final=not raw)
            if exact is not None:
                tokens += exact(text) if text else 0
            else:
                chars += len(text)
            if not raw:
                break
    return tokens if exact is not None else estimate(chars)
