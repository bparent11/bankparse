import datetime as dt
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, col, select

from bankparse_api.categorize import runner, service
from bankparse_api.categorize.prompt import UNKNOWN
from bankparse_api.config import get_settings
from bankparse_api.db import get_session
from bankparse_api.models import Account, CategorizationJob, Category, Space, Transaction
from bankparse_api.queries import SpaceId, TransactionFilters, filtered_query, transaction_filters

router = APIRouter(prefix="/api", tags=["categorization"])
SessionDep = Annotated[Session, Depends(get_session)]


class CategoryOut(BaseModel):
    id: int
    name: str
    description: str | None
    is_system: bool
    transaction_count: int


class CategoryIn(BaseModel):
    name: str


class CategoryPatch(BaseModel):
    name: str | None = None
    description: str | None = Field(default=None, max_length=300)


class InstalledModelOut(BaseModel):
    name: str
    size_gb: float


class CategorizeStatus(BaseModel):
    ollama_ok: bool
    reason: str | None
    models: list[InstalledModelOut]  # installed Ollama models, smallest first
    default_model: str | None  # suggested for precise runs (BANKPARSE_OLLAMA_MODEL when installed)
    fast_model: str | None  # suggested for fast runs: a smaller model (BANKPARSE_OLLAMA_FAST_MODEL when installed)
    missing_models: list[str]  # suggested models that are not installed (shown with the "ollama pull" command)
    default_batch_size: int  # fast (10) for a first run, precise (1) afterwards
    never_categorized: bool  # no operation was ever categorized by a model
    uncategorized: int
    unknown: int
    to_review: int  # proposed by the LLM, not yet validated


class CategorizeStart(BaseModel):
    model: str
    mode: Literal["new", "all"] = "new"
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    batch_size: int = Field(default=1, ge=1, le=20)  # 1 = precise, 10 = fast
    space_id: int | None = None  # operations of this space only (None: every space)


class CategorizeCount(BaseModel):
    count: int


class CategorizationJobOut(BaseModel):
    id: int
    status: Literal["running", "done", "failed", "cancelled"]
    mode: str | None
    model: str | None
    batch_size: int | None
    date_from: dt.date | None
    date_to: dt.date | None
    total: int
    done: int
    merchants_total: int
    merchants_done: int
    space_id: int | None
    message: str | None
    started_at: dt.datetime
    finished_at: dt.datetime | None


class CategoryUpdate(BaseModel):
    category: str
    reason: str | None = Field(default=None, max_length=300)  # the user's explanation, given to the LLM
    apply_to_similar: bool = False


class CategoryUpdateResult(BaseModel):
    updated: int


class ValidationIn(BaseModel):
    validated: bool = True


class SimilarOut(BaseModel):
    count: int  # other operations with a similar label
    examples: list[str]  # a few distinct labels among them


# ---------------------------------------------------------------- categories
@router.get("/categories", response_model=list[CategoryOut])
def list_categories(session: SessionDep, space_id: SpaceId = None) -> list[CategoryOut]:
    """Categories are shared by every space; the operation counts are those of ``space_id``."""
    stmt = select(Transaction.category, func.count()).where(col(Transaction.category).is_not(None))
    if space_id is not None:
        stmt = stmt.join(Account, col(Transaction.account_id) == col(Account.id)).where(Account.space_id == space_id)
    counts = dict(session.exec(stmt.group_by(Transaction.category)).all())
    categories = session.exec(select(Category).order_by(Category.position, Category.id)).all()
    return [
        CategoryOut(
            id=c.id,
            name=c.name,
            description=c.description,
            is_system=c.is_system,
            transaction_count=counts.get(c.name, 0),
        )
        for c in categories
    ]


@router.post("/categories", response_model=CategoryOut, status_code=201)
def create_category(body: CategoryIn, session: SessionDep) -> CategoryOut:
    try:
        c = service.create_category(session, body.name)
    except service.CategoryError as exc:
        raise HTTPException(400, str(exc)) from None
    return CategoryOut(id=c.id, name=c.name, description=c.description, is_system=c.is_system, transaction_count=0)


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def update_category(category_id: int, body: CategoryPatch, session: SessionDep) -> CategoryOut:
    """Rename and/or describe a category (the description is given to the LLM)."""
    category = session.get(Category, category_id)
    if category is None:
        raise HTTPException(404, "Catégorie introuvable")
    try:
        if body.name is not None and body.name.strip() != category.name:
            service.rename_category(session, category, body.name)
        if "description" in body.model_fields_set:
            service.set_description(session, category, body.description)
    except service.CategoryError as exc:
        raise HTTPException(400, str(exc)) from None
    return next(c for c in list_categories(session) if c.id == category_id)


@router.delete("/categories/{category_id}", status_code=204)
def delete_category(category_id: int, session: SessionDep) -> None:
    category = session.get(Category, category_id)
    if category is None:
        raise HTTPException(404, "Catégorie introuvable")
    try:
        service.delete_category(session, category)
    except service.CategoryError as exc:
        raise HTTPException(400, str(exc)) from None


# ---------------------------------------------------------------- manual correction
@router.patch("/transactions/{transaction_id}/category", response_model=CategoryUpdateResult)
def set_transaction_category(transaction_id: int, body: CategoryUpdate, session: SessionDep) -> CategoryUpdateResult:
    tx = session.get(Transaction, transaction_id)
    if tx is None:
        raise HTTPException(404, "Opération introuvable")
    try:
        updated = service.set_category(session, tx, body.category, body.reason, body.apply_to_similar)
    except service.CategoryError as exc:
        raise HTTPException(400, str(exc)) from None
    return CategoryUpdateResult(updated=updated)


@router.get("/transactions/{transaction_id}/similar", response_model=SimilarOut)
def similar_transactions(transaction_id: int, session: SessionDep) -> SimilarOut:
    """Operations with a similar label (shown before applying a correction to them too)."""
    tx = session.get(Transaction, transaction_id)
    if tx is None:
        raise HTTPException(404, "Opération introuvable")
    similar = service.similar_transactions(session, tx)
    labels = list(dict.fromkeys(t.label for t in similar if t.label != tx.label))[:3]
    return SimilarOut(count=len(similar), examples=labels or [t.label for t in similar[:1]])


# ---------------------------------------------------------------- validation of the LLM's proposals
@router.post("/transactions/{transaction_id}/validation", response_model=CategoryUpdateResult)
def validate_transaction(transaction_id: int, body: ValidationIn, session: SessionDep) -> CategoryUpdateResult:
    """Validate (or un-validate) the category the LLM proposed for one operation."""
    if session.get(Transaction, transaction_id) is None:
        raise HTTPException(404, "Opération introuvable")
    return CategoryUpdateResult(updated=service.set_validated(session, [transaction_id], body.validated))


@router.post("/transactions/validation", response_model=CategoryUpdateResult)
def validate_filtered(session: SessionDep, filters: Annotated[TransactionFilters, Depends(transaction_filters)]):
    """Validate every LLM proposal matching the same filters as the operations list."""
    filters.to_review = True
    ids = [tx.id for tx, _ in session.exec(filtered_query(filters)).all()]
    return CategoryUpdateResult(updated=service.set_validated(session, ids, True))


# ---------------------------------------------------------------- LLM job
@router.get("/categorize/status", response_model=CategorizeStatus)
def categorize_status(session: SessionDep, space_id: SpaceId = None) -> CategorizeStatus:
    status = runner.client_factory().status()
    names = [m.name for m in status.models]
    settings = get_settings()

    def count(*conditions) -> int:
        stmt = select(func.count()).select_from(Transaction).where(*conditions)
        if space_id is not None:
            stmt = stmt.join(Account, col(Transaction.account_id) == col(Account.id)).where(
                Account.space_id == space_id
            )
        return session.exec(stmt).one()

    never = count(Transaction.category_source == "llm") == 0

    def installed(preferred: str, fallback: str | None) -> str | None:
        return next((n for n in (preferred, f"{preferred}:latest") if n in names), fallback)

    # Models are sorted smallest first: fall back to the largest for precise runs, the smallest for fast ones.
    default = installed(settings.ollama_model, names[-1] if names else None)
    fast = installed(settings.ollama_fast_model, names[0] if names else None)
    return CategorizeStatus(
        ollama_ok=status.ok,
        reason=status.reason,
        models=[InstalledModelOut(name=m.name, size_gb=m.size_gb) for m in status.models],
        default_model=default,
        fast_model=fast,
        missing_models=[
            m for m in dict.fromkeys((settings.ollama_fast_model, settings.ollama_model))
            if status.ok and m not in names and f"{m}:latest" not in names
        ],
        default_batch_size=10 if never else 1,
        never_categorized=never,
        uncategorized=count(col(Transaction.category).is_(None)),
        unknown=count(Transaction.category == UNKNOWN),
        to_review=count(col(Transaction.category_source).in_(runner.TO_REVIEW_SOURCES)),
    )


@router.get("/categorize/count", response_model=CategorizeCount)
def categorize_count(
    session: SessionDep,
    mode: Literal["new", "all"] = "new",
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    space_id: SpaceId = None,
) -> CategorizeCount:
    """How many operations a run with these options would process."""
    query = runner.candidates_query(mode, date_from, date_to, space_id).subquery()
    return CategorizeCount(count=session.exec(select(func.count()).select_from(query)).one())


@router.post("/categorize", response_model=CategorizationJobOut, status_code=202)
def start_categorization(body: CategorizeStart, session: SessionDep) -> CategorizationJob:
    installed = {m.name for m in runner.client_factory().status().models}
    if body.model not in installed:
        raise HTTPException(400, f"Modèle {body.model} non installé dans Ollama.")
    if body.space_id is not None and session.get(Space, body.space_id) is None:
        raise HTTPException(404, "Utilisateur introuvable")
    try:
        job_id = runner.start_job(
            body.model, body.mode, body.date_from, body.date_to, body.batch_size, space_id=body.space_id
        )
    except runner.JobAlreadyRunning:
        # Ollama runs one model at a time on this computer: one run at once, whatever the space.
        raise HTTPException(409, "Une catégorisation est déjà en cours (peut-être pour un autre utilisateur).") from None
    return session.get(CategorizationJob, job_id)


@router.get("/categorize/jobs/latest", response_model=CategorizationJobOut | None)
def latest_job(session: SessionDep, space_id: SpaceId = None) -> CategorizationJob | None:
    stmt = select(CategorizationJob)
    if space_id is not None:
        stmt = stmt.where(CategorizationJob.space_id == space_id)
    return session.exec(stmt.order_by(col(CategorizationJob.id).desc())).first()


@router.post("/categorize/jobs/{job_id}/cancel", status_code=202)
def cancel_job(job_id: int) -> dict:
    if not runner.request_cancel(job_id):
        raise HTTPException(409, "Aucune catégorisation en cours avec cet identifiant.")
    return {"status": "cancelling"}
