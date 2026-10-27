import secrets
from fastapi import FastAPI, HTTPException, Request, Response, Cookie
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
DATABASE_URL = "sqlite:///./owl.db"

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


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    text = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)


# ← NEW: the sessions table
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


class UserIn(BaseModel):
    username: str
    password: str


# ← NEW: how long a login lasts (7 days)
SESSION_LIFETIME = timedelta(days=7)
COOKIE_NAME = "owl_session"


# ← NEW: helper — create a session row, return the token
def create_session(db, user_id: int) -> str:
    token = secrets.token_urlsafe(32)          # 32 random bytes → safe, unguessable
    now = datetime.now()
    session = Session(
        token=token,
        user_id=user_id,
        created_at=now,
        expires_at=now + SESSION_LIFETIME,
    )
    db.add(session)
    db.commit()
    return token


# ← NEW: helper — look up the user from the cookie, or return None
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
        user = db.query(User).filter(User.id == session.user_id).first()
        return user
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

        # ← NEW: attach the username to each message so the frontend can show "who"
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
                "username": username,   # ← NEW
            })

        return {"messages": result}
    finally:
        db.close()


@app.post("/messages")
def send_message(payload: MessageIn, request: Request):
    user = get_current_user(request)   # ← NEW: require login
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")

    db = SessionLocal()
    try:
        msg = Message(text=payload.text, user_id=user.id)   # ← NEW: attach user
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


@app.post("/signup")
def signup(payload: UserIn):
    db = SessionLocal()
    try:
        if len(payload.username) < 3:
            raise HTTPException(status_code=400, detail="Username too short")
        if len(payload.password) < 6:
            raise HTTPException(status_code=400, detail="Password too short")

        existing = db.query(User).filter(User.username == payload.username).first()
        if existing:
            raise HTTPException(status_code=400, detail="Username already taken")

        hashed = pwd_context.hash(payload.password)
        user = User(username=payload.username, password_hash=hashed)
        db.add(user)
        db.commit()
        db.refresh(user)

        return {"ok": True, "user": {"id": user.id, "username": user.username}}
    finally:
        db.close()


@app.post("/login")
def login(payload: UserIn, response: Response):    # ← NEW: need Response to set cookie
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == payload.username).first()
        if not user or not pwd_context.verify(payload.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid username or password")

        # ← NEW: create the session and set the cookie
        token = create_session(db, user.id)
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            httponly=True,           # JS can't read it — safer against XSS
            samesite="lax",          # basic CSRF protection
            max_age=7 * 24 * 3600,   # 7 days, matches SESSION_LIFETIME
        )

        return {"ok": True, "user": {"id": user.id, "username": user.username}}
    finally:
        db.close()


# ← NEW: logout — delete session + clear cookie
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