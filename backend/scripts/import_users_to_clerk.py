"""Import the existing Easy Single accounts into Clerk.

The application used to own its accounts: a local ``users`` table with bcrypt
passwords, signed in through ``POST /api/v1/auth/login``. Clerk now owns
authentication, so every existing account has to exist on the Clerk side as
well - otherwise the people who already signed up would suddenly be locked
out.

The good news is that Clerk can be handed a password *hash* instead of a
plaintext password, so nobody has to reset their password during the move.
The bcrypt digest already stored in ``users.password_hash`` is passed straight
through with ``password_hasher: "bcrypt"``.

What the script does
--------------------
1. Reads every account from the ``users`` table.
2. Skips the shared guest account, accounts that are already linked to a Clerk
   user, and accounts with no usable email address.
3. Creates the matching Clerk user with the same email, username, avatar and
   bcrypt digest (``external_id`` carries the internal user id, ``public_metadata``
   carries the admin role).
4. Stores the new Clerk user id in ``users.clerk_user_id`` so the backend links
   the two records explicitly instead of guessing by email.
5. Writes a JSON report next to this file.

Nothing happens unless ``--apply`` is passed: the default run is a dry run that
only prints what it *would* do.

Usage
-----
    cd backend
    ../.venv/Scripts/python.exe scripts/import_users_to_clerk.py            # dry run
    ../.venv/Scripts/python.exe scripts/import_users_to_clerk.py --apply    # do it

Options
-------
    --apply               actually create the users (default: dry run)
    --limit N             only look at the first N database users
    --include-inactive    also import accounts that are marked inactive
    --include-guest       also import the shared guest account
    --no-mark-verified    create the Clerk users with unverified email addresses
    --set-password        also import the password digest when the account
                          already exists in Clerk (e.g. a Discord sign-up)
    --delay SECONDS       pause between Clerk API calls (default 0.4)
    --report PATH         where to write the JSON report
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# The application reads ../.env relative to the working directory, so the
# script has to run from the backend folder no matter where it is called.
os.chdir(BACKEND_ROOT)

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.config import GUEST_EMAIL, settings  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402

CLERK_BACKEND_API = "https://api.clerk.com/v1"
REPORT_PATH = Path(__file__).resolve().parent / "clerk_import_report.json"

# The ids that have to be written back to the database are collected first and
# committed in one transaction, so a failure halfway through does not leave
# the table half updated.
_pending_links: list[tuple[str, str]] = []


class ClerkApiError(RuntimeError):
    """Raised when Clerk refuses a request."""


# --------------------------------------------------------------------------
# Clerk Backend API
# --------------------------------------------------------------------------


class ClerkClient:
    """A very small wrapper around the Clerk Backend API."""

    def __init__(self, secret_key: str, delay: float = 0.4) -> None:
        if not secret_key:
            raise SystemExit("CLERK_SECRET_KEY is not set - add it to ../.env first")
        self._secret_key = secret_key
        self._delay = delay
        self._client = httpx.AsyncClient(timeout=30.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        url = f"{CLERK_BACKEND_API}{path}"
        headers = {
            "Authorization": f"Bearer {self._secret_key}",
            "Content-Type": "application/json",
        }
        attempt = 0
        while True:
            attempt += 1
            response = await self._client.request(method, url, headers=headers, json=payload)
            if response.status_code == 429:
                wait = float(response.headers.get("Retry-After") or (2 ** attempt))
                print(f"  rate limited, retrying in {wait:.0f}s", flush=True)
                await asyncio.sleep(wait)
                continue
            if response.status_code >= 400:
                body = response.text[:500]
                raise ClerkApiError(f"{method} {path} -> HTTP {response.status_code}: {body}")
            if not response.content:
                return {}
            data = response.json()
            # The Clerk API is rate limited, so pace the calls.
            await asyncio.sleep(self._delay)
            return data

    async def list_users(self) -> list[dict[str, Any]]:
        """Return every user on the instance, following the pagination."""
        users: list[dict[str, Any]] = []
        offset = 0
        limit = 100
        while True:
            data = await self._request("GET", f"/users?limit={limit}&offset={offset}")
            if isinstance(data, list):
                page = data
            else:
                page = data.get("data", [])
            users.extend(page)
            if len(page) < limit:
                break
            offset += limit
        return users

    async def create_user(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/users", payload)

    async def update_user(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PATCH", f"/users/{user_id}", payload)

    async def set_admin_metadata(self, user_id: str) -> None:
        await self.update_user(user_id, {"public_metadata": {"role": "admin"}})

    async def set_password(self, user_id: str, password_hash: str) -> None:
        await self.update_user(
            user_id,
            {"password_hasher": "bcrypt", "password_digest": password_hash},
        )


# --------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------


def _clerk_email(address: Any) -> str:
    """Read the email out of a Clerk email-address object.

    The Backend API calls the field ``email_address``; older payloads and the
    frontend SDK use ``email``. Both are accepted.
    """
    if not isinstance(address, dict):
        return ""
    return (address.get("email_address") or address.get("email") or "").strip().lower()


def build_payload(user: User, mark_verified: bool) -> dict[str, Any]:
    """Build the Clerk ``CreateUser`` payload for a database account."""
    email_address: dict[str, Any] = {"email": user.email}
    if mark_verified:
        email_address["verified"] = True

    payload: dict[str, Any] = {
        "email_address": [email_address],
        "username": user.username,
        "external_id": str(user.id),
        # The bcrypt digest is handed over as-is, so the existing password
        # keeps working and Clerk can upgrade the hash on the first sign-in.
        "password_hasher": "bcrypt",
        "password_digest": user.password_hash,
    }
    if user.avatar_url:
        payload["profile_image_url"] = user.avatar_url
    if user.is_admin:
        payload["public_metadata"] = {"role": "admin"}
    return payload


async def run(args: argparse.Namespace) -> int:
    secret_key = settings.clerk_secret_key
    if not secret_key:
        print("CLERK_SECRET_KEY is not set - add it to ../.env first", file=sys.stderr)
        return 2

    client = ClerkClient(secret_key, delay=args.delay)
    report: list[dict[str, Any]] = []

    try:
        async with AsyncSessionLocal() as session:
            query = select(User).order_by(User.created_at)
            if not args.include_inactive:
                query = query.where(User.is_active.is_(True))
            result = await session.execute(query)
            users = list(result.scalars().all())

        if args.limit:
            users = users[: args.limit]

        print(f"Found {len(users)} account(s) in the database")
        if not args.apply:
            print("DRY RUN - nothing is written to Clerk or the database\n")
            print("Re-run with --apply to perform the import.\n")

        clerk_users = await client.list_users()
        print(f"Clerk already holds {len(clerk_users)} user(s)\n")

        clerk_by_email: dict[str, dict[str, Any]] = {}
        for clerk_user in clerk_users:
            for address in clerk_user.get("email_addresses", []) or []:
                email = _clerk_email(address)
                if email:
                    clerk_by_email.setdefault(email, clerk_user)

        for index, user in enumerate(users, start=1):
            email = (user.email or "").strip()
            label = f"[{index}/{len(users)}] {user.username} <{email}>"

            if not args.include_guest and email.lower() == GUEST_EMAIL.lower():
                print(f"{label} - skipped (shared guest account)")
                report.append({"username": user.username, "email": email, "status": "skipped", "reason": "guest account"})
                continue

            if user.clerk_user_id:
                print(f"{label} - skipped (already linked to {user.clerk_user_id})")
                report.append({"username": user.username, "email": email, "status": "skipped", "reason": "already linked", "clerk_user_id": user.clerk_user_id})
                continue

            if not email or "@" not in email:
                print(f"{label} - skipped (no usable email address)")
                report.append({"username": user.username, "email": email, "status": "skipped", "reason": "no email"})
                continue

            if not user.password_hash:
                print(f"{label} - skipped (no password hash to import)")
                report.append({"username": user.username, "email": email, "status": "skipped", "reason": "no password hash"})
                continue

            existing = clerk_by_email.get(email.lower())
            if existing is not None:
                clerk_user_id = existing.get("id")
                print(f"{label} - exists in Clerk as {clerk_user_id}; linking only")
                if args.apply:
                    await link_user(user.id, clerk_user_id)
                    if user.is_admin and (existing.get("public_metadata") or {}).get("role") != "admin":
                        await client.set_admin_metadata(clerk_user_id)
                    if args.set_password:
                        # The account may have signed up with Discord and never
                        # had a password in Clerk. Importing the old digest
                        # makes the old password work there too.
                        await client.set_password(clerk_user_id, user.password_hash)
                        print(f"{label} - password digest imported into Clerk")
                report.append({"username": user.username, "email": email, "status": "linked", "clerk_user_id": clerk_user_id})
                continue

            payload = build_payload(user, mark_verified=not args.no_mark_verified)
            if not args.apply:
                print(f"{label} - would create a Clerk user")
                report.append({"username": user.username, "email": email, "status": "would create"})
                continue

            try:
                created = await client.create_user(payload)
            except ClerkApiError as error:
                print(f"{label} - FAILED: {error}")
                report.append({"username": user.username, "email": email, "status": "failed", "reason": str(error)})
                continue

            clerk_user_id = created.get("id")
            print(f"{label} - created {clerk_user_id}")
            await link_user(user.id, clerk_user_id)
            report.append({"username": user.username, "email": email, "status": "created", "clerk_user_id": clerk_user_id})

        if args.apply:
            await commit_links()

        summary: dict[str, int] = {}
        for entry in report:
            summary[entry["status"]] = summary.get(entry["status"], 0) + 1
        print("\nSummary:", ", ".join(f"{k}={v}" for k, v in sorted(summary.items())) or "nothing to do")

        report_path = Path(args.report) if args.report else REPORT_PATH
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Report written to {report_path}")
        return 0
    finally:
        await client.aclose()


async def link_user(user_id: Any, clerk_user_id: str | None) -> None:
    if not clerk_user_id:
        return
    _pending_links.append((str(user_id), clerk_user_id))


async def commit_links() -> None:
    if not _pending_links:
        return
    async with AsyncSessionLocal() as session:
        for user_id, clerk_user_id in _pending_links:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user is not None:
                user.clerk_user_id = clerk_user_id
        await session.commit()
    print(f"Linked {len(_pending_links)} account(s) to their Clerk user")


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Easy Single accounts into Clerk")
    parser.add_argument("--apply", action="store_true", help="actually create the users (default: dry run)")
    parser.add_argument("--limit", type=int, default=0, help="only look at the first N accounts")
    parser.add_argument("--include-inactive", action="store_true", help="also import inactive accounts")
    parser.add_argument("--include-guest", action="store_true", help="also import the shared guest account")
    parser.add_argument("--no-mark-verified", action="store_true", help="create users with unverified email addresses")
    parser.add_argument("--set-password", action="store_true", help="also import the password digest when a Clerk user already exists")
    parser.add_argument("--delay", type=float, default=0.4, help="pause between Clerk API calls in seconds")
    parser.add_argument("--report", type=str, default="", help="path of the JSON report")
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
