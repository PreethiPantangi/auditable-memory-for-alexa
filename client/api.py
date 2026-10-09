from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from client.orchestrator import handle_user_message
import logging
from fastapi.middleware.cors import CORSMiddleware
from .memory_api import router as memory_router

app = FastAPI(title="Auditable Memory API")
app.include_router(memory_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://auditable-memory-interface.onrender.com/"
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


class ChatRequest(BaseModel):
    user_id: str
    message: str

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/chat")
async def chat(request: ChatRequest):
    try:
        result = await handle_user_message(user_id=request.user_id,message=request.message)
        return result    
    except Exception:
        logging.exception("Chat request failed")
        raise HTTPException(status_code=500,detail="Unable to process request")