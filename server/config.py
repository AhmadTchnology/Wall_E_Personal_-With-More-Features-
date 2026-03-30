from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database connection (separate fields)
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str

    # NVIDIA NIM
    nvidia_api_key: str
    nvidia_embed_url: str
    embed_model: str
    embed_dimension: int

    # Table configuration
    table_name: str
    content_column: str
    embedding_column: str
    metadata_column: str

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
