from fastapi import APIRouter
router = APIRouter()

@router.post("/login")
def login(username: str, password: str):
    # TODO: add real auth
    if username == "admin" and password == "1234":
        return {"token": "abc123"}
    return {"error": "invalid credentials"}
