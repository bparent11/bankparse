# Architecture & design decisions

This document explains **why** the project is built the way it is, so that a human or an AI agent can continue the work without re-deriving everything. For **how to run** it, see [README.md](README.md).

## 1. Goal and constraints

- Extract operations from the PDF statements of French banks and make them browsable in an app.
- **Single user, local only.** Bank data must never leave the machine: no login, no cloud, Docker ports bound to `127.0.0.1`.
- Every uploaded operation is **stored persistently and deduplicated**.
- `bankparse` stays an **independent, publishable PyPI library**. The app depends on it, not the other way around.
- Next step (not done yet): automatic categorization with a **local** LLM (Ollama). The `transaction.category` / `category_source` columns are already there.

## 2. Repository layout

```
pyproject.toml            uv workspace root (members: packages/bankparse, apps/api), dev tools, pytest paths
packages/bankparse/       the library (PyPI package "bankparse")
  src/bankparse/
    __init__.py           public API: parse(), detect_bank(), models, errors, __version__
    core.py               parse(): open the PDF once -> detect bank -> dispatch to a parser
    detect.py             bank detection from the first page text
    models.py             ParsedStatement, Account, Transaction, BalanceSnapshot, BalanceCheck
    errors.py             BankParseError > UnsupportedStatementError, ParseError
    utils.py              French amounts/dates helpers (parse_fr_amount, find_french_long_date, infer_year…)
    parsers/
      _common.py          Document/Page/Line/Table wrappers, owner detection, balance check helper
      ca.py, cm.py, bourso.py   one parser per bank -> ParsedStatement
    file_manager/, table_manager/   LEGACY 0.0.x class-based API, kept for backward compatibility
  tests/                  unit tests (committed) + real-statement regression tests (private PDFs)
apps/api/                 FastAPI + SQLModel + SQLite (package "bankparse-api", CLI "bankparse-app")
  src/bankparse_api/
    main.py               all HTTP routes
    ingest.py             import + dedup logic (the heart of the app)
    models.py             database tables
    queries.py            transaction filters shared by the list and export endpoints
    schemas.py            response models (they drive the generated TypeScript types)
    config.py, db.py, cli.py
apps/web/                 Next.js 16 + Tailwind 4 + shadcn/ui (Base UI) + TanStack Query
docker-compose.yml        api + web, ./data mounted as the data volume
```

Private data is never committed (see `.gitignore`): `data/`, `*.db`, `packages/bankparse/tests/fixtures/`, token files.

## 3. The library

### 3.1 Pipeline

`bankparse.parse(source)` accepts a path, bytes or a file object. It works in four steps:

1. Open the PDF **once** with pdfplumber.
2. `detect_bank(first_page_text)` returns `CA`, `CM` or `BOURSO`, or raises `UnsupportedStatementError`.
3. `load_document()` reads every page once: text, text lines with their vertical position (`top`), tables with their position, and the words with their x/y positions (Bourso only).
4. The bank parser builds a `ParsedStatement`.

Every unexpected exception inside a parser is wrapped in a `ParseError`, so callers only ever see the two bankparse error types.

### 3.2 Output model (bank-agnostic)

- Amounts are `Decimal` and **signed**: a debit is negative. The library never uses floats.
- Dates are `datetime.date`.
- `account_id` is the bank's account number. For Bourso it is the 11-digit account number, not the IBAN.
- `balances` holds `BalanceSnapshot(account, date, amount)` entries: the opening and closing balances, plus for CM the "other accounts" and "loans" summary tables.
- `checks` holds one `BalanceCheck` per account. Its `ok` field is `opening + Σ amounts == closing`, or `None` when one of the two balances is missing. `ParsedStatement.is_consistent` combines the checks.

**Why the balance check matters:** these parsers rely on layout rules, so they can silently miss or misread a line. The check catches that kind of error, and it is the main quality signal shown in the app.

### 3.3 Bank detection (`detect.py`)

Detection first looks for **strong structural signals**. Bank names alone are not enough, because operation labels mention other banks (a CA statement can contain "Virement depuis BoursoBank"):

- **CA:** "CREDIT AGRICOLE" and "Date d'arrêté".
- **Bourso:** the BIC `BOUSFRPP` and "MOUVEMENTS EN EUR".
- **CM:** "RELEVE ET INFORMATIONS BANCAIRES", the BIC `CMCIFR`, or the IBAN prefix `FR761027`. The 2014–2016 statements only print "CCM <city>" as the bank name.

Only after that are bank names used. A Boursorama document that is not an account statement (brokerage "espèces" or "titres") raises `UnsupportedStatementError`.

The text is compared after `unidecode` + upper-case, and the spaces are removed in a "compact" copy, because pdfplumber sometimes glues words together.

### 3.4 Parsers (layout heuristics, verified on 2014–2025 statements)

**Crédit Agricole (`ca.py`)**
- **Statement date:** the `Date d'arrêté : 06 Novembre 2025` line.
  - The old code took the first `<number> <word> <year>` it found, so shop names like "Lidl" were read as months.
  - The month regex now only accepts real French month names.
- **Tables:** 6 columns, which are operation date (`dd.mm`, no year), value date, label, debit, credit, and an unused last column. The header repeats on every page.
- **Balance rows:** `Ancien/Nouveau solde créditeur|débiteur au dd.mm.yyyy`. The "Total des opérations" row is skipped.
- **Labels on several lines:** a row with no date and no amount continues the previous operation's label.
- **Year of `dd.mm` dates:** `infer_year()` uses the statement year, minus one when the month is after the statement month (e.g. 31.12 on a statement dated January 2025 means 2024).
- **Account:** the line `… n° <11 digits>`. A table belongs to the closest account header line above it on the same page.

**Crédit Mutuel (`cm.py`)**
- **Statement date:** a line made only of a long date (`31 octobre 2025`).
- **Several accounts per statement.** Each one has a header line `<label> N° <11 digits>`, repeated above every piece of its table, including on the next page. Each table is attached to the closest header above it, and the pieces are merged.
- **Tables:** 5 columns (date `dd/mm/yyyy`, value date, label, debit, credit).
- **Balance rows** (`SOLDE CREDITEUR|DEBITEUR|NUL AU dd/mm/yyyy`): the first one for an account is the opening balance, the next one the closing balance. A row with an empty first cell continues the previous label.
- **Summary tables:** the 3-column table "SITUATION DE VOS AUTRES COMPTES" and the 4-column table "SITUATION DE VOS CREDITS" add accounts and balance snapshots at the statement date. They carry no operations.

**Boursorama (`bourso.py`)**
- The statement has **no ruled table**, so operations are rebuilt from word positions:
  - date at x < 90;
  - label from x = 90 to 370;
  - value date from x = 370 to 430;
  - amount at x ≥ 430.
- An amount whose right edge is left of x = 495 is in the Débit column.
- **Section boundaries:** the operations start after "MOUVEMENTS" on each page and end at "Nouveau solde" (the closing balance, found within ±4 pt vertically). The page footer (y ≥ 735) is ignored.
- **Opening balance:** the `SOLDE AU : dd/mm/yyyy` line. The statement date is the end of the period `du … au …`.
- **Broken fonts:** some fonts map accented letters to the wrong glyphs (`Ø` should be é, `Ł` should be è, and `RŁf` is "Réf"). `_fix_glyphs` repairs them.

### 3.5 Legacy API

`file_manager` and `table_manager` (the 0.0.x API) are kept and were bug-fixed:
- the property that called itself forever;
- in-place mutations of `self.content`;
- shallow copies of rows;
- CM `get_dict()` crashing on balance rows;
- the wrong CA year rule;
- CA dropping identical operations.

`FileFactory.handle_file` now reuses `detect_bank`, and still returns `None` for unknown files to stay compatible. **New code should use `bankparse.parse()`.**

## 4. The API (`apps/api`)

### 4.1 Storage

- SQLite in `$BANKPARSE_DATA_DIR` (default `<repo>/data`). The original PDFs are kept in `data/uploads/<sha256>.pdf`, so any file can be **re-analysed** after a parser improvement (`POST /api/files/{id}/reparse` or `/api/files/reparse-all`).
- Amounts are stored as **integer cents** (`amount_cents`). SQLite has no exact decimal type, and floats would round.
- Tables:
  - `account` (unique on bank + number, with an optional `custom_label` set by the user);
  - `statementfile` (sha256, status `parsed|failed|unsupported`, `check_ok`, `parser_version`);
  - `transaction` (with a unique `fingerprint`);
  - `transactionsource` (many-to-many link between operations and files);
  - `balance` (unique on account + date).
- There are no migrations yet: `create_all` runs at startup. **If you change the schema, add Alembic or delete the dev database.**

### 4.2 Deduplication (`ingest.py`)

1. **File level:** the SHA-256 of the bytes. A file that is already `parsed` is skipped. A `failed` or `unsupported` file is retried when uploaded again.
2. **Operation level:** `fingerprint = sha256(bank|account|op_date|value_date|NORMALIZED_LABEL|cents|n)`, where `n` is the rank of the operation among **identical** operations of the same statement. Two real identical purchases on the same day get n = 0 and n = 1, so both are kept. The same operation seen in two overlapping statements has the same fingerprint, so it is stored once.
3. `transactionsource` records every file that contains an operation. Deleting a file removes its links, then deletes the operations no other file still references, then the accounts left with no data.

Balance snapshots keep the first file that provided them. Deleting that file deletes the snapshot, even if another file had it too. This is a minor, known simplification.

### 4.3 Endpoints

`/api/uploads`, `/api/files` (list, delete, reparse, reparse-all), `/api/accounts` (list, PATCH label, balances), `/api/transactions` (filters, pagination, sorting, sums), `/api/transactions/export?format=csv|xlsx|json`, `/api/summary`. The interactive docs are at `/docs`.

- The CSV export targets French Excel: `;` separator, decimal comma, UTF-8 with BOM.
- Parsing is CPU-bound, so the route handlers are plain `def` functions. FastAPI runs them in its thread pool.

## 5. The web app (`apps/web`)

- **Next.js 16** with `cacheComponents` and `partialPrefetching`, as scaffolded. Read `apps/web/AGENTS.md`: this version differs from older Next.js, and its docs are in `node_modules/next/dist/docs/`.
- **Data fetching happens in the browser** with TanStack Query. The pages are static shells, so nothing server-side is cached.
- `/api/*` is proxied to FastAPI by `rewrites` in `next.config.ts`, so the browser talks to one origin and no CORS setup is needed. `API_URL` is read **at build time**, which is why the Docker image takes it as a build argument.
- **Typed client:** `openapi-fetch` + types generated by `openapi-typescript` (`src/lib/api-types.ts`). Run `npm run gen:api` after changing the API schemas.
- **shadcn/ui uses the `base-nova` style**, built on Base UI rather than Radix: components take a `render` prop instead of `asChild`. `cn` comes from the `cn` package.
- **Deliberate choices:**
  - No TanStack Table: it installed as v9 with a new API, and sorting and pagination are done on the server anyway.
  - Native `<select>` elements (`components/native-select.tsx`) instead of the Base UI Select, for simplicity and accessibility.
  - `useSearchParams` (the `?account=` deep link) is only used in `OperationsView`, wrapped in `<Suspense>` as Cache Components requires.
  - Uploads are sent **one file per request**, for per-file progress and so that one bad file doesn't block the others.
- **UI:** French; dark mode follows the system (`next-themes`); credit and debit colors are the `--positive` / `--negative` tokens in `globals.css`.

## 6. Decision: no automatic retrieval from the banks

An automatic retrieval robot (woob modules, credentials in Windows Credential Manager, "Récupérer mes relevés" button) was built and then **removed at the user's request on 2026-11-11**: it was too fragile to run in practice (it needs the API running natively on Windows, not in Docker, plus phone approval on each bank). Statements are imported **by manual upload only** (web Import page or `bankparse-app import`). Do not reintroduce bank logins or credential handling without an explicit request from the user.

## 7. Tests

- `uv run pytest` runs the library unit tests, the detection tests, and the API tests. The API tests check deduplication, delete, filters and export with **synthetic statements** (`bankparse.parse` is monkeypatched), so they are committed and need no private data.
- **Real-statement regression tests** (`packages/bankparse/tests/test_real_statements.py`) run on every PDF in `tests/fixtures/` and in the folders listed in `BANKPARSE_STATEMENTS` (separated by `os.pathsep`). Each file must parse, pass its balance check, and parse the same from bytes as from a path, and the legacy API must still work on it.
  - Reference run (2025-11): 167 supported statements (2014–2025) passed and 39 brokerage statements were correctly rejected.
- **When a new statement fails or shows "Écart de solde":**
  1. copy it into `tests/fixtures/`;
  2. fix the parser;
  3. re-run the tests on all statements;
  4. click "Tout réanalyser" in the app.

## 8. Known limitations

- The parsers rely on page layout. A bank redesigning its PDF can break them. The balance check and the `failed` status make such breakage **visible, not silent**.
- They were validated on statements from **one customer**: Crédit Agricole Lorraine, one Crédit Mutuel branch, and Boursorama, 2014–2025. Other regional CA banks or other CM branches may use slight variants.
- Scanned PDFs (images without a text layer) are not supported, since there is no OCR.
- Not supported yet: Boursorama brokerage statements (`Relevés-espèces`, `Relevés-titres`), other banks, foreign currencies.
- Legacy code: `file_manager/bourso_statement_file.py` can reference an undefined variable in a rare edge case (flagged by ruff F821). The new parser does not use this code.

## 9. How to add a bank

1. Dump a statement's layout (page text, `page.find_tables()`, `page.extract_words()` with their x/y positions) to see its structure.
2. Add a strong detection signal in `detect.py`, ideally the BIC or the IBAN bank code.
3. Write `parsers/<bank>.py`, returning a `ParsedStatement` with opening and closing balances so the check works.
4. Register it in `core._PARSERS` and `detect.BANK_NAMES`, and add its label and color in `apps/web/src/lib/format.ts` and `components/common.tsx`.
5. Add statements to the fixtures and make `test_real_statements.py` pass.
