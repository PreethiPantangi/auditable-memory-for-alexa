from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from client.orchestrator import handle_user_message

import logging

app = FastAPI(title="Auditable Memory API")

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