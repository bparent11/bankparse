import io
import json
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import pandas as pd
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import func
from sqlmodel import Session, col, select

from bankparse_api.categorize import runner as categorize_runner
from bankparse_api.categorize.routes import router as categorize_router
from bankparse_api.categorize.service import backfill_corrections, forget_llm_memory, seed_categories
from bankparse_api.config import get_settings
from bankparse_api.db import get_engine, get_session
from bankparse_api.ingest import ImportResult, import_pdf, process, remove_file_data
from bankparse_api.models import Account, Balance, Space, StatementFile, Transaction, TransactionSource
from bankparse_api.queries import (
    SortField,
    SpaceId,
    TransactionFilters,
    account_label,
    filtered_query,
    order_by,
    transaction_filters,
)
from bankparse_api.schemas import (
    AccountOut,
    AccountUpdate,
    BalanceOut,
    FileOut,
    ImportResultOut,
    MonthTotal,
    SpaceOut,
    SpaceUpdate,
    Summary,
    TransactionOut,
    TransactionPage,
)
from bankparse_api.spaces import SpaceError, create_space, move_account


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_engine()  # create the data folder and the tables
    with Session(get_engine()) as session:
        seed_categories(session)
        backfill_corrections(session)
        forget_llm_memory(session)
    categorize_runner.mark_interrupted_jobs()
    yield


app = FastAPI(
    title="bankparse",
    version="0.1.0",
    description="Import French bank statements and browse operations.",
    lifespan=lifespan,
)

app.include_router(categorize_router)

SessionDep = Annotated[Session, Depends(get_session)]
FiltersDep = Annotated[TransactionFilters, Depends(transaction_filters)]


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------- spaces
@app.get("/api/spaces", response_model=list[SpaceOut])
def list_spaces(session: SessionDep) -> list[SpaceOut]:
    """One space per user. Spaces detected from a holder and left without any account are not listed."""
    accounts = dict(session.exec(select(Account.space_id, func.count()).group_by(Account.space_id)).all())
    operations = dict(
        session.exec(
            select(Account.space_id, func.count())
            .join(Transaction, col(Transaction.account_id) == col(Account.id))
            .group_by(Account.space_id)
        ).all()
    )
    return [
        SpaceOut(id=sp.id, name=sp.name, account_count=accounts.get(sp.id, 0), transaction_count=operations.get(sp.id, 0))
        for sp in session.exec(select(Space).order_by(Space.id)).all()
        if accounts.get(sp.id) or sp.manual
    ]


@app.post("/api/spaces", response_model=SpaceOut, status_code=201)
def add_space(body: SpaceUpdate, session: SessionDep) -> SpaceOut:
    """Add a user by hand, then import their statements for them."""
    try:
        space = create_space(session, body.name)
    except SpaceError as exc:
        raise HTTPException(400, str(exc)) from None
    session.commit()
    return SpaceOut(id=space.id, name=space.name, account_count=0, transaction_count=0)


@app.delete("/api/spaces/{space_id}", status_code=204)
def delete_space(space_id: int, session: SessionDep) -> None:
    """Remove a user who has no account (move or delete their statements first)."""
    space = session.get(Space, space_id)
    if space is None:
        raise HTTPException(404, "Utilisateur introuvable")
    if session.exec(select(Account.id).where(Account.space_id == space_id)).first() is not None:
        raise HTTPException(400, "Cet utilisateur a encore des comptes : déplacez-les ou supprimez ses relevés d'abord.")
    space.manual = False  # hidden; kept so its rules and corrections stay attached if the holder comes back
    session.add(space)
    session.commit()


@app.patch("/api/spaces/{space_id}", response_model=SpaceOut)
def rename_space(space_id: int, body: SpaceUpdate, session: SessionDep) -> SpaceOut:
    space = session.get(Space, space_id)
    if space is None:
        raise HTTPException(404, "Utilisateur introuvable")
    space.name = " ".join(body.name.split())
    session.add(space)
    session.commit()
    return next(s for s in list_spaces(session) if s.id == space_id)


# ---------------------------------------------------------------- uploads
@app.post("/api/uploads", response_model=list[ImportResultOut])
def upload(
    session: SessionDep,
    files: Annotated[list[UploadFile], File()],
    space_id: Annotated[int | None, Form()] = None,
    fallback_space_id: Annotated[int | None, Form()] = None,
) -> list[dict]:
    """Import one or several statement PDFs. Each file gets its own result, an error never aborts the batch.

    ``space_id`` (optional): the user these statements belong to, chosen in the app. Without it, the holder read
    on each statement decides (a new holder gets a new user). ``fallback_space_id``: the user shown in the app,
    for files whose holder cannot be known (unreadable or unsupported documents)."""
    for sid in (space_id, fallback_space_id):
        if sid is not None and session.get(Space, sid) is None:
            raise HTTPException(404, "Utilisateur introuvable")
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    results = []
    for f in files:
        name = f.filename or "statement.pdf"
        content = f.file.read(max_bytes + 1)
        if len(content) > max_bytes:
            results.append(ImportResult(name, "rejected", error=f"File larger than {max_bytes // 1024 // 1024} MB."))
        elif not content.startswith(b"%PDF"):
            results.append(ImportResult(name, "rejected", error="Not a PDF file."))
        else:
            results.append(import_pdf(session, name, content, space_id, fallback_space_id))
    return [r.to_dict() for r in results]


# ---------------------------------------------------------------- files
def _file_out(record: StatementFile, count: int) -> FileOut:
    return FileOut(**record.model_dump(exclude={"sha256", "stored_path", "parser_version"}), transaction_count=count)


@app.get("/api/files", response_model=list[FileOut])
def list_files(session: SessionDep, space_id: SpaceId = None) -> list[FileOut]:
    """Statement files of a user (every file belongs to exactly one)."""
    counts = dict(
        session.exec(
            select(TransactionSource.file_id, func.count()).group_by(TransactionSource.file_id)
        ).all()
    )
    stmt = select(StatementFile)
    if space_id is not None:
        stmt = stmt.where(StatementFile.space_id == space_id)
    records = session.exec(
        stmt.order_by(col(StatementFile.statement_date).desc(), col(StatementFile.id).desc())
    ).all()
    return [_file_out(r, counts.get(r.id, 0)) for r in records]


@app.delete("/api/files/{file_id}", status_code=204)
def delete_file(file_id: int, session: SessionDep) -> None:
    record = session.get(StatementFile, file_id)
    if record is None:
        raise HTTPException(404, "File not found")
    path = get_settings().data_dir / record.stored_path
    remove_file_data(session, file_id)
    session.commit()
    path.unlink(missing_ok=True)


def _reparse(session: Session, record: StatementFile) -> dict:
    path = get_settings().data_dir / record.stored_path
    if not path.exists():
        return ImportResult(record.filename, "failed", file_id=record.id, error="Stored PDF is missing.").to_dict()
    return process(session, record, path.read_bytes()).to_dict()


@app.post("/api/files/{file_id}/reparse", response_model=ImportResultOut)
def reparse_file(file_id: int, session: SessionDep) -> dict:
    record = session.get(StatementFile, file_id)
    if record is None:
        raise HTTPException(404, "File not found")
    return _reparse(session, record)


@app.post("/api/files/reparse-all", response_model=list[ImportResultOut])
def reparse_all(session: SessionDep) -> list[dict]:
    """Re-run the parser on every stored PDF (useful after upgrading bankparse)."""
    return [_reparse(session, r) for r in session.exec(select(StatementFile)).all()]


# ---------------------------------------------------------------- accounts
@app.get("/api/accounts", response_model=list[AccountOut])
def list_accounts(session: SessionDep, space_id: SpaceId = None) -> list[AccountOut]:
    stats = {
        row[0]: row[1:]
        for row in session.exec(
            select(
                Transaction.account_id,
                func.count(),
                func.min(Transaction.operation_date),
                func.max(Transaction.operation_date),
            ).group_by(Transaction.account_id)
        ).all()
    }
    out = []
    stmt = select(Account) if space_id is None else select(Account).where(Account.space_id == space_id)
    for acc in session.exec(stmt.order_by(Account.bank_code, Account.label)).all():
        last = session.exec(
            select(Balance).where(Balance.account_id == acc.id).order_by(col(Balance.date).desc())
        ).first()
        count, first_op, last_op = stats.get(acc.id, (0, None, None))
        out.append(
            AccountOut(
                id=acc.id,
                bank_code=acc.bank_code,
                bank=acc.bank,
                account_number=acc.account_number,
                label=account_label(acc),
                statement_label=acc.label,
                owner=acc.owner,
                space_id=acc.space_id,
                transaction_count=count,
                first_operation=first_op,
                last_operation=last_op,
                last_balance=last.amount_cents / 100 if last else None,
                last_balance_date=last.date if last else None,
            )
        )
    return out


@app.patch("/api/accounts/{account_id}", response_model=AccountOut)
def update_account(account_id: int, body: AccountUpdate, session: SessionDep) -> AccountOut:
    acc = session.get(Account, account_id)
    if acc is None:
        raise HTTPException(404, "Account not found")
    if "label" in body.model_fields_set:
        acc.custom_label = (body.label or "").strip() or None
    if body.space_id is not None and body.space_id != acc.space_id:
        if session.get(Space, body.space_id) is None:
            raise HTTPException(404, "Utilisateur introuvable")
        move_account(session, acc, body.space_id)
    session.add(acc)
    session.commit()
    return next(a for a in list_accounts(session) if a.id == account_id)


@app.get("/api/accounts/{account_id}/balances", response_model=list[BalanceOut])
def account_balances(account_id: int, session: SessionDep) -> list[BalanceOut]:
    rows = session.exec(select(Balance).where(Balance.account_id == account_id).order_by(Balance.date)).all()
    return [BalanceOut(date=b.date, amount=b.amount_cents / 100) for b in rows]


# ---------------------------------------------------------------- transactions
def _tx_out(tx: Transaction, acc: Account) -> TransactionOut:
    return TransactionOut(
        id=tx.id,
        account_id=acc.id,
        account_label=account_label(acc),
        bank_code=acc.bank_code,
        operation_date=tx.operation_date,
        value_date=tx.value_date,
        label=tx.label,
        amount=tx.amount_cents / 100,
        category=tx.category,
        category_source=tx.category_source,
        category_model=tx.category_model,
    )


@app.get("/api/transactions", response_model=TransactionPage)
def list_transactions(
    session: SessionDep,
    filters: FiltersDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
    sort: SortField = "operation_date",
    order: Literal["asc", "desc"] = "desc",
) -> TransactionPage:
    base = filtered_query(filters).subquery()
    total, credit, debit = session.exec(
        select(
            func.count(),
            func.coalesce(func.sum(base.c.amount_cents).filter(base.c.amount_cents > 0), 0),
            func.coalesce(func.sum(base.c.amount_cents).filter(base.c.amount_cents < 0), 0),
        ).select_from(base)
    ).one()
    stmt = order_by(filtered_query(filters), sort, order).offset((page - 1) * page_size).limit(page_size)
    items = [_tx_out(tx, acc) for tx, acc in session.exec(stmt).all()]
    return TransactionPage(
        items=items, total=total, page=page, page_size=page_size, total_credit=credit / 100, total_debit=debit / 100
    )


@app.get("/api/transactions/export")
def export_transactions(
    session: SessionDep,
    filters: FiltersDep,
    format: Literal["csv", "xlsx", "json"] = "csv",
    sort: SortField = "operation_date",
    order: Literal["asc", "desc"] = "asc",
) -> Response:
    rows = [
        {
            "date_operation": tx.operation_date,
            "date_valeur": tx.value_date,
            "banque": acc.bank,
            "compte": account_label(acc),
            "numero_compte": acc.account_number,
            "libelle": tx.label,
            "montant": tx.amount_cents / 100,
            "categorie": tx.category,
        }
        for tx, acc in session.exec(order_by(filtered_query(filters), sort, order)).all()
    ]
    df = pd.DataFrame(rows, columns=["date_operation", "date_valeur", "banque", "compte", "numero_compte",
                                     "libelle", "montant", "categorie"])
    if format == "json":
        body = json.dumps(rows, ensure_ascii=False, indent=2, default=lambda d: d.isoformat())
        return Response(body, media_type="application/json", headers=_attachment("operations.json"))
    if format == "xlsx":
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False, sheet_name="Opérations")
        return Response(
            buffer.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=_attachment("operations.xlsx"),
        )
    # CSV for French Excel: ";" separator, decimal comma, UTF-8 with BOM.
    body = df.to_csv(index=False, sep=";", decimal=",")
    return Response("﻿" + body, media_type="text/csv; charset=utf-8", headers=_attachment("operations.csv"))


def _attachment(filename: str) -> dict:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


# ---------------------------------------------------------------- summary
@app.get("/api/summary", response_model=Summary)
def summary(session: SessionDep, space_id: SpaceId = None) -> Summary:
    def in_space(stmt):
        if space_id is None:
            return stmt
        return stmt.join(Account, col(Transaction.account_id) == col(Account.id)).where(Account.space_id == space_id)

    month = func.strftime("%Y-%m", Transaction.operation_date)
    months = session.exec(
        in_space(
            select(
                month,
                func.coalesce(func.sum(Transaction.amount_cents).filter(Transaction.amount_cents > 0), 0),
                func.coalesce(func.sum(Transaction.amount_cents).filter(Transaction.amount_cents < 0), 0),
            ).select_from(Transaction)
        )
        .group_by(month)
        .order_by(month)
    ).all()
    first_op, last_op, n_tx = session.exec(
        in_space(
            select(
                func.min(Transaction.operation_date), func.max(Transaction.operation_date), func.count(Transaction.id)
            ).select_from(Transaction)
        )
    ).one()
    accounts = select(func.count(Account.id))
    files = select(func.count(StatementFile.id))
    if space_id is not None:
        accounts = accounts.where(Account.space_id == space_id)
        files = files.where(StatementFile.space_id == space_id)
    return Summary(
        accounts=session.exec(accounts).one(),
        transactions=n_tx,
        files=session.exec(files.where(StatementFile.status == "parsed")).one(),
        files_total=session.exec(files).one(),
        first_operation=first_op,
        last_operation=last_op,
        months=[MonthTotal(month=m, credit=c / 100, debit=d / 100) for m, c, d in months],
    )
