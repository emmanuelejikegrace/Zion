import secrets
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker
from passlib.context import CryptContext

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------- Database setup ----------
DATABASE_URL = "sqlite:///./zion.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


# ---------- Password hashing ----------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------- Models ----------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    # ← NEW
    security_question = Column(String, nullable=True)
    security_answer_hash = Column(String, nullable=True)


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    text = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)


class Session(Base):
    __tablename__ = "sessions"

    token = Column(String, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    expires_at = Column(DateTime, nullable=False)


Base.metadata.create_all(bind=engine)


# ---------- Pydantic models ----------
class MessageIn(BaseModel):
    text: str


# ← NEW: signup now takes more fields
class SignupIn(BaseModel):
    username: str
    password: str
    confirm_password: str
    security_question: str
    security_answer: str


# ← NEW: login is its own model
class LoginIn(BaseModel):
    username: str
    password: str


# ← NEW: reset password model
class ResetIn(BaseModel):
    username: str
    security_answer: str
    new_password: str


SESSION_LIFETIME = timedelta(days=7)
COOKIE_NAME = "Zion_session"


# ---------- Helpers ----------
def create_session(db, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now()
    db.add(Session(
        token=token,
        user_id=user_id,
        created_at=now,
        expires_at=now + SESSION_LIFETIME,
    ))
    db.commit()
    return token


def get_current_user(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None

    db = SessionLocal()
    try:
        session = db.query(Session).filter(Session.token == token).first()
        if not session:
            return None
        if session.expires_at < datetime.now():
            db.delete(session)
            db.commit()
            return None
        return db.query(User).filter(User.id == session.user_id).first()
    finally:
        db.close()


# ---------- Routes ----------
@app.get("/")
def home():
    return FileResponse("static/index.html")


@app.get("/messages")
def get_messages():
    db = SessionLocal()
    try:
        rows = db.query(Message).order_by(Message.id.asc()).all()
        result = []
        for r in rows:
            username = None
            if r.user_id is not None:
                u = db.query(User).filter(User.id == r.user_id).first()
                if u:
                    username = u.username
            result.append({
                "id": r.id,
                "text": r.text,
                "time": r.created_at.strftime("%H:%M") if r.created_at else "",
                "user_id": r.user_id,
                "username": username,
            })
        return {"messages": result}
    finally:
        db.close()


@app.post("/messages")
def send_message(payload: MessageIn, request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")

    db = SessionLocal()
    try:
        msg = Message(text=payload.text, user_id=user.id)
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return {
            "ok": True,
            "message": {
                "id": msg.id,
                "text": msg.text,
                "time": msg.created_at.strftime("%H:%M"),
                "user_id": msg.user_id,
                "username": user.username,
            },
        }
    finally:
        db.close()


# ---------- NEW: signup (extended) ----------
@app.post("/signup")
def signup(payload: SignupIn):
    db = SessionLocal()
    try:
        # Validation
        if len(payload.username) < 3:
            raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
        if len(payload.password) < 6:
            raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
        if payload.password != payload.confirm_password:
            raise HTTPException(status_code=400, detail="Passwords do not match")
        if not payload.security_question.strip():
            raise HTTPException(status_code=400, detail="Security question is required")
        if len(payload.security_answer.strip()) < 2:
            raise HTTPException(status_code=400, detail="Security answer is too short")

        # Duplicate check
        existing = db.query(User).filter(User.username == payload.username).first()
        if existing:
            raise HTTPException(status_code=400, detail="Username already taken")

        # Hash password AND answer (case-sensitive — no .lower()!)
        password_hash = pwd_context.hash(payload.password)
        answer_hash = pwd_context.hash(payload.security_answer)

        user = User(
            username=payload.username,
            password_hash=password_hash,
            security_question=payload.security_question,
            security_answer_hash=answer_hash,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        return {"ok": True, "user": {"id": user.id, "username": user.username}}
    finally:
        db.close()


# ---------- NEW: get the security question for a user ----------
@app.get("/security-question")
def get_security_question(username: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user or not user.security_question:
            raise HTTPException(status_code=404, detail="User not found")
        return {"question": user.security_question}
    finally:
        db.close()


# ---------- NEW: reset password using the security answer ----------
@app.post("/reset-password")
def reset_password(payload: ResetIn):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == payload.username).first()
        if not user or not user.security_answer_hash:
            raise HTTPException(status_code=400, detail="Invalid username or answer")

        if len(payload.new_password) < 6:
            raise HTTPException(status_code=400, detail="New password must be at least 6 characters")

        # Verify the answer (case-sensitive)
        if not pwd_context.verify(payload.security_answer, user.security_answer_hash):
            raise HTTPException(status_code=400, detail="Invalid username or answer")

        # Set new password, invalidate all existing sessions for that user
        user.password_hash = pwd_context.hash(payload.new_password)
        db.query(Session).filter(Session.user_id == user.id).delete()
        db.commit()

        return {"ok": True}
    finally:
        db.close()


# ---------- Login ----------
@app.post("/login")
def login(payload: LoginIn, response: Response):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == payload.username).first()
        if not user or not pwd_context.verify(payload.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid username or password")

        token = create_session(db, user.id)
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            httponly=True,
            samesite="lax",
            max_age=7 * 24 * 3600,
        )
        return {"ok": True, "user": {"id": user.id, "username": user.username}}
    finally:
        db.close()


@app.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        db = SessionLocal()
        try:
            db.query(Session).filter(Session.token == token).delete()
            db.commit()
        finally:
            db.close()

    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@app.get("/me")
def me(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    return {"user": {"id": user.id, "username": user.username}}