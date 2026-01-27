"""Bulk-create/update users from a CSV list.

Run from project root:
    python manage.py shell -c "from SmileHealth.scripts.bulk_create_users import run; run('path/to/users.csv')"

CSV headers (case/spacing flexible):
    first_name, last_name, branch, role, email
Optional headers:
    username, password

Username rule (per request): first two letters of first name + last name (spaces removed), ASCII/slugified, then deduplicated by adding a counter.
Passwords: uses provided password on create; otherwise generates a random password per new user. Existing users keep their password unless reset_password=True.
"""
from __future__ import annotations

import csv
import re
import secrets
import string
from pathlib import Path
from typing import Dict, Iterable, Tuple

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.text import slugify

from SmileHealth.models import Branch, Profile

User = get_user_model()

ROLE_MAP = {
    "auszubildende": Profile.Role.ASSISTANT,
    "einstiegsqualifikant": Profile.Role.VIEWER,
}


def _normalize_headers(headers: Iterable[str]) -> Dict[str, str]:
    mapping = {}
    for h in headers:
        norm = (h or "").strip().lower().replace(" ", "_")
        mapping[norm] = h
    return mapping


def _normalize_row(row: Dict[str, str]) -> Dict[str, str]:
    normalized = {}
    for key, value in row.items():
        norm_key = (key or "").strip().lower().replace(" ", "_")
        normalized[norm_key] = (value or "").strip()
    return normalized


def _gen_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _username_from_names(first_name: str, last_name: str) -> str:
    first_two = (first_name or "")[:2]
    base = f"{first_two}{last_name}".replace(" ", "")
    # slugify enforces ASCII and lowercases; remove hyphens to keep compact
    base = slugify(base).replace("-", "") or "user"
    return base


def _unique_username(base: str) -> str:
    candidate = base
    n = 1
    while User.objects.filter(username=candidate).exists():
        n += 1
        candidate = f"{base}{n}"
    return candidate


def _normalize_role(raw: str) -> str:
    key = (raw or "").strip().lower()
    return ROLE_MAP.get(key, Profile.Role.VIEWER)


def _get_or_create_branch(name: str):
    name = (name or "").strip()
    if not name:
        return None
    branch, _ = Branch.objects.get_or_create(name=name)
    return branch


def _choose_username(row: Dict[str, str]) -> str:
    explicit = row.get("username", "")
    if explicit:
        base = slugify(explicit).replace("-", "") or "user"
    else:
        base = _username_from_names(row.get("first_name", ""), row.get("last_name", ""))
    return _unique_username(base)


def _upsert_user(row: Dict[str, str], reset_password: bool, password_length: int) -> Tuple[str, bool, str]:
    first = row.get("first_name", "")
    last = row.get("last_name", "")
    email = row.get("email", "") or None
    branch_name = row.get("branch", "")
    role_raw = row.get("role", "")

    username = _choose_username(row)
    supplied_password = row.get("password", "")
    password = supplied_password or _gen_password(password_length)

    with transaction.atomic():
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"first_name": first, "last_name": last, "email": email},
        )

        updated = False
        for field, value in (("first_name", first), ("last_name", last), ("email", email)):
            if value and getattr(user, field) != value:
                setattr(user, field, value)
                updated = True
        if updated:
            user.save()

        if created or reset_password:
            user.set_password(password)
            user.save()
        else:
            password = ""  # keep existing password undisclosed

        profile, _ = Profile.objects.get_or_create(user=user)
        profile.role = _normalize_role(role_raw)
        profile.save()

        branch = _get_or_create_branch(branch_name)
        if branch:
            profile.branches.add(branch)

    return user.username, created, password


def run(csv_path: str, *, reset_password: bool = False, password_length: int = 12) -> None:
    path = Path(csv_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        expected = {"first_name", "last_name", "branch", "role", "email"}
        header_keys = _normalize_headers(reader.fieldnames or {}).keys()
        missing = expected - set(header_keys)
        if missing:
            raise ValueError(f"CSV is missing headers: {', '.join(sorted(missing))}")

        created, updated = 0, 0
        new_credentials = []
        for row in reader:
            normalized_row = _normalize_row(row)
            username, was_created, password = _upsert_user(
                normalized_row, reset_password, password_length
            )
            if was_created:
                created += 1
                if password:
                    new_credentials.append(
                        (username, normalized_row.get("email", ""), password)
                    )
            else:
                updated += 1
            print(f"processed: {username} (created={was_created})")

    print(f"\nDone. created={created}, updated={updated}")
    if new_credentials:
        print("\nNew credentials (store securely):")
        for username, email, password in new_credentials:
            print(f"  user={username} email={email} temp_password={password}")


if __name__ == "__main__":
    raise SystemExit("Use run() via manage.py shell; see module docstring.")
