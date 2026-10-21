from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from datetime import datetime

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------- Data model ----------
class MessageIn(BaseModel):
    text: str


# ---------- In-memory storage (Season 1 only!) ----------
messages = []


# ---------- Routes ----------
@app.get("/")
def home():
    return FileResponse("static/index.html")


@app.get("/messages")
def get_messages():
    return {"messages": messages}


@app.post("/messages")
def send_message(payload: MessageIn):
    new_message = {
        "id": len(messages) + 1,
        "text": payload.text,
        "time": datetime.now().strftime("%H:%M"),
    }
    messages.append(new_message)
    return {"ok": True, "message": new_message}