from typing import Optional

from sqlalchemy.orm import Session

from app.database.models import User


def create_user(
    db: Session,
    *,
    email: str,
    password_hash: str,
    name: Optional[str] = None,
    business_name: Optional[str] = None,
    business_type: Optional[str] = None,
) -> User:
    user = User(
        email=email,
        password_hash=password_hash,
        name=name,
        business_name=business_name,
        business_type=business_type,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()
