"""Background categorization job: every operation is judged on its own by the chosen local model.

Nothing the model answers is copied to other operations. Only the user's own choices are reused: as
examples in the prompt, and, when the user ticked "apply to similar operations", as rules.
"""

from __future__ import annotations

import datetime as dt
import logging
import threading

from sqlmodel import Session, col, select

from bankparse_api.categorize import service
from bankparse_api.categorize.ollama import LLMError, OllamaClient
from bankparse_api.categorize.prompt import UNKNOWN, Operation, batch_prompt, system_prompt, user_prompt
from bankparse_api.db import get_engine
from bankparse_api.models import Account, CategorizationJob, Transaction, utcnow

log = logging.getLogger(__name__)

MODES = ("new", "all")  # never categorized | everything except the user's own choices
USER_SOURCES = ("user", "rule", "validated")  # never sent to the model again
TO_REVIEW_SOURCES = ("llm", "memory")  # proposed by the model, not yet validated by the user
_start_lock = threading.Lock()

# Replaced by a fake in tests.
client_factory = OllamaClient


class JobAlreadyRunning(Exception):
    pass


def active_job(session: Session) -> CategorizationJob | None:
    return session.exec(select(CategorizationJob).where(CategorizationJob.status == "running")).first()


def mark_interrupted_jobs() -> None:
    with Session(get_engine()) as session:
        for job in session.exec(select(CategorizationJob).where(CategorizationJob.status == "running")).all():
            job.status, job.message, job.finished_at = "failed", "Interrompu (serveur arrêté).", utcnow()
            session.add(job)
        session.commit()


def candidates_query(
    mode: str, date_from: dt.date | None = None, date_to: dt.date | None = None, space_id: int | None = None
):
    """Operations a run will process (also used to show the count before starting)."""
    stmt = select(Transaction)
    if space_id is not None:
        stmt = stmt.join(Account, col(Transaction.account_id) == col(Account.id)).where(Account.space_id == space_id)
    if mode == "new":
        stmt = stmt.where(col(Transaction.category).is_(None))
    else:  # "all": everything the user did not choose by hand
        stmt = stmt.where(
            col(Transaction.category_source).is_(None) | col(Transaction.category_source).not_in(USER_SOURCES)
        )
    if date_from:
        stmt = stmt.where(Transaction.operation_date >= date_from)
    if date_to:
        stmt = stmt.where(Transaction.operation_date <= date_to)
    return stmt.order_by(col(Transaction.operation_date).desc(), col(Transaction.id).desc())


def start_job(
    model: str,
    mode: str = "new",
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    batch_size: int = 1,
    background: bool = True,
    space_id: int | None = None,
) -> int:
    if mode not in MODES:
        raise ValueError(mode)
    with _start_lock, Session(get_engine()) as session:
        if active_job(session) is not None:
            raise JobAlreadyRunning()
        job = CategorizationJob(
            mode=mode, model=model, date_from=date_from, date_to=date_to, batch_size=max(1, min(batch_size, 20)),
            include_unknown=mode == "all",
            space_id=space_id,
            message="Préparation…",
        )
        session.add(job)
        session.commit()
        job_id = job.id
    if background:
        threading.Thread(target=run_job, args=(job_id,), name=f"categorize-{job_id}", daemon=True).start()
    else:
        run_job(job_id)
    return job_id


def request_cancel(job_id: int) -> bool:
    with Session(get_engine()) as session:
        job = session.get(CategorizationJob, job_id)
        if job is None or job.status != "running":
            return False
        job.cancel_requested = True
        session.add(job)
        session.commit()
        return True


def run_job(job_id: int) -> None:
    with Session(get_engine()) as session:
        job = session.get(CategorizationJob, job_id)
        if job is None:
            return

        def save(message: str | None = None, **fields) -> None:
            for key, value in fields.items():
                setattr(job, key, value)
            if message is not None:
                job.message = message
            session.add(job)
            session.commit()

        try:
            mode = job.mode or "new"
            operations = list(session.exec(candidates_query(mode, job.date_from, job.date_to, job.space_id)).all())
            save(total=len(operations), message="Préparation…")
            if not operations:
                save("Rien à catégoriser pour ce choix.", status="done", finished_at=utcnow())
                return

            # The user's "apply to similar operations" choices: no LLM call needed.
            rules = service.rules_for(session, operations)
            to_ask = []
            for tx in operations:
                rule = rules.get(tx.id)
                if rule is not None:
                    tx.category, tx.category_source, tx.category_model = rule.category, "rule", None
                    session.add(tx)
                    job.done += 1
                else:
                    to_ask.append(tx)
            save(merchants_total=len(to_ask))

            client = client_factory()
            size = job.batch_size or 1
            categories = service.category_names(session)
            system = system_prompt(service.category_infos(session), service.user_examples(session, job.space_id), batch=size > 1)
            accounts = service.account_names(session)

            def operation(tx: Transaction) -> Operation:
                return Operation(tx.label, tx.amount_cents / 100, tx.operation_date, accounts.get(tx.account_id))

            for start in range(0, len(to_ask), size):
                session.refresh(job, ["cancel_requested"])
                if job.cancel_requested:
                    save(f"Annulé : {job.done}/{job.total} opérations traitées.", status="cancelled",
                         finished_at=utcnow())
                    return
                chunk = to_ask[start : start + size]
                if size == 1:
                    answers = {1: client.classify(job.model, system, user_prompt(operation(chunk[0])), categories)}
                else:  # each operation still gets its own answer: nothing is copied between them
                    ids = list(range(1, len(chunk) + 1))
                    answers = client.classify_batch(
                        job.model, system, batch_prompt([operation(t) for t in chunk]), categories, ids
                    )
                for i, tx in enumerate(chunk, start=1):
                    tx.category = answers.get(i) or UNKNOWN  # missing or invalid answer -> Inconnu
                    tx.category_source, tx.category_model = "llm", job.model
                    session.add(tx)
                job.done += len(chunk)
                job.merchants_done += len(chunk)
                if size > 1 or job.merchants_done % 5 == 0 or job.merchants_done == len(to_ask):
                    save(f"{job.merchants_done}/{len(to_ask)} opérations analysées par {job.model}…")

            save(f"Terminé : {job.done} opérations catégorisées avec {job.model}.", status="done",
                 finished_at=utcnow())
        except LLMError as exc:
            session.commit()  # keep what was already categorized
            save(f"{exc} Les opérations déjà traitées sont conservées.", status="failed", finished_at=utcnow())
        except Exception:  # report and keep the server alive
            session.rollback()
            log.exception("categorization job %s failed", job_id)
            save("Erreur inattendue (voir les logs du serveur).", status="failed", finished_at=utcnow())
