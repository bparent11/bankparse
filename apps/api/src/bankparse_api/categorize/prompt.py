"""Prompts sent to the local LLM.

One operation per request, with its context (account, date, direction, amount). The guidance comes from the
user: the description of each category (editable on the Catégories page) and every operation the user
categorized by hand, given as an example with its context and optional explanation. There is deliberately
no hand-written rule such as "a credit is income": the model uses the context and its own judgement.

The system prompt is identical for every operation of a run, so Ollama can reuse its cached computation and
only processes the short operation message.
"""

import datetime as dt
from dataclasses import dataclass

UNKNOWN = "Inconnu"
MAX_EXAMPLES = 40

# Starting descriptions, copied into the database on first start; the user edits them afterwards.
DEFAULT_CATEGORIES: dict[str, str] = {
    "Alimentation": "supermarchés, épiceries, boulangeries, marchés",
    "Restaurants": "restaurants, cafés, bars, fast-food, livraison de repas",
    "Logement": "loyer, charges, électricité, gaz, eau, assurance habitation, travaux",
    "Transport": "train, avion, métro, bus, taxi, VTC, carburant, péage, parking, vélo",
    "Santé": "pharmacie, médecin, dentiste, mutuelle, hôpital",
    "Loisirs": "sport, cinéma, concerts, sorties, jeux, livres, culture",
    "Shopping": "vêtements, électronique, maison, cadeaux, achats en ligne",
    "Abonnements": "téléphone, internet, streaming, presse, logiciels, salle de sport",
    "Voyages": "hôtels, locations de vacances, agences de voyage, séjours",
    "Revenus": "salaire, bourses, aides, primes, intérêts",
    "Virements internes": "virements entre ses propres comptes ou vers soi-même",
    "Épargne": "versements sur livret, placements, assurance vie",
    "Impôts": "impôts, taxes, amendes, administration",
    "Frais bancaires": "frais facturés par la banque : cotisation de carte, tenue de compte, agios, commissions",
    "Autre": "opération identifiable qui n'entre dans aucune autre catégorie",
    UNKNOWN: "opération impossible à interpréter avec certitude",
}


@dataclass(frozen=True)
class Example:
    """An operation categorized by the user, with its context and optional explanation."""

    label: str
    amount: float | None  # signed, None when unknown
    category: str
    reason: str | None
    account: str | None = None  # e.g. "Compte Chèque (Crédit Agricole)"
    date: dt.date | None = None


@dataclass(frozen=True)
class Operation:
    label: str
    amount: float  # signed
    date: dt.date
    account: str | None = None


def _amount(value: float) -> str:
    return f"{'crédit' if value > 0 else 'débit'} de {abs(value):.2f} EUR"


def _context(account: str | None, date: dt.date | None, amount: float | None) -> str:
    parts = [p for p in (account, f"le {date:%d/%m/%Y}" if date else None,
                         _amount(amount) if amount is not None else None) if p]
    return f" ({', '.join(parts)})" if parts else ""


def system_prompt(categories: list[tuple[str, str | None]], examples: list[Example], batch: bool = False) -> str:
    """``categories``: (name, description) pairs in display order. ``batch``: several operations per request."""
    lines = [
        "Tu classes une opération bancaire française (libellé abrégé de relevé) dans une catégorie.",
        "Catégories possibles, avec ce qu'elles signifient pour l'utilisateur :",
    ]
    lines += [f"- {name}" + (f" : {desc}" if desc else "") for name, desc in categories]
    lines += [
        "",
        "Utilise tout le contexte : libellé, compte, date, sens (débit ou crédit) et montant.",
        "Un avoir ou un remboursement d'achat prend la catégorie de l'achat d'origine (ex. avoir SNCF → Transport).",
        f"Si tu ne peux pas savoir, réponds « {UNKNOWN} » plutôt que de deviner.",
        (
            "Tu reçois plusieurs opérations indépendantes : juge chacune séparément, sans t'influencer des autres. "
            'Réponds uniquement en JSON : {"results": [{"id": <id>, "category": "<catégorie>"}, ...]}.'
            if batch
            else 'Réponds uniquement en JSON : {"category": "<catégorie>"}.'
        ),
    ]
    if examples:
        lines += [
            "",
            (
                "Opérations déjà classées par l'utilisateur, avec ses explications éventuelles. Elles montrent ses "
                "habitudes : inspire-t'en pour des situations comparables, en gardant ton propre jugement."
            ),
        ]
        for ex in examples[:MAX_EXAMPLES]:
            reason = f" — explication : {ex.reason}" if ex.reason else ""
            lines.append(f"- « {ex.label} »{_context(ex.account, ex.date, ex.amount)} → {ex.category}{reason}")
    return "\n".join(lines)


def user_prompt(op: Operation) -> str:
    return f"Opération à classer : « {op.label} »{_context(op.account, op.date, op.amount)}"


def batch_prompt(ops: list[Operation]) -> str:
    """Numbered operations (ids 1..n) for a batch request."""
    lines = ["Opérations à classer :"]
    lines += [f"{i}. « {op.label} »{_context(op.account, op.date, op.amount)}" for i, op in enumerate(ops, start=1)]
    return "\n".join(lines)
