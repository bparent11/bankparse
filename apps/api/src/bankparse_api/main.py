import io
import json
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import pandas as pd
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import func
from sqlmodel import Session, col, select

from bankparse_api.config import get_settings
from bankparse_api.db import get_engine, get_session
from bankparse_api.ingest import ImportResult, import_pdf, process, remove_file_data
from bankparse_api.models import Account, Balance, StatementFile, Transaction, TransactionSource
from bankparse_api.queries import (
    SortField,
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
    Summary,
    TransactionOut,
    TransactionPage,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_engine()  # create the data folder and the tables
    yield


app = FastAPI(
    title="bankparse",
    version="0.1.0",
    description="Import French bank statements and browse operations.",
    lifespan=lifespan,
)

SessionDep = Annotated[Session, Depends(get_session)]
FiltersDep = Annotated[TransactionFilters, Depends(transaction_filters)]


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------- uploads
@app.post("/api/uploads", response_model=list[ImportResultOut])
def upload(session: SessionDep, files: Annotated[list[UploadFile], File()]) -> list[dict]:
    """Import one or several statement PDFs. Each file gets its own result, an error never aborts the batch."""
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
            results.append(import_pdf(session, name, content))
    return [r.to_dict() for r in results]


# ---------------------------------------------------------------- files
def _file_out(record: StatementFile, count: int) -> FileOut:
    return FileOut(**record.model_dump(exclude={"sha256", "stored_path", "parser_version"}), transaction_count=count)


@app.get("/api/files", response_model=list[FileOut])
def list_files(session: SessionDep) -> list[FileOut]:
    counts = dict(
        session.exec(
            select(TransactionSource.file_id, func.count()).group_by(TransactionSource.file_id)
        ).all()
    )
    records = session.exec(
        select(StatementFile).order_by(col(StatementFile.statement_date).desc(), col(StatementFile.id).desc())
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
def list_accounts(session: SessionDep) -> list[AccountOut]:
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
    for acc in session.exec(select(Account).order_by(Account.bank_code, Account.label)).all():
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
    acc.custom_label = (body.label or "").strip() or None
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
def summary(session: SessionDep) -> Summary:
    month = func.strftime("%Y-%m", Transaction.operation_date)
    months = session.exec(
        select(
            month,
            func.coalesce(func.sum(Transaction.amount_cents).filter(Transaction.amount_cents > 0), 0),
            func.coalesce(func.sum(Transaction.amount_cents).filter(Transaction.amount_cents < 0), 0),
        )
        .group_by(month)
        .order_by(month)
    ).all()
    first_op, last_op, n_tx = session.exec(
        select(func.min(Transaction.operation_date), func.max(Transaction.operation_date), func.count(Transaction.id))
    ).one()
    return Summary(
        accounts=session.exec(select(func.count(Account.id))).one(),
        transactions=n_tx,
        files=session.exec(select(func.count(StatementFile.id)).where(StatementFile.status == "parsed")).one(),
        files_total=session.exec(select(func.count(StatementFile.id))).one(),
        first_operation=first_op,
        last_operation=last_op,
        months=[MonthTotal(month=m, credit=c / 100, debit=d / 100) for m, c, d in months],
    )
