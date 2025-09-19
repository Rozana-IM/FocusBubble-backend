# main.py
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import asyncio
import os
from typing import List

from focusbubble_backend.app.database import SessionLocal, engine, Base
from focusbubble_backend.app import models, schemas, crud, auth
from focusbubble_backend.app.background import expiry_loop

# Create tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="FocusBubble Backend API",
    description="Backend service for FocusBubble app (sessions, schedules, blocking apps).",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 🔒 You can restrict later to specific frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency: get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Startup background task
@app.on_event("startup")
async def startup_event():
    env_cid = os.getenv("GOOGLE_CLIENT_ID")
    if env_cid:
        auth.GOOGLE_CLIENT_ID = env_cid
    asyncio.create_task(expiry_loop(30))  # run every 30s

# Root endpoint
@app.get("/")
def root():
    return {"message": "Welcome to FocusBubble API"}

# Health check
@app.get("/health")
def health():
    return {"ok": True, "time": datetime.utcnow().isoformat()}

# AUTH
@app.post("/auth/google", response_model=schemas.UserOut)
def google_sign_in(token_in: schemas.TokenIn, db: Session = Depends(get_db)):
    payload = auth.verify_google_token(token_in.id_token)
    email = payload.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Google token missing email")
    user = crud.get_or_create_user(
        db,
        email=email,
        name=payload.get("name"),
        picture=payload.get("picture")
    )
    return user

# USERS
@app.post("/users", response_model=schemas.UserOut)
def create_user(user_in: schemas.UserCreate, db: Session = Depends(get_db)):
    return crud.get_or_create_user(db, email=user_in.email, name=user_in.name, picture=user_in.picture)

@app.get("/users/{user_id}", response_model=schemas.UserOut)
def get_user(user_id: int, db: Session = Depends(get_db)):
    u = crud.get_user(db, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return u

# SCHEDULES
@app.post("/users/{user_id}/schedules", response_model=schemas.ScheduleOut)
def create_schedule_for_user(user_id: int, s_in: schemas.ScheduleCreate, db: Session = Depends(get_db)):
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    s = crud.create_schedule(db, user_id, s_in)
    return {
        "id": s.id,
        "label": s.label,
        "duration_minutes": s.duration_minutes,
        "apps": s.apps_csv.split(",") if s.apps_csv else [],
        "is_active": s.is_active,
        "created_at": s.created_at
    }

@app.get("/users/{user_id}/schedules", response_model=List[schemas.ScheduleOut])
def list_schedules_for_user(user_id: int, db: Session = Depends(get_db)):
    return crud.list_schedules(db, user_id)

@app.delete("/users/{user_id}/schedules/{schedule_id}")
def delete_schedule_for_user(user_id: int, schedule_id: int, db: Session = Depends(get_db)):
    ok = crud.delete_schedule(db, user_id, schedule_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"ok": True}

# SESSIONS
@app.post("/users/{user_id}/sessions", response_model=schemas.SessionOut)
def start_session_for_user(user_id: int, body: schemas.SessionCreate, db: Session = Depends(get_db)):
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    session = crud.start_session(db, user_id, body.schedule_id, body.duration_minutes)

    # If schedule provided, create blocked apps
    if body.schedule_id:
        sched = db.query(models.Schedule).filter(models.Schedule.id == body.schedule_id).first()
        if sched and sched.apps_csv:
            crud.create_blocked_apps_for_session(db, user_id, sched.apps_csv.split(","), body.duration_minutes)

    return session

@app.post("/sessions/{session_id}/pause", response_model=schemas.SessionOut)
def pause_session(session_id: int, db: Session = Depends(get_db)):
    s = crud.pause_session(db, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return s

@app.post("/sessions/{session_id}/resume", response_model=schemas.SessionOut)
def resume_session(session_id: int, db: Session = Depends(get_db)):
    s = crud.resume_session(db, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return s

@app.post("/sessions/{session_id}/stop", response_model=schemas.SessionOut)
def stop_session(session_id: int, db: Session = Depends(get_db)):
    s = crud.stop_session(db, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    # deactivate user’s blocked apps
    now = datetime.utcnow()
    blocks = db.query(models.BlockedApp).filter(
        models.BlockedApp.user_id == s.user_id,
        models.BlockedApp.is_active == True
    ).all()
    for b in blocks:
        b.is_active = False
        b.end_time = now
    db.commit()
    return s

@app.get("/users/{user_id}/sessions/active", response_model=List[schemas.SessionOut])
def list_active_sessions_for_user(user_id: int, db: Session = Depends(get_db)):
    return crud.list_active_sessions(db, user_id)

# BLOCKED APPS
@app.post("/users/{user_id}/blocks", response_model=List[schemas.BlockedAppOut])
def create_blocks(user_id: int, body: List[schemas.BlockedAppCreate], db: Session = Depends(get_db)):
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    created = []
    for b in body:
        start = b.start_time or datetime.utcnow()
        end = b.end_time or (start + timedelta(minutes=25))
        row = models.BlockedApp(
            user_id=user_id,
            package_name=b.package_name,
            app_name=b.app_name,
            start_time=start,
            end_time=end,
            is_active=True
        )
        db.add(row)
        created.append(row)

    db.commit()
    for c in created:
        db.refresh(c)
    return created

@app.get("/users/{user_id}/blocks", response_model=List[schemas.BlockedAppOut])
def get_active_blocks(user_id: int, db: Session = Depends(get_db)):
    return crud.list_active_blocked_apps(db, user_id)

@app.post("/refresh_blocks")
def refresh_blocks(db: Session = Depends(get_db)):
    expired = crud.deactivate_expired_blocks(db)
    return {"expired": len(expired)}
