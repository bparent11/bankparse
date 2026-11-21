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
2. `detect_bank(first_page_text)` returns `CA`, `CM`, `BOURSO` or `LCL`, or raises `UnsupportedStatementError`.
3. `load_document()` reads every page once: text, text lines with their vertical position (`top`), tables with their position (CA, CM), and the words with their x/y positions (Bourso and LCL, which have no ruled table).
4. The bank parser builds a `ParsedStatement`.

Every unexpected exception inside a parser is wrapped in a `ParseError`, so callers only ever see the two bankparse error types.

### 3.2 Output model (bank-agnostic)

- Amounts are `Decimal` and **signed**: a debit is negative. The library never uses floats.
- Dates are `datetime.date`.
- `account_id` is the bank's account number. For Bourso it is the 11-digit account number, not the IBAN. For LCL it is the 5-digit branch code ("indicatif") + the 6-digit account number, without the key letter (`01234123456`), as in LCL's own file names.
- `balances` holds `BalanceSnapshot(account, date, amount)` entries: the opening and closing balances, plus for CM the "other accounts" and "loans" summary tables.
- `checks` holds one `BalanceCheck` per account. Its `ok` field is `opening + Σ amounts == closing`, or `None` when one of the two balances is missing. `ParsedStatement.is_consistent` combines the checks.

**Why the balance check matters:** these parsers rely on layout rules, so they can silently miss or misread a line. The check catches that kind of error, and it is the main quality signal shown in the app.

### 3.3 Bank detection (`detect.py`)

Detection first looks for **strong structural signals**. Bank names alone are not enough, because operation labels mention other banks (a CA statement can contain "Virement depuis BoursoBank"):

- **CA:** "CREDIT AGRICOLE" and "Date d'arrêté".
- **Bourso:** the BIC `BOUSFRPP` and "MOUVEMENTS EN EUR".
- **LCL:** "ECRITURES DE LA PERIODE" and either the BIC `CRLYFRPP` (current account) or "Crédit Lyonnais" (legal footer, the only bank name printed on savings statements). It is checked before CM, because a CM BIC or IBAN can appear in an LCL transfer label.
- **CM:** "RELEVE ET INFORMATIONS BANCAIRES", the BIC `CMCIFR`, or the IBAN prefix `FR761027`. The 2014–2016 statements only print "CCM <city>" as the bank name.

Only after that are bank names used. A Boursorama document that is not an account statement (brokerage "espèces", "titres" or "coupons-dividendes") raises `UnsupportedStatementError`, as does any other document (e.g. a rent receipt).

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

**LCL (`lcl.py`, verified on 2022–2026 statements)**
- **One layout for every product**, one account per statement: current account ("RELEVE DE COMPTE"), "LIVRET A", "RELEVE LIVRET JEUNE", "RELEVE DE COMPTE SUR LIVRET" (Livret LCL) and "RELEVE DE PLAN EPARGNE LOGEMENT". The title (first line) gives the account label. Savings statements are often yearly, and a current-account statement with no movement can cover 14 months.
- **No ruled table**: operations are rebuilt from word positions, after the `DATE LIBELLE VALEUR DEBIT CREDIT` header line of each page (repeated on page 2). Columns: operation date `dd.mm` at x < 70, label from x = 70 to the "VALEUR" header, value date `dd.mm.yy`, then the amount. An amount whose right edge is left of the midpoint between the right edges of the "DEBIT" and "CREDIT" headers is a debit. The ` .` printed after some debits is not used.
- **Balances:** `ANCIEN SOLDE` (opening) and `SOLDE EN EUROS` (closing, end of the section); their sign comes from the column too (an overdrawn balance is in DEBIT). `TOTAUX` (which includes the opening balance), `SOLDE INTERMEDIAIRE A FIN <mois>` and `PAS DE MOUVEMENT SUR LA PERIODE` are skipped. A page section ends at the `Page n / m` footer.
- **Dates:** the statement date is the end of the period `du dd.mm.yyyy au dd.mm.yyyy`. Operation dates have no year: the year closest to the value date (which has a 2-digit year) is used. The opening date is the `dd.mm` closest to the period start (it can be the day before), the closing date the one closest to the period end.
- **Labels on several lines:** a line with only words in the label column (`LIBELLE:…`, `REF.CLIENT:…`, the end of a long reference) continues the previous operation, also across pages.
- **Account:** `Indicatif :7000 Compte : 123456 L` (page 2+), the line below "Indicatif N° de compte" (savings), or the RIB `30002 <indicatif> <compte><clé> <clé RIB>` (current account).
- **Owner:** the line below "Titulaire du compte", left column only (the address is printed on the right), civility removed (`MLLE`, `MME`, `M`…), cut at " OU " for joint accounts.
- **Legacy API:** none; `FileFactory.handle_file` returns `None` for LCL.

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
  - `space` (one per account holder, see § 4.4);
  - `account` (unique on bank + number, with an optional `custom_label` set by the user, and its `space_id`);
  - `statementfile` (sha256, status `parsed|failed|unsupported`, `check_ok`, `parser_version`, `space_id`);
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

`/api/spaces` (list, PATCH name), `/api/uploads`, `/api/files` (list, delete, reparse, reparse-all), `/api/accounts` (list, PATCH label or space, balances), `/api/transactions` (filters, pagination, sorting, sums), `/api/transactions/export?format=csv|xlsx|json`, `/api/summary`. The interactive docs are at `/docs`.

- The CSV export targets French Excel: `;` separator, decimal comma, UTF-8 with BOM.
- Parsing is CPU-bound, so the route handlers are plain `def` functions. FastAPI runs them in its thread pool.

### 4.4 Spaces (`spaces.py`)

Several people can use the same app: each **user** (account holder) gets a **space**, and their data never mixes. The UI says "utilisateur".

- **Chosen at import:** the Import page has an "Importer pour" selector: *Détection automatique* (default), an existing user, or *＋ Nouvel utilisateur…* (`POST /api/spaces`, a `manual` space listed before it has accounts; also in the menu's user selector, which can rename a user or remove one without accounts). The choice is sent as the `space_id` form field of `POST /api/uploads` (CLI: `bankparse-app import <folder> --user "Prénom Nom"`). It wins over the name read on the PDF: it is stored in `statementfile.chosen_space_id` (also used by re-analysis), the file's accounts are moved there, even for a file imported before, and a warning is returned when the name read differs. When the first statement imported into an empty user carries a holder name no other user has, that user **learns it** (`learn_holder`): later statements of that person are recognized automatically.
- **Automatic detection (no choice):** the holder name read on the statement (`ParsedStatement.owner`) gives the space. Banks write it in different orders ("Parent Benjamin" at CA and Boursorama, "Benjamin Parent" at CM), so the key `owner_key` ignores case, accents and word order (`benjamin parent`). A new holder creates a space (`ImportResult.space_created`, shown on the Import page).
- **An account never changes space by itself:** it keeps the space it was created in, so a manual move (`PATCH /api/accounts/{id}` with `space_id`, "Modifier le compte" in the app) sticks. Its statement files follow it.
- **Holder not readable:** the statement goes to the space of one of its known accounts; otherwise to a "Titulaire inconnu" space. **A file always belongs to exactly one user:** an unreadable or unsupported file goes to the user chosen at import, else to the user shown in the app (`fallback_space_id`); files left without one by older versions go to the first user at startup.
- **Scope:** accounts, operations, balances, files, `merchantrule` (unique on space + key), `correction` and `categorizationjob` belong to a space. **Categories are shared** (their counts are per space). One categorization runs at a time for the whole app (one local Ollama).
- **API:** list endpoints take an optional `space_id` query parameter; **omitted, they return every space** (CLI, tests). The web app always sends it: `lib/space.tsx` holds the current space (remembered in `localStorage`), `lib/queries.ts` adds it to every query and cache key, and the user selector is `components/space-switcher.tsx`. Spaces detected automatically and left with no account are not listed; spaces added by hand are.
- **Upgrade:** `spaces.migrate` (startup, idempotent) creates the spaces of existing accounts, attaches files, rules, corrections and jobs to them, and replaces the old unique index on `merchantrule.merchant_key` with one on `(space_id, merchant_key)`.
- **Not a security boundary:** there is no login. Anyone using the app can switch spaces, and the SQLite file holds everything.

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

## 6. Categorization (`apps/api/src/bankparse_api/categorize/`)

Design validated with the user after a first version based on per-merchant memory proved too rigid (one LLM answer copied to a whole group, e.g. 9 "Avoir SNCF" in Voyages; hand-written prompt rules such as "a credit is income" biasing refunds).

- **Every operation is judged on its own** by the model chosen for the run, with its context: account (label + bank), date, debit/credit and amount. **Nothing the model answers is copied to other operations.**
- **Only the user's own choices are reused:** every manual choice is stored in `correction` (label, amount, category, optional explanation `reason`) and given to the model as an example with its context (`user_examples`, 40 most recent). When the user ticks "apply to similar operations" (off by default), a `merchantrule` (source `user`, key from `merchant.py`) categorizes the similar operations and future imports, without the LLM.
- **Validation of the model's proposals:** `category_source = "validated"` (keeps `category_model`). Validated operations are excluded from every run, like the user's own choices (`runner.USER_SOURCES`). One by one (`POST /api/transactions/{id}/validation`) or for a whole filtered list (`POST /api/transactions/validation`, same filters as the list + `to_review`). Validations are not prompt examples: only corrections (where the user changed the category) are, so obvious cases do not drown the informative ones.
- **No hand-written rules in the prompt** (`prompt.py`): categories with their **user-editable descriptions** (`category.description`, seeded from `DEFAULT_CATEGORIES`), the user's policy for refunds ("an avoir takes the category of the purchase"), "answer Inconnu rather than guess", the JSON format, then the examples.
- **Runs** (`runner.py`, one at a time, cancellable): options chosen in the launch dialog: `model` (any installed Ollama model, `/api/categorize/status` lists them), `mode` (`new` = never categorized, `all` = everything except `user`/`rule` sources), optional period, and `batch_size` (1 = precise, 10 = fast: several independent operations per request, the prompt is read once). Each operation records `category_source` (`user` | `rule` | `llm`) and `category_model`.
- **Measured on the user's laptop** (Ryzen 7 7735HS, CPU only; 30 fictitious operations with known answers, same prompt): gemma4:latest precise 30/30 at 5.5 s/op, fast 29/30 at 2.0 s/op (~1 h for 2 000 operations); gemma4:e2b precise 27/30 at 2.1 s/op, fast 24/30 at 0.7 s/op. Prompt reading dominates (~480 tokens re-read on every request: Ollama does not reuse it for Gemma 4), hence the batch option. Defaults: the fast option suggests a small model (`BANKPARSE_OLLAMA_FAST_MODEL`, gemma4:e2b; smallest installed otherwise) with batches of 10, the precise option a bigger one (`BANKPARSE_OLLAMA_MODEL`, gemma4:latest; largest installed otherwise), one operation per request. Fast is preselected for the very first run, precise afterwards; the user can pick any installed model.
- **Ollama call** (`ollama.py`): `/api/chat`, `think: false` (Gemma 4 otherwise reasons ~500 tokens), `temperature: 0`, JSON-Schema `format` whose `enum` forces a valid category (and ids in batch mode). Unusable answer → `Inconnu`.
- **Schema upgrades:** `db.add_missing_columns` adds new nullable columns to existing SQLite databases at startup (no migration tool yet; a NOT NULL column would require a real migration). At startup: default categories get their description, past manual choices become corrections (`backfill_corrections`), LLM answers memorized by the first version are dropped (`forget_llm_memory`).
- **Import & re-analysis** (`ingest.py`): user rules apply to new imports; categories are kept by fingerprint when a statement is re-analysed.
- **Docker:** the API container reaches the host's Ollama via `host.docker.internal` (verified).
- **Privacy:** only a local Ollama URL is supported. Never send labels to an external API.

## 7. Decision: no automatic retrieval from the banks

An automatic retrieval robot (woob modules, credentials in Windows Credential Manager, "Récupérer mes relevés" button) was built and then **removed at the user's request on 2026-11-11**: it was too fragile to run in practice (it needs the API running natively on Windows, not in Docker, plus phone approval on each bank). Statements are imported **by manual upload only** (web Import page or `bankparse-app import`). Do not reintroduce bank logins or credential handling without an explicit request from the user.

## 8. Tests

- `uv run pytest` runs the library unit tests, the detection tests, and the API tests. The API tests check deduplication, delete, filters and export with **synthetic statements** (`bankparse.parse` is monkeypatched), so they are committed and need no private data.
- **Real-statement regression tests** (`packages/bankparse/tests/test_real_statements.py`) run on every PDF in `tests/fixtures/` and in the folders listed in `BANKPARSE_STATEMENTS` (separated by `os.pathsep`). Each file must parse, pass its balance check, and parse the same from bytes as from a path, and the legacy API must still work on it.
  - Reference run (2025-11): 167 supported statements (2014–2025) passed and 39 brokerage statements were correctly rejected.
- **When a new statement fails or shows "Écart de solde":**
  1. copy it into `tests/fixtures/`;
  2. fix the parser;
  3. re-run the tests on all statements;
  4. click "Tout réanalyser" in the app.

## 9. Known limitations

- The parsers rely on page layout. A bank redesigning its PDF can break them. The balance check and the `failed` status make such breakage **visible, not silent**.
- They were validated on statements from **two customers**: Crédit Agricole Lorraine, one Crédit Mutuel branch and Boursorama (2014–2026), and LCL (one branch, 2022–2026: current account, Livret A, Livret Jeune, Livret LCL, PEL). Other regional CA banks, other CM branches or other LCL products (credit cards with deferred debit, loans, securities, joint accounts) may use variants.
- LCL: an operation printed without a value date gets the year closest to the statement date; the `SOLDE INTERMEDIAIRE A FIN <mois>` lines have no day, so they are not stored as balance snapshots.
- Scanned PDFs (images without a text layer) are not supported, since there is no OCR.
- Joint accounts ("M ou Mme …"): only the first holder name is read, so the account goes to that person's space. Move it by hand if needed.
- Re-analysing the only file of an account recreates the account: a custom label or a manual space move is then lost.
- Not supported yet: Boursorama brokerage statements (`Relevés-espèces`, `Relevés-titres`, `Relevé-coupons-dividendes`), other banks, foreign currencies. Documents that are not statements (e.g. a rent receipt `QUIT_*.pdf`) are rejected with `UnsupportedStatementError`.
- Legacy code: `file_manager/bourso_statement_file.py` can reference an undefined variable in a rare edge case (flagged by ruff F821). The new parser does not use this code.

## 10. How to add a bank

1. Dump a statement's layout (page text, `page.find_tables()`, `page.extract_words()` with their x/y positions) to see its structure.
2. Add a strong detection signal in `detect.py`, ideally the BIC or the IBAN bank code.
3. Write `parsers/<bank>.py`, returning a `ParsedStatement` with opening and closing balances so the check works.
4. Register it in `core._PARSERS` and `detect.BANK_NAMES` (and in `core._WORD_LAYOUTS` if it is parsed from word positions), and add its label and color in `apps/web/src/lib/format.ts` and `components/common.tsx`. The legacy `FileFactory` does not need a class: it returns `None` for banks it does not know (add the bank to `LEGACY_BANKS` in the test only if you write one).
5. Add statements to the fixtures and make `test_real_statements.py` pass. A synthetic test built from word positions (see `tests/test_lcl.py`) documents the layout without committing private data.
