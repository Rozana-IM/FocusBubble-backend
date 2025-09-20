import os
import asyncio
from datetime import datetime, timedelta
from typing import List

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from app.database import SessionLocal, engine, Base
from app import models, schemas, crud, auth
from app.background import expiry_loop
from pydantic import BaseModel as PydanticBaseModel

# ----------------------
# Load .env at the very start
# ----------------------
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

# ----------------------
# DB setup
# ----------------------
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="FocusBubble Backend API",
    description="Backend service for FocusBubble app (sessions, schedules, blocking apps).",
    version="1.0.0",
)

# ----------------------
# CORS
# ----------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://your-frontend-domain.com",
        "https://5c51e96c9247.ngrok-free.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------
# DB Dependency
# ----------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ----------------------
# Startup task
# ----------------------
@app.on_event("startup")
async def startup_event():
    env_cid = os.getenv("GOOGLE_CLIENT_ID")
    if env_cid:
        print(f"✅ Google Client ID loaded: {env_cid}")
    else:
        print("⚠️ GOOGLE_CLIENT_ID not set in .env")

    asyncio.create_task(expiry_loop(30))  # background task every 30s

# ----------------------
# Root & Health
# ----------------------
@app.get("/")
def root():
    return {"message": "Welcome to FocusBubble API"}

@app.get("/health")
def health():
    return {"ok": True, "time": datetime.utcnow().isoformat()}

# ----------------------
# JWT + Google Auth
# ----------------------
class TokenIn(PydanticBaseModel):
    id_token: str

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = auth.decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    return payload

@app.post("/auth/google")
def google_sign_in(token_in: TokenIn, db: Session = Depends(get_db)):
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

    access_token = auth.create_access_token({"sub": email})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "picture": user.picture
        }
    }
