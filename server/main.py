import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import db
import embeddings
from config import get_settings
from schemas import (
    DocumentResult,
    HealthResponse,
    QueryRequest,
    QueryResponse,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("wall-e-kb")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage async resources: DB pool up on start, down on shutdown."""
    await db.init_pool()
    logger.info("Database pool initialized")
    yield
    await db.close_pool()
    logger.info("Database pool closed")


app = FastAPI(
    title="Wall-E Knowledge Base",
    description="RAG retrieval service for the Wall-E AI assistant",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health():
    """Quick liveness / readiness check."""
    db_ok = "ok"
    embed_ok = "ok"

    try:
        pool = db._pool
        if pool is None:
            db_ok = "not_connected"
        else:
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
    except Exception as exc:
        db_ok = f"error: {exc}"

    settings = get_settings()
    if not settings.nvidia_api_key:
        embed_ok = "no_api_key"

    return HealthResponse(status="healthy", database=db_ok, embedding=embed_ok)


@app.post("/query", response_model=QueryResponse)
async def query_knowledge_base(req: QueryRequest):
    """
    1. Embed the query via NVIDIA NIM
    2. Cosine-similarity search in pgvector
    3. Return ranked results
    """
    logger.info(f"Query received: {req.query[:80]}")

    try:
        query_vector = await embeddings.get_embedding(req.query)
        logger.info(f"Embedding OK — dim={len(query_vector)}")
    except Exception as exc:
        logger.error(f"Embedding failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Embedding service error: {exc}",
        )

    try:
        rows = await db.search_similar(query_vector, top_k=req.top_k)
        logger.info(f"DB search OK — {len(rows)} results")
    except Exception as exc:
        logger.error(f"DB search failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Database search error: {exc}",
        )

    results = [DocumentResult(**r) for r in rows]
    return QueryResponse(query=req.query, results=results, total=len(results))
