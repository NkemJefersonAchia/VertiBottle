"""Login / identity endpoints. Any of the five seeded demo users can log in
here; the frontend also uses this as its role switcher."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..database import get_db
from ..models import User
from ..schemas import LoginRequest, LoginResponse, UserOut
from ..security import create_token, current_user, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username))
    if user is None or not user.active or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid username or password")
    token = create_token(db, user)
    audit.log(db, user.username, "login", f"{user.role.value} logged in")
    db.commit()
    return LoginResponse(token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user
