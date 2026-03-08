"""Qdrant vector database client and collection initialization."""

from __future__ import annotations

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    PayloadSchemaType,
    VectorParams,
)

from kimiko.config import get_settings

_client: AsyncQdrantClient | None = None


async def init_qdrant() -> AsyncQdrantClient:
    """Initialize the Qdrant client and ensure collection exists."""
    global _client
    settings = get_settings()

    _client = AsyncQdrantClient(url=settings.qdrant_url)

    # Ensure the memories collection exists with proper schema
    collections = await _client.get_collections()
    collection_names = [c.name for c in collections.collections]

    if settings.qdrant_collection not in collection_names:
        await _client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(
                size=settings.vector_size,
                distance=Distance.COSINE,
            ),
        )

        # Create payload indexes for efficient filtering
        for field_name, field_type in [
            ("user_id", PayloadSchemaType.KEYWORD),
            ("type", PayloadSchemaType.KEYWORD),
            ("tags", PayloadSchemaType.KEYWORD),
            ("timestamp", PayloadSchemaType.INTEGER),
        ]:
            await _client.create_payload_index(
                collection_name=settings.qdrant_collection,
                field_name=field_name,
                field_schema=field_type,
            )

    return _client


async def close_qdrant() -> None:
    """Close the Qdrant client."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None


def get_qdrant() -> AsyncQdrantClient:
    """Get the Qdrant client instance."""
    if _client is None:
        raise RuntimeError("Qdrant not initialized. Call init_qdrant() first.")
    return _client
