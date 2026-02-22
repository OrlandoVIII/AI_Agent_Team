from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import jwt
import os
from datetime import datetime, timedelta

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    token: str

@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest):
    """Authenticate a user and return a JWT token."""
    # In production this would check against the database
    # with hashed passwords (bcrypt)
    SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    if not SECRET_KEY:
        raise HTTPException(status_code=500, detail="Server misconfiguration")

    # Placeholder user check — replace with DB lookup
    if request.username != "admin":
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = jwt.encode(
        {"user": request.username, "exp": datetime.utcnow() + timedelta(hours=1)},
        SECRET_KEY,
        algorithm="HS256"
    )
    return LoginResponse(token=token)