"""Generate prose answers from retrieved context chunks.

Uses a local LLM via Ollama to synthesize a natural-language answer
from semantically-retrieved content when no structured trail data
matches the user's query.
"""

from __future__ import annotations

import logging

from api.nlq.ollama_client import generate_completion
from utils.exceptions import LlmConnectionError

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a helpful assistant answering questions about US National Parks.
Answer based ONLY on the provided context below. If the context doesn't \
contain enough information to fully answer the question, say so.
Cite which parks the information comes from.
Keep your answer concise (2-4 sentences).\
"""


def _format_context(chunks: list[dict]) -> str:
    """Format context chunks into a readable text block for the LLM.

    Args:
        chunks: List of dicts with keys: title, chunk_text, park_code,
            park_name, source_type, similarity_score.

    Returns:
        A formatted string with each chunk labeled by park and title.
    """
    parts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        park = chunk.get("park_name") or chunk.get("park_code", "Unknown")
        title = chunk.get("title") or "Untitled"
        text = chunk.get("chunk_text", "")
        parts.append(f"[{i}] {park} - {title}\n{text}")
    return "\n\n".join(parts)


async def generate_from_context(
    user_query: str,
    context_chunks: list[dict],
) -> str | None:
    """Generate a prose answer from retrieved context chunks.

    Formats the chunks into a context block, sends them with the user's
    query to the LLM, and returns the generated answer.

    Args:
        user_query: The original user question.
        context_chunks: Retrieved content chunks to use as context.

    Returns:
        The generated answer string, or None if generation fails
        (e.g. Ollama unavailable or empty context).
    """
    if not context_chunks:
        return None

    context_text = _format_context(context_chunks)

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Context:\n{context_text}\n\nQuestion: {user_query}",
        },
    ]

    try:
        answer = await generate_completion(messages)
        return answer if answer and answer.strip() else None
    except LlmConnectionError:
        logger.warning("Ollama unavailable for generation; returning raw chunks only")
        return None
