from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from services.rag_service import answer_question
from models.tables import ChatHistory
from pydantic import BaseModel

router = APIRouter(prefix="/chat", tags=["RAG Chat"])

class ChatRequest(BaseModel):
    question: str

@router.post("/ask")
async def ask_question(request: ChatRequest, db: Session = Depends(get_db)):
    from fastapi.concurrency import run_in_threadpool

    # Get answer from RAG pipeline
    answer = await run_in_threadpool(
        answer_question, db, request.question
    )

    # Save to chat history
    history_entry = ChatHistory(
        question=request.question,
        answer=answer
    )
    db.add(history_entry)
    db.commit()

    return {
        "question": request.question,
        "answer": answer
    }

@router.get("/history")
def get_chat_history(db: Session = Depends(get_db), limit: int = 20):
    from models.tables import ChatHistory
    history = db.query(ChatHistory).order_by(
        ChatHistory.timestamp.desc()
    ).limit(limit).all()
    return [
        {
            "id": h.id,
            "timestamp": str(h.timestamp),
            "question": h.question,
            "answer": h.answer
        }
        for h in history
    ]