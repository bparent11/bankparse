"""Command line ``bankparse-app``: ``import <folder-or-pdf>...`` and ``serve``."""

import argparse
import sys
from pathlib import Path

from sqlmodel import Session

from bankparse_api.db import get_engine
from bankparse_api.ingest import import_pdf

ICONS = {"imported": "+", "already_imported": "=", "failed": "!", "unsupported": "-"}


def _import(paths: list[str]) -> int:
    files = []
    for p in map(Path, paths):
        files += sorted(p.rglob("*.pdf")) if p.is_dir() else [p]
    totals = {"inserted": 0, "duplicates": 0}
    failures = 0
    with Session(get_engine()) as session:
        for f in files:
            r = import_pdf(session, f.name, f.read_bytes())
            totals["inserted"] += r.inserted
            totals["duplicates"] += r.duplicates
            failures += r.status == "failed"
            check = {True: "balance OK", False: "BALANCE MISMATCH", None: ""}[r.check_ok]
            detail = r.error or f"{r.inserted} new, {r.duplicates} duplicates {check}".strip()
            print(f"[{ICONS.get(r.status, '?')}] {f.name}: {r.status} - {detail}")
    print(f"\n{len(files)} files, {totals['inserted']} new operations, {totals['duplicates']} duplicates skipped.")
    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="bankparse-app")
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import", help="Import PDF statements (files or folders, recursively).")
    imp.add_argument("paths", nargs="+")
    serve = sub.add_parser("serve", help="Run the API server.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.command == "import":
        sys.exit(_import(args.paths))
    if args.command == "serve":
        import uvicorn

        uvicorn.run("bankparse_api.main:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
