from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural language query")
    top_k: int = Field(default=5, ge=1, le=50, description="Number of results")


class DocumentResult(BaseModel):
    content: str
    score: float
    metadata: dict = Field(default_factory=dict)


class QueryResponse(BaseModel):
    query: str
    results: list[DocumentResult]
    total: int


class HealthResponse(BaseModel):
    status: str
    database: str
    embedding: str
