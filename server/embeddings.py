import httpx
from config import get_settings


async def get_embedding(text: str) -> list[float]:
    """Vectorize text using NVIDIA NIM embedding API."""
    settings = get_settings()

    # Handle both /v1 and /v1/embeddings URL formats
    url = settings.nvidia_embed_url.rstrip("/")
    if not url.endswith("/embeddings"):
        url = f"{url}/embeddings"

    headers = {
        "Authorization": f"Bearer {settings.nvidia_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "model": settings.embed_model,
        "input": [text],
        "input_type": "query",
        "encoding_format": "float",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            headers=headers,
            json=payload,
        )
        response.raise_for_status()

    data = response.json()
    vec = data["data"][0]["embedding"]
    
    # Strict safeguard: Truncate down to match database column dimension (e.g. 3072 -> 2048)
    if len(vec) > settings.embed_dimension:
        vec = vec[:settings.embed_dimension]
        
    return vec
