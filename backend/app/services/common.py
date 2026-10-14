from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import Base
from ..errors import NotFound
from ..models import AuditLog, Notification, User

M = TypeVar("M", bound=Base)


def get_or_404(db: Session, model: type[M], obj_id: int, label: str | None = None) -> M:
    obj = db.get(model, obj_id)
    if obj is None:
        raise NotFound(f"{label or model.__name__} not found")
    return obj


def audit(
    db: Session,
    actor: User | None,
    action: str,
    entity: str,
    entity_id: int | None = None,
    details: str = "",
) -> None:
    db.add(
        AuditLog(
            actor_id=actor.id if actor else None,
            action=action,
            entity=entity,
            entity_id=entity_id,
            details=details[:500],
        )
    )


def notify(
    db: Session,
    user_id: int,
    kind: str,
    title: str,
    message: str,
    ref_key: str | None = None,
) -> bool:
    """Queue an in-app notification. Returns False if one with the same ref_key exists."""
    if ref_key is not None:
        exists = db.scalar(
            select(Notification.id).where(
                Notification.user_id == user_id, Notification.ref_key == ref_key
            )
        )
        if exists:
            return False
    db.add(Notification(user_id=user_id, kind=kind, title=title, message=message, ref_key=ref_key))
    return True


def paginate_args(page: int, size: int) -> tuple[int, int]:
    page = max(page, 1)
    size = min(max(size, 1), 100)
    return page, size
