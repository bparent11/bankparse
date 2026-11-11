# bankparse

Turn the monthly PDF statements of your French bank into structured, searchable data, **on your own computer**.

- [`packages/bankparse`](packages/bankparse): the Python library that reads the PDFs (Crédit Agricole, Crédit Mutuel, Boursorama), published on PyPI.
- [`apps/api`](apps/api): a FastAPI service that imports statements into SQLite, deduplicates operations and exports them.
- [`apps/web`](apps/web): a Next.js + Tailwind + shadcn/ui interface to upload statements and browse operations.

Nothing leaves your machine: no account, no cloud, the database and the uploaded PDFs live in `./data`.

## Run the app

### With Docker (simplest)

```bash
docker compose up -d --build
```

Open http://localhost:3000. Data is stored in `./data` (SQLite + original PDFs). Ports are bound to `127.0.0.1` only.

### For development

Requirements: [uv](https://docs.astral.sh/uv/) and Node.js ≥ 20.

```bash
uv sync                                   # Python workspace (library + API)
uv run bankparse-app serve                # API on http://127.0.0.1:8000  (docs: /docs)

cd apps/web && npm install && npm run dev # web on http://localhost:3000, /api/* is proxied to FastAPI
```

### Bulk import existing statements

```bash
uv run bankparse-app import path/to/statements/     # folders are scanned recursively
```

Re-running it is safe: already imported files and operations are skipped.

## How deduplication works

1. **File level**: a PDF is identified by its SHA-256. Uploading the same file twice does nothing.
2. **Operation level**: each operation gets a fingerprint (bank, account, dates, normalized label, amount, and its rank among identical operations of the statement). Overlapping statements do not create duplicates, while two genuine identical purchases on the same day are both kept.
3. Deleting a statement removes only the operations no other statement contains.

Each imported statement is also checked: `opening balance + operations == closing balance` (shown as *Soldes vérifiés* in the app).

## Tests

```bash
uv run pytest                                       # library + API
BANKPARSE_STATEMENTS=../data/bronze-layer uv run pytest packages/bankparse   # + your own statements
```

Real statements contain personal data and are never committed. Put them in `packages/bankparse/tests/fixtures/` (gitignored) or point `BANKPARSE_STATEMENTS` to a folder.

After changing the API, regenerate the TypeScript client with `npm run gen:api` in `apps/web`.

## Roadmap

- Automatic categorization (groceries, rent, salary…) with a **local LLM** (Ollama) and editable rules. The `category` column is already in the database.
- Boursorama brokerage statements (*espèces*, *titres*) and more banks.
