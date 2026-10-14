from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from ..models import Role, User
from ..schemas import LoginIn, Message, PasswordChange, ProfileUpdate, RegisterIn, TokenOut, UserOut
from ..security import DB, CurrentUser, create_access_token, hash_password, verify_password
from ..services.common import audit, notify
from ..services.members import create_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut, status_code=201)
def register(data: RegisterIn, db: DB) -> TokenOut:
    user = create_user(db, **data.model_dump(), role=Role.MEMBER)
    notify(
        db,
        user.id,
        "welcome",
        "Welcome to Smart Library",
        f"Your member code is {user.member_code}. Show it at the desk to borrow books.",
    )
    audit(db, user, "member.register", "user", user.id, user.email)
    db.commit()
    return TokenOut(access_token=create_access_token(user), user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, db: DB) -> TokenOut:
    user = db.scalar(select(User).where(func.lower(User.email) == data.email.lower()))
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated")
    return TokenOut(access_token=create_access_token(user), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user


@router.put("/me", response_model=UserOut)
def update_profile(data: ProfileUpdate, user: CurrentUser, db: DB) -> User:
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(user, key, value)
    db.commit()
    return user


@router.post("/change-password", response_model=Message)
def change_password(data: PasswordChange, user: CurrentUser, db: DB) -> Message:
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    user.password_hash = hash_password(data.new_password)
    audit(db, user, "user.password", "user", user.id)
    db.commit()
    return Message(detail="Password updated")
