"""Document ingestion engine — PDF/Markdown parsing and chunking."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import structlog
from pypdf import PdfReader

from kimiko.memory.semantic import SemanticMemory

logger = structlog.get_logger(__name__)


class DocumentEngine:
    """Handles document ingestion, parsing, chunking, and semantic indexing."""

    def __init__(
        self, 
        semantic_memory: Optional[SemanticMemory] = None,
        chunk_size: int = 500,
        chunk_overlap: int = 50
    ) -> None:
        self.semantic = semantic_memory or SemanticMemory()
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    async def ingest(self, path: str, user_id: str, tags: List[str] | None = None) -> Dict[str, Any]:
        """Ingest a document: extract, chunk, and index."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"Document not found at {path}")

        logger.info("document_ingestion_start", path=path, user_id=user_id)
        
        # 1. Extract text
        text = self._extract_text(path)
        if not text:
            return {"status": "error", "message": "No text extracted from document."}

        # 2. Chunk text
        chunks = self._chunk_text(text)
        logger.info("document_chunked", path=path, total_chunks=len(chunks))

        # 3. Index chunks in semantic memory
        doc_name = os.path.basename(path)
        tags = (tags or []) + ["document", doc_name]
        
        indexed_count = 0
        for i, chunk in enumerate(chunks):
            metadata = {
                "source": doc_name,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "path": path,
            }
            await self.semantic.index(
                text=chunk,
                user_id=user_id,
                tags=tags,
                memory_type="document",
                metadata=metadata,
                importance=0.8, # Documents are generally important
            )
            indexed_count += 1

        logger.info(
            "document_ingestion_complete", 
            path=path, 
            chunks_indexed=indexed_count
        )
        
        return {
            "status": "success", 
            "chunks_indexed": indexed_count,
            "document_name": doc_name
        }

    def _extract_text(self, path: str) -> str:
        """Extract text from PDF, Markdown, or Text files."""
        ext = os.path.splitext(path)[1].lower()
        
        if ext == ".pdf":
            return self._extract_pdf(path)
        elif ext in [".md", ".markdown", ".txt"]:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        else:
            logger.warning("unsupported_file_type", extension=ext)
            return ""

    def _extract_pdf(self, path: str) -> str:
        """Extract text from PDF using pypdf."""
        try:
            reader = PdfReader(path)
            text = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text.append(page_text)
            return "\n".join(text)
        except Exception as e:
            logger.error("pdf_extraction_failed", path=path, error=str(e))
            return ""

    def _chunk_text(self, text: str) -> List[str]:
        """Split text into overlapping chunks of a specific size (character-based approx)."""
        if not text:
            return []

        chunks = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = start + self.chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            
            # Move start forward but subtract overlap
            start += (self.chunk_size - self.chunk_overlap)
            
            # Prevent infinite loop if overlap >= chunk_size
            if self.chunk_size <= self.chunk_overlap:
                break

        return chunks
