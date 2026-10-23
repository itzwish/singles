"""Long-term memory API"""

import uuid

from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.security import decrypt_api_key
from app.core.database import get_db
from app.models.memory import LongTermMemory
from app.models.user import User
from app.services.memory_service import consolidate_memories


class MemoryUpdate(BaseModel):
    content: str | None = None
    importance: int | None = None

router = APIRouter()


@router.get("")
async def list_memories(
    character_id: uuid.UUID | None = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
):
    """List the user's long-term memories"""
    stmt = (
        select(LongTermMemory)
        .where(LongTermMemory.user_id == current_user.id)
        .order_by(LongTermMemory.importance.desc(), LongTermMemory.created_at.desc())
        .limit(limit)
    )
    if character_id:
        stmt = stmt.where(LongTermMemory.character_id == character_id)

    result = await db.execute(stmt)
    memories = result.scalars().all()

    return [
        {
            "id": str(m.id),
            "character_id": str(m.character_id),
            "content": m.content,
            "importance": m.importance,
            "created_at": m.created_at.isoformat(),
        }
        for m in memories
    ]


@router.post("/consolidate")
async def trigger_consolidation(
    character_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger consolidation: fold short-term chat into long-term memory"""
    api_key = decrypt_api_key(current_user.api_key_encrypted) if current_user.api_key_encrypted else None
    result = await consolidate_memories(
        str(character_id), str(current_user.id), db, api_key, current_user.api_model
    )
    return result


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_memory(
    character_id: uuid.UUID,
    content: str,
    importance: int = 3,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
):
    """Manually add a long-term memory"""
    if importance < 1 or importance > 5:
        raise HTTPException(status_code=400, detail="Importance must be between 1 and 5")

    memory = LongTermMemory(
        user_id=current_user.id,
        character_id=character_id,
        content=content,
        importance=importance,
    )
    db.add(memory)
    await db.flush()
    await db.refresh(memory)

    return {
        "id": str(memory.id),
        "content": memory.content,
        "importance": memory.importance,
    }


@router.patch("/{memory_id}")
async def update_memory(
    memory_id: uuid.UUID,
    data: MemoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
):
    """Edit a memory's content or importance"""
    result = await db.execute(select(LongTermMemory).where(LongTermMemory.id == memory_id))
    memory = result.scalar_one_or_none()
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    if memory.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed to edit this memory")

    if data.content is not None:
        memory.content = data.content
    if data.importance is not None:
        if data.importance < 1 or data.importance > 5:
            raise HTTPException(status_code=400, detail="Importance must be between 1 and 5")
        memory.importance = data.importance

    await db.flush()
    await db.refresh(memory)
    return {
        "id": str(memory.id),
        "content": memory.content,
        "importance": memory.importance,
    }


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
):
    """Delete a memory"""
    result = await db.execute(
        select(LongTermMemory).where(LongTermMemory.id == memory_id)
    )
    memory = result.scalar_one_or_none()
    if not memory:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    if memory.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to delete this memory")

    await db.delete(memory)
    await db.flush()
