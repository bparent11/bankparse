"""Categories, the user's corrections and similar-label rules (no LLM here)."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import delete, update
from sqlmodel import Session, col, select

from bankparse_api.categorize.merchant import merchant_key
from bankparse_api.categorize.prompt import DEFAULT_CATEGORIES, UNKNOWN, Example
from bankparse_api.models import Account, Category, Correction, MerchantRule, Transaction, utcnow
from bankparse_api.spaces import space_of_transaction


class CategoryError(ValueError):
    """Invalid category operation, with a message for the user."""


# ---------------------------------------------------------------- categories
def seed_categories(session: Session) -> None:
    """Create the default categories on first start, make sure Inconnu exists, and give the default
    categories their starting description when they have none (databases created before descriptions)."""
    existing = {c.name: c for c in session.exec(select(Category)).all()}
    if not existing:
        for position, (name, description) in enumerate(DEFAULT_CATEGORIES.items()):
            session.add(Category(name=name, position=position, is_system=name == UNKNOWN, description=description))
    else:
        if UNKNOWN not in existing:
            session.add(Category(name=UNKNOWN, position=10_000, is_system=True))
        for name, category in existing.items():
            if category.description is None and name in DEFAULT_CATEGORIES:
                category.description = DEFAULT_CATEGORIES[name]
                session.add(category)
    session.commit()


def forget_llm_memory(session: Session) -> None:
    """Earlier versions copied an LLM answer to every operation with a similar label. Only the user's own
    rules are kept now; the operations keep their category until they are categorized again."""
    session.execute(delete(MerchantRule).where(MerchantRule.source != "user"))
    session.commit()


def backfill_corrections(session: Session) -> int:
    """Manual choices made before corrections were recorded become corrections (without explanation),
    so they keep guiding the LLM. Idempotent."""
    recorded = set(session.exec(select(Correction.transaction_id)).all())
    added = 0
    for tx in session.exec(select(Transaction).where(Transaction.category_source == "user")).all():
        if tx.id not in recorded and tx.category:
            session.add(
                Correction(
                    transaction_id=tx.id, label=tx.label, amount_cents=tx.amount_cents, category=tx.category,
                    space_id=space_of_transaction(session, tx.id),
                )
            )
            added += 1
    session.commit()
    return added


def category_names(session: Session) -> list[str]:
    return list(session.exec(select(Category.name).order_by(Category.position, Category.id)).all())


def category_infos(session: Session) -> list[tuple[str, str | None]]:
    """(name, description) pairs in display order, for the LLM prompt."""
    return [(c.name, c.description) for c in session.exec(select(Category).order_by(Category.position, Category.id))]


def set_description(session: Session, category: Category, description: str | None) -> Category:
    category.description = " ".join((description or "").split())[:300] or None
    session.add(category)
    session.commit()
    session.refresh(category)
    return category


def create_category(session: Session, name: str) -> Category:
    name = _clean(name)
    if session.exec(select(Category).where(Category.name == name)).first():
        raise CategoryError(f"La catégorie « {name} » existe déjà.")
    last = session.exec(select(Category.position).order_by(col(Category.position).desc())).first() or 0
    category = Category(name=name, position=last + 1)
    session.add(category)
    session.commit()
    session.refresh(category)
    return category


def rename_category(session: Session, category: Category, new_name: str) -> Category:
    new_name = _clean(new_name)
    if category.is_system:
        raise CategoryError(f"« {category.name} » ne peut pas être renommée.")
    if new_name != category.name and session.exec(select(Category).where(Category.name == new_name)).first():
        raise CategoryError(f"La catégorie « {new_name} » existe déjà.")
    old = category.name
    session.execute(update(Transaction).where(Transaction.category == old).values(category=new_name))
    session.execute(update(MerchantRule).where(MerchantRule.category == old).values(category=new_name))
    session.execute(update(Correction).where(Correction.category == old).values(category=new_name))
    category.name = new_name
    session.add(category)
    session.commit()
    session.refresh(category)
    return category


def delete_category(session: Session, category: Category) -> None:
    """Operations and rules of a deleted category fall back to Inconnu."""
    if category.is_system:
        raise CategoryError(f"« {category.name} » ne peut pas être supprimée.")
    session.execute(update(Transaction).where(Transaction.category == category.name).values(category=UNKNOWN))
    session.execute(update(MerchantRule).where(MerchantRule.category == category.name).values(category=UNKNOWN))
    session.execute(update(Correction).where(Correction.category == category.name).values(category=UNKNOWN))
    session.delete(category)
    session.commit()


def _clean(name: str) -> str:
    name = " ".join((name or "").split())
    if not name or len(name) > 40:
        raise CategoryError("Le nom doit faire entre 1 et 40 caractères.")
    return name


# ---------------------------------------------------------------- rules
def rules_by_key(session: Session, space_id: int | None = None) -> dict[str, MerchantRule]:
    """The user's "apply to similar operations" choices in a space (None: every space), by label key."""
    stmt = select(MerchantRule).where(MerchantRule.source == "user")
    if space_id is not None:
        stmt = stmt.where(MerchantRule.space_id == space_id)
    return {r.merchant_key: r for r in session.exec(stmt).all()}


def rules_for(session: Session, transactions: Iterable[Transaction]) -> dict[int, MerchantRule]:
    """Transaction id -> the rule of its own space that covers its label, if any."""
    spaces = dict(session.exec(select(Account.id, Account.space_id)).all())
    rules: dict[int | None, dict[str, MerchantRule]] = {}
    found = {}
    for tx in transactions:
        space_id = spaces.get(tx.account_id)
        if space_id not in rules:
            rules[space_id] = rules_by_key(session, space_id) if space_id is not None else {}
        rule = rules[space_id].get(merchant_key(tx.label))
        if rule is not None:
            found[tx.id] = rule
    return found


def account_names(session: Session) -> dict[int, str]:
    """Account id -> "label (bank)", used as context in the LLM prompt."""
    return {a.id: f"{a.custom_label or a.label} ({a.bank})" for a in session.exec(select(Account)).all()}


def user_examples(session: Session, space_id: int | None = None, limit: int = 40) -> list[Example]:
    """Every manual choice made in a space (None: every space; most recent first, one per label), with the
    operation's context (account, date, amount) and the user's explanation. Given to the LLM as guidance."""
    accounts = account_names(session)
    examples: dict[str, Example] = {}
    corrections = select(Correction)
    if space_id is not None:
        corrections = corrections.where(Correction.space_id == space_id)
    for c in session.exec(corrections.order_by(col(Correction.created_at).desc())).all():
        if c.label in examples:
            continue
        tx = session.get(Transaction, c.transaction_id) if c.transaction_id is not None else None
        examples[c.label] = Example(
            label=c.label,
            amount=c.amount_cents / 100,
            category=c.category,
            reason=c.reason,
            account=accounts.get(tx.account_id) if tx else None,
            date=tx.operation_date if tx else None,
        )
    # Rules created before corrections were recorded (no context nor reason known).
    for r in rules_by_key(session, space_id).values():
        examples.setdefault(r.example_label, Example(r.example_label, None, r.category, None))
    return list(examples.values())[:limit]


def upsert_rule(
    session: Session, space_id: int | None, key: str, category: str, source: str, example_label: str
) -> MerchantRule:
    rule = session.exec(
        select(MerchantRule).where(MerchantRule.merchant_key == key, MerchantRule.space_id == space_id)
    ).first()
    if rule is None:
        rule = MerchantRule(
            space_id=space_id, merchant_key=key, category=category, source=source, example_label=example_label
        )
    else:
        rule.category, rule.source, rule.example_label, rule.updated_at = category, source, example_label, utcnow()
    session.add(rule)
    return rule


def apply_rules(session: Session, transactions: Iterable[Transaction]) -> int:
    """Categorize uncategorized operations covered by one of the user's similar-label choices (in the
    operation's own space)."""
    pending = [tx for tx in transactions if tx.category is None]
    rules = rules_for(session, pending)
    changed = 0
    for tx in pending:
        rule = rules.get(tx.id)
        if rule is not None:
            tx.category = rule.category
            tx.category_source, tx.category_model = "rule", None
            session.add(tx)
            changed += 1
    return changed


# ---------------------------------------------------------------- manual corrections
def similar_transactions(session: Session, tx: Transaction) -> list[Transaction]:
    """Other operations of the same space whose label looks the same (same key: date, card number and
    references ignored)."""
    key = merchant_key(tx.label)
    same_space = (
        select(Transaction)
        .join(Account, col(Transaction.account_id) == col(Account.id))
        .where(Account.space_id == space_of_transaction(session, tx.id))
    )
    return [t for t in session.exec(same_space).all() if t.id != tx.id and merchant_key(t.label) == key]


def set_category(
    session: Session, tx: Transaction, category: str, reason: str | None = None, apply_to_similar: bool = False
) -> int:
    """Manual correction, recorded with its explanation. Returns the number of operations updated."""
    if category not in category_names(session):
        raise CategoryError(f"Catégorie inconnue : {category}")
    reason = " ".join((reason or "").split())[:300] or None
    space_id = space_of_transaction(session, tx.id)

    correction = session.exec(select(Correction).where(Correction.transaction_id == tx.id)).first()
    if correction is None:
        correction = Correction(
            transaction_id=tx.id, label=tx.label, amount_cents=tx.amount_cents, category=category, space_id=space_id
        )
    correction.category, correction.reason = category, reason
    correction.applied_to_similar, correction.created_at = apply_to_similar, utcnow()
    session.add(correction)

    tx.category, tx.category_source, tx.category_model = category, "user", None
    session.add(tx)
    updated = 1
    if apply_to_similar:
        # Remembered for this kind of label: future imports and runs reuse it without the LLM.
        upsert_rule(session, space_id, merchant_key(tx.label), category, "user", tx.label)
        ids = [t.id for t in similar_transactions(session, tx) if t.category_source != "user"]
        if ids:
            session.execute(
                update(Transaction).where(col(Transaction.id).in_(ids)).values(category=category, category_source="rule", category_model=None)
            )
        updated += len(ids)
    session.commit()
    return updated


# ---------------------------------------------------------------- validation of the LLM's proposals
def set_validated(session: Session, ids: list[int], validated: bool) -> int:
    """Validate (or un-validate) categories proposed by the LLM. A validated operation keeps its category
    and the model that proposed it, and is never sent to the model again. Returns how many changed."""
    if not ids:
        return 0
    if validated:
        condition = col(Transaction.category_source).in_(("llm", "memory"))
        new_source = "validated"
    else:
        condition = Transaction.category_source == "validated"
        new_source = "llm"
    result = session.execute(
        update(Transaction)
        .where(col(Transaction.id).in_(ids), condition, col(Transaction.category).is_not(None))
        .values(category_source=new_source)
    )
    session.commit()
    return result.rowcount or 0
