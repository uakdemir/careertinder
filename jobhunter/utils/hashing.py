import hashlib
import re


def normalize_and_hash(company: str, title: str) -> str:
    """Generate a SHA-256 fingerprint hash for deduplication.

    Formula: sha256(normalize(company) + "|" + normalize(title))

    Normalization: lowercase, strip whitespace, remove special characters,
    collapse multiple spaces.
    """
    normalized = f"{_normalize(company)}|{_normalize(title)}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def file_hash(file_path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text
