import httpx

from app.api.config import get_settings

# Must match what the corpus was embedded with (see app/api/models/chunk.py
# EMBEDDING_DIM) or cosine similarity against stored vectors is meaningless.
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536


async def embed_query(text: str) -> list[float] | None:
    """Embed free text for the vector half of hybrid search.

    Returns None (lexical-only search) if no OpenAI key is configured or the
    embeddings call fails — a degraded search tool beats a broken one.
    """
    settings = get_settings()
    if not settings.openai_api_key or not text.strip():
        return None

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={"model": EMBEDDING_MODEL, "input": text, "dimensions": EMBEDDING_DIM},
            )
            resp.raise_for_status()
            data = resp.json()
            return data["data"][0]["embedding"]
    except (httpx.HTTPError, KeyError, IndexError):
        return None
