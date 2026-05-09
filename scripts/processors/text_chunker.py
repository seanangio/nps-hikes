"""Text chunking logic for NPS content.

Converts raw content records (thingstodo, places, park descriptions) into
embeddable text chunks. Each chunk is prefixed with title and park name
for embedding context.
"""

from __future__ import annotations

MAX_CHUNK_LENGTH = 2000


def chunk_thingstodo(record: dict) -> list[dict]:
    """Convert a thingstodo record into embeddable text chunks.

    Concatenates title + short_description + long_description into a
    single chunk. Splits on paragraph boundaries if over MAX_CHUNK_LENGTH.

    Args:
        record: Dict with keys from the nps_thingstodo table.

    Returns:
        List of chunk dicts with keys: chunk_text, source_type, source_id,
        title, park_code, metadata.
    """
    title = record.get("title", "")
    short_desc = record.get("short_description") or ""
    long_desc = record.get("long_description") or ""

    # Build full text with title prefix for embedding context
    parts = [p for p in [title, short_desc, long_desc] if p.strip()]
    full_text = "\n\n".join(parts)

    if not full_text.strip():
        if title.strip():
            full_text = title
        else:
            return []

    metadata = {}
    for key in ("tags", "season", "duration", "activities", "topics"):
        val = record.get(key)
        if val:
            metadata[key] = val

    chunks = _split_text(full_text)

    return [
        {
            "chunk_text": chunk,
            "source_type": "thingstodo",
            "source_id": record.get("id"),
            "title": title,
            "park_code": record.get("park_code"),
            "metadata": metadata,
        }
        for chunk in chunks
    ]


def chunk_places(record: dict) -> list[dict]:
    """Convert a places record into embeddable text chunks.

    Combines title + short_description + body_text. Same splitting logic
    as chunk_thingstodo.

    Args:
        record: Dict with keys from the nps_places table.

    Returns:
        List of chunk dicts.
    """
    title = record.get("title", "")
    short_desc = record.get("short_description") or ""
    body_text = record.get("body_text") or ""

    parts = [p for p in [title, short_desc, body_text] if p.strip()]
    full_text = "\n\n".join(parts)

    if not full_text.strip():
        if title.strip():
            full_text = title
        else:
            return []

    metadata = {}
    tags = record.get("tags")
    if tags:
        metadata["tags"] = tags

    chunks = _split_text(full_text)

    return [
        {
            "chunk_text": chunk,
            "source_type": "places",
            "source_id": record.get("id"),
            "title": title,
            "park_code": record.get("park_code"),
            "metadata": metadata,
        }
        for chunk in chunks
    ]


def chunk_park_description(
    park_code: str, park_name: str, description: str
) -> list[dict]:
    """Convert a park description into an embeddable text chunk.

    Park descriptions are short (1-3 sentences), always a single chunk.

    Args:
        park_code: 4-character park code.
        park_name: Full park name for context.
        description: Park description text.

    Returns:
        List with zero or one chunk dict.
    """
    if not description or not description.strip():
        return []

    chunk_text = f"{park_name}\n\n{description}"

    return [
        {
            "chunk_text": chunk_text,
            "source_type": "park_description",
            "source_id": park_code,
            "title": park_name,
            "park_code": park_code,
            "metadata": {},
        }
    ]


def _split_text(text: str) -> list[str]:
    """Split text on paragraph boundaries if it exceeds MAX_CHUNK_LENGTH.

    If individual paragraphs still exceed MAX_CHUNK_LENGTH, they are
    further split on sentence boundaries to stay within the embedding
    model's context window.

    Args:
        text: Text to potentially split.

    Returns:
        List of text chunks, each under MAX_CHUNK_LENGTH.
    """
    if len(text) <= MAX_CHUNK_LENGTH:
        return [text]

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current_chunk = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # If a single paragraph exceeds the limit, split on sentences
        if len(para) > MAX_CHUNK_LENGTH:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""
            chunks.extend(_split_long_paragraph(para))
            continue

        if not current_chunk:
            current_chunk = para
        elif len(current_chunk) + len(para) + 2 <= MAX_CHUNK_LENGTH:
            current_chunk += "\n\n" + para
        else:
            chunks.append(current_chunk)
            current_chunk = para

    if current_chunk:
        chunks.append(current_chunk)

    return chunks if chunks else [text[:MAX_CHUNK_LENGTH]]


def _split_long_paragraph(text: str) -> list[str]:
    """Split a long paragraph on sentence boundaries.

    Args:
        text: A paragraph that exceeds MAX_CHUNK_LENGTH.

    Returns:
        List of text chunks, each at most MAX_CHUNK_LENGTH.
    """
    import re

    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current_chunk = ""

    for sentence in sentences:
        if not current_chunk:
            current_chunk = sentence
        elif len(current_chunk) + len(sentence) + 1 <= MAX_CHUNK_LENGTH:
            current_chunk += " " + sentence
        else:
            chunks.append(current_chunk)
            current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk)

    # Final safety: hard-truncate any chunk still over the limit
    # (e.g., a single very long sentence)
    return (
        [c[:MAX_CHUNK_LENGTH] for c in chunks] if chunks else [text[:MAX_CHUNK_LENGTH]]
    )
