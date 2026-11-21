"""Command line ``bankparse-app``: ``import <folder-or-pdf>...`` and ``serve``."""

import argparse
import sys
from pathlib import Path

from sqlmodel import Session, select

from bankparse_api.db import get_engine
from bankparse_api.ingest import import_pdf
from bankparse_api.models import Space
from bankparse_api.spaces import create_space, owner_key

ICONS = {"imported": "+", "already_imported": "=", "failed": "!", "unsupported": "-"}


def _space_id(session: Session, user: str | None) -> int | None:
    """The user named on the command line (created when new), or None to use the holder read on each file."""
    if not user:
        return None
    space = session.exec(select(Space).where(Space.owner_key == owner_key(user))).first()
    if space is None:
        space = create_space(session, user)
        session.commit()
        print(f"New user: {space.name}")
    return space.id


def _import(paths: list[str], user: str | None = None) -> int:
    files: list[Path] = []
    for p in map(Path, paths):
        files += sorted(p.rglob("*.pdf")) if p.is_dir() else [p]
    totals = {"inserted": 0, "duplicates": 0}
    failures = 0
    with Session(get_engine()) as session:
        space_id = _space_id(session, user)
        for f in files:
            r = import_pdf(session, f.name, f.read_bytes(), space_id)
            totals["inserted"] += r.inserted
            totals["duplicates"] += r.duplicates
            failures += r.status == "failed"
            check = {True: "balance OK", False: "BALANCE MISMATCH", None: ""}[r.check_ok]
            detail = r.error or f"{r.inserted} new, {r.duplicates} duplicates {check}".strip()
            space = f" -> {r.space_name}" if r.space_name else ""
            print(f"[{ICONS.get(r.status, '?')}] {f.name}: {r.status} - {detail}{space}")
            for warning in r.warnings:
                print(f"    ! {warning}")
    print(f"\n{len(files)} files, {totals['inserted']} new operations, {totals['duplicates']} duplicates skipped.")
    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="bankparse-app")
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import", help="Import PDF statements (files or folders, recursively).")
    imp.add_argument("paths", nargs="+")
    imp.add_argument(
        "--user",
        help='Import the files for this user ("Prénom Nom", created if new) instead of the holder read on them.',
    )
    serve = sub.add_parser("serve", help="Run the API server.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.command == "import":
        sys.exit(_import(args.paths, args.user))
    if args.command == "serve":
        import uvicorn

        uvicorn.run("bankparse_api.main:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
