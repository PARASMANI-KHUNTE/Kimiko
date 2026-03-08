"""Semantic memory — Qdrant vector store with proper schema and payload indexes.

Collection: memories
Vector size: 768 (nomic-embed-text)
Payload indexes: user_id, type, tags, timestamp
"""

from __future__ import annotations

import time
import uuid

import structlog
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
)

from kimiko.config import get_settings
from kimiko.core.observability import VECTOR_SEARCH_DURATION
from kimiko.db.qdrant import get_qdrant
from kimiko.services.embedding import get_embedding_service

logger = structlog.get_logger(__name__)


class SemanticMemory:
    """Qdrant-backed vector memory with embedding generation."""

    async def index(
        self,
        text: str,
        user_id: str,
        tags: list[str] | None = None,
        memory_type: str = "general",
        importance: float = 0.5,
        metadata: dict | None = None,
        request_id: str | None = None,
    ) -> str:
        """Embed text and store in Qdrant. Returns the point ID."""
        settings = get_settings()
        embedding_service = get_embedding_service()
        qdrant = get_qdrant()

        # Generate embedding
        vector = await embedding_service.embed(text)

        # Create point
        point_id = str(uuid.uuid4())
        payload = {
            "user_id": user_id,
            "text": text,
            "tags": tags or [],
            "type": memory_type,
            "importance": importance,
            "timestamp": int(time.time()),
            **(metadata or {}),
        }

        await qdrant.upsert(
            collection_name=settings.qdrant_collection,
            points=[
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload,
                )
            ],
        )

        logger.info(
            "semantic_memory_indexed",
            point_id=point_id,
            user_id=user_id,
            memory_type=memory_type,
            request_id=request_id,
        )
        return point_id

    async def search(
        self,
        query: str,
        user_id: str | None = None,
        top_k: int = 5,
        score_threshold: float = 0.3,
        request_id: str | None = None,
    ) -> list[dict]:
        """Semantic search — returns ranked results with scores.

        Returns list of dicts with: text, score, metadata (tags, type, timestamp).
        """
        settings = get_settings()
        embedding_service = get_embedding_service()
        qdrant = get_qdrant()

        # Generate query embedding
        query_vector = await embedding_service.embed(query)

        # Build filter
        search_filter = None
        if user_id:
            search_filter = Filter(
                must=[
                    FieldCondition(
                        key="user_id",
                        match=MatchValue(value=user_id),
                    )
                ]
            )

        # Search
        with VECTOR_SEARCH_DURATION.time():
            results = await qdrant.query_points(
                collection_name=settings.qdrant_collection,
                query=query_vector,
                query_filter=search_filter,
                limit=top_k,
                score_threshold=score_threshold,
            )

        # Format results
        formatted = []
        for hit in results.points:
            formatted.append({
                "text": hit.payload.get("text", ""),
                "score": hit.score,
                "metadata": {
                    "tags": hit.payload.get("tags", []),
                    "type": hit.payload.get("type", "general"),
                    "timestamp": hit.payload.get("timestamp", 0),
                    "user_id": hit.payload.get("user_id", ""),
                    "importance": hit.payload.get("importance", 0.5),
                },
                "point_id": hit.id,
            })

        logger.debug(
            "semantic_search_complete",
            query_preview=query[:50],
            results_count=len(formatted),
            top_score=formatted[0]["score"] if formatted else 0,
            request_id=request_id,
        )

        return formatted

    async def delete(self, point_id: str) -> None:
        """Delete a vector point by ID."""
        settings = get_settings()
        qdrant = get_qdrant()
        await qdrant.delete(
            collection_name=settings.qdrant_collection,
            points_selector=[point_id],
        )
        logger.info("semantic_memory_deleted", point_id=point_id)
