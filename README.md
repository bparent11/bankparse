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

Stop it with:

```bash
docker compose stop      # pause the containers (restart with: docker compose start)
docker compose down      # stop and remove the containers; ./data is kept
docker compose logs -f   # follow the logs
```

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

### Several people

Each person gets their own **user** in the app: their accounts, operations, files and learned categorization rules stay separate; the list of categories is shared.

- On the **Importer** page, choose **Importer pour**: *Détection automatique* (the name printed on each statement decides; a new name creates a new user), an existing user, or **＋ Nouvel utilisateur…** to add someone, then drop their statements.
- Switch between users with the selector at the top of the menu (✏️ to rename, or to remove a user who has no account).
- A wrongly placed account can be moved with its ✏️ button on the **Comptes** page.
- Command line: `uv run bankparse-app import <folder> --user "Prénom Nom"`.

Users are for tidiness, not security: there is no password.

## Categorization with a local LLM

The **Opérations** page has a **« Catégoriser… »** button that classifies operations with a model running **on your own PC** through [Ollama](https://ollama.com): labels never leave the machine.

1. Install Ollama and at least one model, e.g. `ollama pull gemma4`.
2. Keep Ollama running, click **Catégoriser…**, then choose:
   - the **speed**: *Rapide* (small model `gemma4:e2b`, 10 operations per request) or *Précis* (bigger model `gemma4`, one at a time),
   - the **model** (preselected from the speed; any installed model can be chosen),
   - the **operations**: never categorized, or all except the ones you classified yourself,
   - an optional **period**.

   Measured on a laptop CPU for 2 000 operations: fast (gemma4:e2b) ≈ 25 min, precise (gemma4) ≈ 3 h. Install both with `ollama pull gemma4:e2b` and `ollama pull gemma4`. Later runs only handle new operations.

How it guides the model (no hard-coded rules):
- Each operation is judged on its own, with its account, date and amount.
- Click a category in the table to fix it, optionally with **an explanation (« Pourquoi ? »)**: every manual choice becomes an example for the model in later runs. Ticking « appliquer aux opérations similaires » also applies it to similar labels and future imports.
- On the **Catégories** page, describe what each category means for you: the description is given to the model.
- **Validate** what the model proposed (the ✓ next to a category, or « À vérifier seulement » + « Valider ces N opérations » for a whole filtered list): validated operations are never sent to the model again, which saves time on later runs.
- The model may answer **« Inconnu »** instead of guessing. A refund (« Avoir ») takes the category of the purchase.

Settings (optional environment variables): `BANKPARSE_OLLAMA_URL` (default `http://127.0.0.1:11434`; Docker Compose points to `host.docker.internal`) `BANKPARSE_OLLAMA_FAST_MODEL` (suggested for fast runs, default `gemma4:e2b`) and `BANKPARSE_OLLAMA_MODEL` (suggested for precise runs, default `gemma4:latest`).

## How deduplication works

1. **File level**: a PDF is identified by its SHA-256. Uploading the same file twice does nothing.
2. **Operation level**: each operation gets a fingerprint (bank, account, dates, normalized label, amount, and its rank among identical operations of the statement). Overlapping statements do not create duplicates, while two genuine identical purchases on the same day are both kept.
3. Deleting a statement removes only the operations no other statement contains.

Each imported statement is also checked: `opening balance + operations == closing balance` (shown as *Soldes vérifiés* in the app).

## Tests

```bash
uv run pytest                                       # library + API
BANKPARSE_STATEMENTS="../data/Relevés" uv run pytest packages/bankparse   # + your own statements (bash)
```

On Windows PowerShell:

```powershell
$env:BANKPARSE_STATEMENTS="..\data\Relevés"; uv run pytest packages/bankparse
```

Real statements contain personal data and are never committed. Put them in `packages/bankparse/tests/fixtures/` (gitignored) or point `BANKPARSE_STATEMENTS` to a folder.

After changing the API, regenerate the TypeScript client with `npm run gen:api` in `apps/web`.

## Roadmap

- Spending per category on the overview page.
- Boursorama brokerage statements (*espèces*, *titres*) and more banks.
