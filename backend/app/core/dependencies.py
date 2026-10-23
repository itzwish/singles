"""FastAPI dependency injection"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.identity import AuthenticatedIdentity, resolve_identity
from app.models.user import User

security_scheme = HTTPBearer(auto_error=False)


async def get_current_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> AuthenticatedIdentity:
    """Resolve the caller from their bearer credential.

    Accepts a Clerk session token or a legacy access token, depending on
    ``AUTH_MODE``. Raises 401 when the credential is missing or not trusted.
    """
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in first")

    identity = await resolve_identity(credentials.credentials, db)
    if identity is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired or is invalid")

    return identity


async def get_current_user(
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> User:
    """Resolve the current user. Raises 401 when not authenticated."""
    return identity.user


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Optional authentication — returns None instead of raising when signed out."""
    if not credentials:
        return None
    identity = await resolve_identity(credentials.credentials, db)
    if identity is None:
        return None
    return identity.user


async def get_admin_user(
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> User:
    """Require administrator privileges.

    Admin status comes from the database row *or* from the Clerk
    ``publicMetadata.role == "admin"`` claim, so a Clerk admin works even
    before the webhook has synced the flag.
    """
    if not identity.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")
    return identity.user


def check_quota(feature: str):
    """Factory enforcing a per-day quota. Usage: Depends(check_quota("chat"))"""

    async def checker(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        from datetime import datetime, timezone

        from app.core.config import settings
        from app.models.payment import UsageLog
        from sqlalchemy import func

        if current_user.membership_tier == "vip":
            return current_user

        today = datetime.now(timezone.utc).date()

        if feature == "chat":
            limit = (
                settings.premium_daily_messages
                if current_user.membership_tier == "premium"
                else settings.free_daily_messages
            )
        else:
            limit = 10

        count_result = await db.execute(
            select(func.count()).select_from(UsageLog).where(
                UsageLog.user_id == current_user.id,
                UsageLog.endpoint == feature,
                func.date(UsageLog.created_at) == today,
            )
        )
        count = count_result.scalar() or 0

        if count >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"You have used today's {feature} quota ({limit}/day). "
                    "Upgrade your membership for more."
                ),
            )

        return current_user

    return checker
