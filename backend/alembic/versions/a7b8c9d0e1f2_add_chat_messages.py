"""add chat_messages audit table

Revision ID: a7b8c9d0e1f2
Revises: f6g7h8i9j0k1
Create Date: 2026-05-20 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f6g7h8i9j0k1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'chat_messages',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('character_id', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column(
            'timestamp',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_chat_messages_user_id', 'chat_messages', ['user_id'])
    op.create_index('ix_chat_messages_character_id', 'chat_messages', ['character_id'])
    op.create_index('ix_chat_messages_timestamp', 'chat_messages', ['timestamp'])
    op.create_index(
        'ix_chat_messages_user_timestamp',
        'chat_messages',
        ['user_id', 'timestamp'],
    )


def downgrade() -> None:
    op.drop_index('ix_chat_messages_user_timestamp', table_name='chat_messages')
    op.drop_index('ix_chat_messages_timestamp', table_name='chat_messages')
    op.drop_index('ix_chat_messages_character_id', table_name='chat_messages')
    op.drop_index('ix_chat_messages_user_id', table_name='chat_messages')
    op.drop_table('chat_messages')