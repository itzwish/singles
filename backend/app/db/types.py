"""Dialect-agnostic column types.

The models are written once and run on both PostgreSQL (production) and SQLite
(local development / serverless fallback). Postgres-only types are attached via
`with_variant`, so the same model definitions work everywhere.
"""

from sqlalchemy import JSON, Uuid
from sqlalchemy.dialects.postgresql import JSONB

# UUID(as_uuid=True) on Postgres, CHAR(32) storage on everything else
UUID = Uuid(as_uuid=True)

# JSONB on Postgres, generic JSON elsewhere
JSONType = JSON().with_variant(JSONB, "postgresql")

__all__ = ["UUID", "JSONType"]