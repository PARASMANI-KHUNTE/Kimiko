"""Document endpoint — POST /v1/documents/upload."""

from __future__ import annotations

import os
import shutil
import tempfile
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from kimiko.api.deps import get_orchestrator
from kimiko.api.middleware.auth import verify_api_key
from kimiko.core.orchestrator import RequestOrchestrator
from kimiko.models.schemas import DocumentIngestResponse

router = APIRouter(prefix="/documents", tags=["documents"])

logger = structlog.get_logger(__name__)


@router.post("/upload", response_model=DocumentIngestResponse)
async def upload_document(
    user_id: str = Form(...),
    file: UploadFile = File(...),
    tags: Optional[str] = Form(None),  # Comma-separated tags
    orchestrator: RequestOrchestrator = Depends(get_orchestrator),
    _auth: dict = Depends(verify_api_key),
) -> DocumentIngestResponse:
    """Upload and ingest a document (PDF, Markdown, Text).
    
    The document will be chunked and indexed in semantic memory.
    """
    logger.info("document_upload_received", filename=file.filename, user_id=user_id)
    
    # Check extension
    ext = os.path.splitext(file.filename)[1].lower() if file.filename else ""
    if ext not in [".pdf", ".md", ".markdown", ".txt"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {ext}. Supported: PDF, MD, TXT."
        )

    # Save to temp file
    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, file.filename or "upload")
    
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Parse tags
        tag_list = [t.strip() for t in tags.split(",")] if tags else []
        
        # Ingest
        result = await orchestrator.document_engine.ingest(
            path=temp_path,
            user_id=user_id,
            tags=tag_list
        )
        
        if result.get("status") == "error":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("message")
            )
            
        return DocumentIngestResponse(
            status="success",
            document_name=result.get("document_name", "unknown"),
            chunks_indexed=result.get("chunks_indexed", 0)
        )
        
    except Exception as e:
        logger.error("document_upload_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload failed: {str(e)}"
        )
    finally:
        # Cleanup
        if os.path.exists(temp_path):
            os.remove(temp_path)
