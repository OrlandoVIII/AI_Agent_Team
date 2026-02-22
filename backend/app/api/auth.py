from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
import jwt
import bcrypt
import os
from datetime import datetime, timedelta

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    token: str

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())

@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest):
    """Authenticate a user and return a signed JWT token."""
    SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    if not SECRET_KEY:
        raise HTTPException(status_code=500, detail="Server misconfiguration")

    # TODO: replace with real DB lookup when database is wired up
    # user = get_user_by_username(db, request.username)
    # if not user or not verify_password(request.password, user.hashed_password):
    #     raise HTTPException(status_code=401, detail="Invalid credentials")

    # Temporary stub — no hardcoded credentials, fails safely
    raise HTTPException(
        status_code=501,
        detail="Authentication not yet implemented. Database required."
    )