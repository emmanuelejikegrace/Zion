from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------- Database setup ----------
DATABASE_URL = "sqlite:///./Zion.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

Base = declarative_base()


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    text = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.now)


# Create the table if it doesn't exist
Base.metadata.create_all(bind=engine)


# ---------- Pydantic model (for input) ----------
class MessageIn(BaseModel):
    text: str


# ---------- Routes ----------
@app.get("/")
def home():
    return FileResponse("static/index.html")


@app.get("/messages")
def get_messages():
    db = SessionLocal()
    try:
        rows = db.query(Message).order_by(Message.id.asc()).all()
        return {
            "messages": [
                {
                    "id": r.id,
                    "text": r.text,
                    "time": r.created_at.strftime("%H:%M") if r.created_at else "",
                }
                for r in rows
            ]
        }
    finally:
        db.close()


@app.post("/messages")
def send_message(payload: MessageIn):
    db = SessionLocal()
    try:
        msg = Message(text=payload.text)
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return {
            "ok": True,
            "message": {
                "id": msg.id,
                "text": msg.text,
                "time": msg.created_at.strftime("%H:%M"),
            },
        }
    finally:
        db.close()