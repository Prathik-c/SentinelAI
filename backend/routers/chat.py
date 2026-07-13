"""
SentinelAI — Chat Router (RAG Q&A)

Uses the new async RAG service with intent-aware retrieval.
Includes timeout handling, proper error messages, and chat history pagination.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import LLM_TIMEOUT_SECONDS
from database import get_db

router = APIRouter(prefix="/chat", tags=["RAG Chat"])


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


@router.post("/ask")
async def ask_question(request: ChatRequest, db: Session = Depends(get_db)):
    """
    Answers a natural language question about the system using the
    intent-aware RAG pipeline. Returns immediately on LLM timeout with
    a fallback message.
    """
    from services.rag_service import answer_question
    from services.intent_classifier import classify

    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        # Intent classification (instant)
        intent = classify(question)

        # RAG answer (async, timeout-safe)
        answer = await asyncio.wait_for(
            answer_question(db, question),
            timeout=float(LLM_TIMEOUT_SECONDS + 10),  # Extra buffer beyond LLM timeout
        )

    except asyncio.TimeoutError:
        logger.warning(f"Chat timeout | question='{question[:60]}'")
        answer = (
            "⚠️ Response timed out. The local AI model may be loading. "
            "Please try again in a moment."
        )
        intent = None

    except Exception as exc:
        logger.error(f"POST /chat/ask error: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Failed to process your question. Check that Ollama is running."
        )

    # Save to chat history (only on success)
    try:
        from models.tables import ChatHistory
        entry = ChatHistory(
            question = question,
            answer   = answer,
            intent   = str(intent) if intent else None,
        )
        db.add(entry)
        db.commit()
    except Exception as exc:
        logger.warning(f"Failed to save chat history: {exc}")
        # Don't fail the response just because history save failed

    return {
        "question": question,
        "answer":   answer,
        "intent":   str(intent) if intent else "general",
    }


@router.get("/history")
def get_chat_history(
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    skip:  int = Query(default=0,  ge=0),
):
    """Returns paginated chat history, most recent first."""
    from models.tables import ChatHistory

    try:
        history = (
            db.query(ChatHistory)
            .order_by(ChatHistory.timestamp.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return [
            {
                "id":        h.id,
                "timestamp": str(h.timestamp),
                "question":  h.question,
                "answer":    h.answer,
                "intent":    h.intent,
            }
            for h in history
        ]
    except Exception as exc:
        logger.error(f"GET /chat/history error: {exc}")
        raise HTTPException(status_code=500, detail="Failed to retrieve chat history.")