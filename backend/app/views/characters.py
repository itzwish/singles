"""Character API — expose the public defaults to every visitor."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.character import Character
from app.schemas.character import CharacterOut

router = APIRouter()


class PublicCharacterOut(BaseModel):
    id: str
    name: str
    description: str | None
    system_prompt: str
    personality_profile: dict | None
    is_template: bool
    is_public: bool
    tags: str | None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


@router.get("/public", response_model=list[PublicCharacterOut])
async def list_public_characters(db: AsyncSession = Depends(get_db)):
    """Return the pre-seeded, publicly-listed default characters that everyone
    gets on sign-up. These are the *starter* characters - every new user's
    roster is copied from this list, so this endpoint is simply the canonical
    source of which characters exist out of the box."""
    result = await db.execute(
        select(Character)
        .where(Character.is_public.is_(True))
        .order_by(Character.name)
    )
    return list(result.scalars().all())
