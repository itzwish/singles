"""rename chat_messages.timestamp to created_at

Renames the column and the matching indexes, and moves the default from a
server-side func.now() to a Python-side UTC default so the value is populated
identically on SQLite and Postgres.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-05-22 10:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index('ix_chat_messages_user_timestamp', table_name='chat_messages')
    op.drop_index('ix_chat_messages_timestamp', table_name='chat_messages')

    # SQLite has no ALTER COLUMN, so batch mode is required there; on Postgres
    # it compiles down to a plain ALTER TABLE.
    with op.batch_alter_table('chat_messages', schema=None) as batch_op:
        batch_op.alter_column(
            'timestamp',
            new_column_name='created_at',
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            existing_server_default=sa.func.now(),
            server_default=None,
        )

    op.create_index('ix_chat_messages_created_at', 'chat_messages', ['created_at'])
    op.create_index(
        'ix_chat_messages_user_created_at',
        'chat_messages',
        ['user_id', 'created_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_chat_messages_user_created_at', table_name='chat_messages')
    op.drop_index('ix_chat_messages_created_at', table_name='chat_messages')

    with op.batch_alter_table('chat_messages', schema=None) as batch_op:
        batch_op.alter_column(
            'created_at',
            new_column_name='timestamp',
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=sa.func.now(),
        )

    op.create_index('ix_chat_messages_timestamp', 'chat_messages', ['timestamp'])
    op.create_index(
        'ix_chat_messages_user_timestamp',
        'chat_messages',
        ['user_id', 'timestamp'],
    )