"""Database bootstrap helpers — default user seeding and user-ID normalisation.

The CLI and the web dashboard address the local user as ``default`` rather than
by UUID, while every memory/fact store parses user IDs as UUIDs. Resolving that
mismatch in one place keeps the API from raising ``ValueError`` on the friendly
form and guarantees facts are always attributed to a real ``users`` row.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# Friendly username used by the CLI, the web UI, and ``GET /v1/memory/facts``.
DEFAULT_USERNAME = "default"

# Deterministic ID for the seeded local user. Deliberately distinct from
# ``OS_USER_ID`` (00000000-0000-0000-0000-000000000001), which selects the
# experimental OS-agent path.
DEFAULT_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


def is_uuid(value: str | None) -> bool:
    """Return ``True`` when ``value`` can be parsed as a UUID."""
    if not value:
        return False
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def resolve_user_id(user_id: str | None) -> str:
    """Return a UUID string that is safe for persistence.

    Clients may omit ``user_id`` or send the friendly name ``default``. Both map
    to the seeded local user; any other non-UUID value also falls back so a
    typo cannot turn a chat request into a 500.
    """
    if user_id:
        if is_uuid(user_id):
            return str(uuid.UUID(str(user_id)))
        if user_id != DEFAULT_USERNAME:
            logger.warning("unknown_user_id_defaulted", user_id=user_id)
    return str(DEFAULT_USER_ID)


async def ensure_default_user(session: AsyncSession) -> None:
    """Insert the local default user when it is missing (idempotent)."""
    from kimiko.models.database import User

    existing = await session.scalar(select(User.id).where(User.id == DEFAULT_USER_ID))
    if existing is not None:
        return

    session.add(
        User(
            id=DEFAULT_USER_ID,
            username=DEFAULT_USERNAME,
            display_name="Local User",
        )
    )
    try:
        await session.commit()
        logger.info("default_user_seeded", user_id=str(DEFAULT_USER_ID))
    except IntegrityError:
        # Another process won the race; the row exists either way.
        await session.rollback()
