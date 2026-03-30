"""
knowledge_base.py — Query the Wall-E Knowledge Base server.

Sends a natural-language query to the RAG retrieval endpoint,
which vectorises it via NVIDIA NIM and searches pgvector.
"""

import json
from pathlib import Path

import httpx

_BASE_DIR = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _BASE_DIR / "config" / "api_keys.json"


def _get_server_url() -> str:
    """Read the knowledge base server URL from api_keys.json."""
    cfg = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    return cfg["knowledge_base_url"].rstrip("/")


def knowledge_base(*, parameters: dict, player=None) -> str:
    """
    Tool entry-point called by main.py's _execute_tool.

    Parameters
    ----------
    parameters : dict
        Must contain "query" (str). Optional "top_k" (int, default 5).
    player : WallEUI, optional
        UI handle for logging.
    """
    query = parameters.get("query", "").strip()
    if not query:
        return "No query provided for the knowledge base."

    top_k = int(parameters.get("top_k", 5))
    server_url = _get_server_url()

    if player:
        player.write_log(f"[KB] Searching: {query[:60]}...")

    try:
        resp = httpx.post(
            f"{server_url}/query",
            json={"query": query, "top_k": top_k},
            timeout=30.0,
        )
        resp.raise_for_status()
    except httpx.ConnectError:
        return (
            "Knowledge base server is unreachable. "
            "Make sure the server is running."
        )
    except httpx.HTTPStatusError as exc:
        return f"Knowledge base error (HTTP {exc.response.status_code}): {exc.response.text[:200]}"
    except Exception as exc:
        return f"Knowledge base request failed: {exc}"

    data = resp.json()
    results = data.get("results", [])

    if not results:
        return f"No results found in the knowledge base for: {query}"

    # Format results for Wall-E to speak
    parts = [f"Found {len(results)} result(s) from the knowledge base:\n"]
    for i, r in enumerate(results, 1):
        score = r.get("score", 0)
        content = r.get("content", "").strip()
        # Truncate very long content for speech
        if len(content) > 500:
            content = content[:497] + "..."
        parts.append(f"Result {i} (relevance {score:.0%}): {content}")

    return "\n\n".join(parts)
