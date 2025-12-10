# auth_tokens.py

import argparse
import hashlib
import json
import secrets
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

DEFAULT_TOKENS_FILE = Path("tokens.json")


# --- Data model ---

@dataclass
class TokenRecord:
    name: str
    hash: str
    expires: datetime
    created_at: Optional[datetime] = None
    scopes: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "TokenRecord":
        expires = datetime.fromisoformat(data["expires"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)

        created_at_raw = data.get("created_at")
        if created_at_raw is not None:
            created_at = datetime.fromisoformat(created_at_raw)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
        else:
            created_at = None

        scopes = data.get("scopes") or []

        return cls(
            name=data["name"],
            hash=data["hash"],
            expires=expires,
            created_at=created_at,
            scopes=scopes,
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "hash": self.hash,
            "expires": self.expires.astimezone(timezone.utc).isoformat(),
            "created_at": (
                self.created_at.astimezone(timezone.utc).isoformat()
                if self.created_at
                else None
            ),
            "scopes": self.scopes,
        }


# --- JSON file helpers ---

def load_token_records(path: Path) -> List[TokenRecord]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"Token file '{path}' is corrupted or contains invalid JSON: {e}")
    
    try:
        return [TokenRecord.from_dict(item) for item in data]
    except (KeyError, TypeError) as e:
        raise ValueError(f"Token file '{path}' contains invalid token data: missing or invalid field: {e}")
    except ValueError as e:
        # ValueError from datetime.fromisoformat() or other parsing
        raise ValueError(f"Token file '{path}' contains invalid token data: {e}")


def save_token_records(path: Path, records: List[TokenRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = [rec.to_dict() for rec in records]
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    tmp.replace(path)


def find_record_by_name(records: List[TokenRecord], name: str) -> Optional[TokenRecord]:
    for rec in records:
        if rec.name == name:
            return rec
    return None


# --- Token generation / hashing ---

def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- CLI actions ---

def cmd_add(name: str, ttl_days: int, scopes: List[str], file: Path) -> int:

    try:
        records = load_token_records(file)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if find_record_by_name(records, name) is not None:
        print(f"ERROR: A token with name '{name}' already exists.", file=sys.stderr)
        return 1

    token = generate_token()
    token_hash = hash_token(token)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=ttl_days)
    scopes_norm = sorted(set(scopes)) if scopes else []

    record = TokenRecord(
        name=name,
        hash=token_hash,
        expires=expires,
        created_at=now,
        scopes=scopes_norm,
    )
    records.append(record)
    save_token_records(file, records)

    print("Token created.")
    print(f"  name:     {name}")
    print(f"  ttl_days: {ttl_days}")
    print(f"  expires:  {expires.isoformat()}")
    print(f"  scopes:   {scopes_norm or '[]'}")
    print()
    print("Plaintext token (store this securely, you won't see it again):")
    print(token)
    return 0


def cmd_delete(name: str, file: Path) -> int:
    try:
        records = load_token_records(file)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    before = len(records)
    records = [rec for rec in records if rec.name != name]

    if len(records) == before:
        print(f"ERROR: No token with name '{name}' found.", file=sys.stderr)
        return 1

    save_token_records(file, records)
    print(f"Token '{name}' deleted.")
    return 0


def cmd_refresh(name: str, ttl_days: int, scopes: Optional[List[str]], file: Path) -> int:
    try:
        records = load_token_records(file)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    rec = find_record_by_name(records, name)

    if rec is None:
        print(f"ERROR: No token with name '{name}' found.", file=sys.stderr)
        return 1

    new_token = generate_token()
    new_hash = hash_token(new_token)
    now = datetime.now(timezone.utc)
    new_expires = now + timedelta(days=ttl_days)

    rec.hash = new_hash
    rec.expires = new_expires

    if scopes is not None and len(scopes) > 0:
        rec.scopes = sorted(set(scopes))

    save_token_records(file, records)

    print(f"Token '{name}' refreshed.")
    print(f"  ttl_days:    {ttl_days}")
    print(f"  new_expires: {new_expires.isoformat()}")
    print(f"  scopes:      {rec.scopes or '[]'}")
    print()
    print("New plaintext token (store this securely, you won't see it again):")
    print(new_token)
    return 0


# --- CLI entrypoint ---

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage hashed API tokens stored in a JSON file."
    )
    parser.add_argument(
        "--file",
        "-f",
        type=Path,
        default=DEFAULT_TOKENS_FILE,
        help=f"Path to tokens JSON file (default: {DEFAULT_TOKENS_FILE})",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    p_add = subparsers.add_parser("add", help="Add a new token")
    p_add.add_argument("name", help="Logical name for the token (must be unique)")
    p_add.add_argument(
        "--ttl",
        type=int,
        required=True,
        help="Time-to-live in days for the token",
    )
    p_add.add_argument(
        "--scope",
        action="append",
        default=[],
        help="Scope to assign (can be repeated)",
    )

    p_del = subparsers.add_parser("delete", help="Delete a token by name")
    p_del.add_argument("name", help="Name of the token to delete")

    p_ref = subparsers.add_parser("refresh", help="Refresh a token by name")
    p_ref.add_argument("name", help="Name of the token to refresh")
    p_ref.add_argument(
        "--ttl",
        type=int,
        required=True,
        help="New time-to-live in days (from now)",
    )
    p_ref.add_argument(
        "--scope",
        action="append",
        default=None,
        help=(
            "New scopes for the token (can be repeated). "
            "If omitted, existing scopes are preserved."
        ),
    )

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    file: Path = args.file

    if args.command == "add":
        return cmd_add(args.name, args.ttl, args.scope, file)
    elif args.command == "delete":
        return cmd_delete(args.name, file)
    elif args.command == "refresh":
        return cmd_refresh(args.name, args.ttl, args.scope, file)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())