# Notes for coding agents

## ⚠️ Private data

**Never read, open, display or search `.env` / `.env.*` files**, and never run commands that print environment variables. Bank statements, the database and tokens are private (see below). Statements are imported by manual upload only: no bank login automation (ARCHITECTURE.md § 6).

Read [ARCHITECTURE.md](ARCHITECTURE.md) before changing anything: it records the design decisions, the parser heuristics, the deduplication rules and the known limitations.

- Python: uv workspace. `uv sync`, `uv run pytest`, `uv run bankparse-app serve`, `uv run bankparse-app import <folder>`.
- Web: `apps/web` uses Next.js 16 (read `apps/web/AGENTS.md`) and shadcn/ui on Base UI (`render` prop, not `asChild`). Run `npm run gen:api` after API schema changes.
- Never commit bank statements, databases or tokens: `data/`, `packages/bankparse/tests/fixtures/` and `*Token*.txt` are gitignored on purpose.
- Any parser change must keep `test_real_statements.py` green on all available statements: `BANKPARSE_STATEMENTS=../data/bronze-layer uv run pytest packages/bankparse`.
