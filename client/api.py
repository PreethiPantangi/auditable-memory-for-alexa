from fastapi import FastAPI
from pydantic import BaseModel
from client.orchestrator import handle_user_message

app = FastAPI(title="Auditable Memory API")

class ChatRequest(BaseModel):
    user_id: str
    message: str

@app.post("/chat")
async def chat(request: ChatRequest):
    result = await handle_user_message(user_id=request.user_id,message=request.message)
    return result    