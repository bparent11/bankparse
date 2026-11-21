"""Categorization tests: fake local LLM, fictitious operations, no network."""

import re
from datetime import date

import conftest
import pytest
from bankparse_api.categorize import runner
from bankparse_api.categorize.merchant import merchant_key
from bankparse_api.categorize.ollama import InstalledModel, OllamaStatus
from bankparse_api.db import get_engine
from bankparse_api.models import CategorizationJob, Correction, MerchantRule, Transaction
from conftest import tx
from sqlmodel import Session, delete, select

# --------------------------------------------------------------------------- label key (similar operations)


@pytest.mark.parametrize(
    "label, key",
    [
        ("CARTE X4847 CARREFOUR MARKET 12/03", "CARREFOUR MARKET"),
        ("Carte X8500 SNCF Internet Paris 09/12", "SNCF INTERNET PARIS"),
        ("PAIEMENT CB 0212 57050 MET SAS METZ HANDBAL PAYWEB7944", "MET SAS METZ"),
        ("VIR SEPA LOYER", "LOYER"),
        ("VIR Virement depuis BoursoBank Réf : SCT4061820250807", "DEPUIS BOURSOBANK"),
        ("12345 67890", "12345 67890"),  # nothing meaningful: falls back to the label
    ],
)
def test_merchant_key(label, key):
    assert merchant_key(label) == key


# --------------------------------------------------------------------------- fake LLM

MODELS = [InstalledModel("tiny:1b", 0.8), InstalledModel("gemma4:latest", 6.6)]


class FakeLLM:
    """Answers by keyword found in the operation; records every call."""

    DEFAULT_ANSWERS = {"CAFE": "Restaurants", "LOYER": "Logement", "SALAIRE": "Revenus"}
    answers: dict = {}
    calls: list = []
    on_call = None

    def status(self):
        return OllamaStatus(True, list(MODELS), None)

    def classify(self, model, system, user, categories):
        FakeLLM.calls.append((model, system, user))
        if FakeLLM.on_call:
            FakeLLM.on_call()
        label = re.search(r"« (.+?) »", user).group(1).upper()
        return FakeLLM._answer(label, categories)

    def classify_batch(self, model, system, user, categories, ids):
        FakeLLM.calls.append((model, system, user))
        if FakeLLM.on_call:
            FakeLLM.on_call()
        labels = dict(re.findall(r"^(\d+)\. « (.+?) »", user, flags=re.MULTILINE))
        return {int(i): a for i, label in labels.items() if (a := FakeLLM._answer(label.upper(), categories))}

    @staticmethod
    def _answer(label, categories):
        return next((c for word, c in FakeLLM.answers.items() if word in label and c in categories), None)


@pytest.fixture
def llm(monkeypatch):
    FakeLLM.calls, FakeLLM.on_call, FakeLLM.answers = [], None, dict(FakeLLM.DEFAULT_ANSWERS)
    monkeypatch.setattr(runner, "client_factory", FakeLLM)
    return FakeLLM


@pytest.fixture
def data(client, fake_parser, monkeypatch):
    statements = dict(conftest.STATEMENTS)
    statements[b"%PDF-C"] = [tx(date(2025, 3, 3), "CARTE X9999 CAFE DU COIN 03/03", "-4.20")]
    statements[b"%PDF-D"] = [tx(date(2025, 3, 5), "CARTE X9999 GARAGE MYSTERE 05/03", "-80.00")]
    statements[b"%PDF-E"] = [tx(date(2025, 4, 1), "CARTE X0000 CAFE DU COIN 01/04", "-3.00")]
    monkeypatch.setattr(conftest, "STATEMENTS", statements)
    upload(client, ("a.pdf", b"%PDF-A"), ("b.pdf", b"%PDF-B"))  # 2 coffees, rent, salary
    return client


def upload(client, *files):
    r = client.post("/api/uploads", files=[("files", (n, c, "application/pdf")) for n, c in files])
    assert r.status_code == 200, r.text
    return r.json()


def operations(client, **params):
    items = client.get("/api/transactions", params={"page_size": 100, **params}).json()["items"]
    return {t["label"]: t for t in items}


def run(mode="new", model="tiny:1b", batch_size=1, **dates):
    return runner.start_job(model, mode, batch_size=batch_size, background=False, **dates)


def job(job_id):
    with Session(get_engine()) as s:
        return s.get(CategorizationJob, job_id)


# --------------------------------------------------------------------------- tests


def test_default_categories_have_editable_descriptions(client):
    cats = {c["name"]: c for c in client.get("/api/categories").json()}
    assert "train" in cats["Transport"]["description"]
    unknown = cats["Inconnu"]
    assert unknown["is_system"]
    assert client.patch(f"/api/categories/{unknown['id']}", json={"name": "X"}).status_code == 400
    assert client.delete(f"/api/categories/{unknown['id']}").status_code == 400

    r = client.patch(f"/api/categories/{cats['Logement']['id']}", json={"description": "loyer et colocation"})
    assert r.json()["description"] == "loyer et colocation" and r.json()["name"] == "Logement"


def test_every_operation_is_judged_on_its_own_with_context(data, llm):
    j = job(run())
    assert j.status == "done" and (j.total, j.done, j.merchants_total) == (4, 4, 4)
    assert len(llm.calls) == 4  # one request per operation, even for the two identical coffees
    model, system, user = llm.calls[0]
    assert model == "tiny:1b"
    assert "- Transport : train, avion" in system  # descriptions come from the categories
    assert "avoir ou un remboursement d'achat prend la catégorie de l'achat" in system
    assert "le plus souvent Revenus" not in system  # no hand-written bias anymore
    assert re.search(r"« .+ » \(C/C EUROCOMPTE \(Crédit Mutuel\), le \d\d/\d\d/2025, (débit|crédit) de", user)

    ops = operations(data)
    assert ops["VIR SEPA LOYER"]["category"] == "Logement"
    assert (ops["VIR SALAIRE"]["category_source"], ops["VIR SALAIRE"]["category_model"]) == ("llm", "tiny:1b")

    # Nothing the model said is copied: a new coffee stays uncategorized until the next run.
    upload(data, ("c.pdf", b"%PDF-C"))
    assert operations(data)["CARTE X9999 CAFE DU COIN 03/03"]["category"] is None
    assert job(run()).total == 1


def test_unusable_answer_becomes_unknown(data, llm):
    upload(data, ("d.pdf", b"%PDF-D"))
    run()
    assert operations(data)["CARTE X9999 GARAGE MYSTERE 05/03"]["category"] == "Inconnu"
    assert data.get("/api/categorize/status").json()["unknown"] == 1


def test_mode_all_reruns_everything_but_the_users_choices_with_another_model(data, llm):
    run()
    salary = operations(data)["VIR SALAIRE"]
    r = data.patch(f"/api/transactions/{salary['id']}/category", json={"category": "Autre", "reason": "prime"})
    assert r.json() == {"updated": 1}

    assert data.get("/api/categorize/count", params={"mode": "all"}).json() == {"count": 3}
    llm.answers = {**FakeLLM.DEFAULT_ANSWERS, "CAFE": "Alimentation"}
    j = job(run("all", model="gemma4:latest"))
    assert (j.mode, j.model, j.total) == ("all", "gemma4:latest", 3)
    ops = operations(data)
    coffee = ops["CARTE CAFE DU COIN"]
    assert (coffee["category"], coffee["category_model"]) == ("Alimentation", "gemma4:latest")
    assert (ops["VIR SALAIRE"]["category"], ops["VIR SALAIRE"]["category_source"]) == ("Autre", "user")
    # The user's choice and explanation are an example for the model, with their context.
    assert (
        "« VIR SALAIRE » (C/C EUROCOMPTE (Crédit Mutuel), le 01/02/2025, crédit de 2000.00 EUR) → Autre "
        "— explication : prime" in llm.calls[-1][1]
    )


def test_period_limits_the_run(data, llm):
    params = {"mode": "new", "date_from": "2025-02-01", "date_to": "2025-02-28"}
    assert data.get("/api/categorize/count", params=params).json() == {"count": 1}
    j = job(run(date_from=date(2025, 2, 1), date_to=date(2025, 2, 28)))
    assert j.total == 1 and len(llm.calls) == 1
    assert operations(data, uncategorized=True).keys() == {"CARTE CAFE DU COIN", "VIR SEPA LOYER"}


def test_similar_operations_only_when_the_user_asks(data, llm):
    upload(data, ("c.pdf", b"%PDF-C"))
    coffee = operations(data)["CARTE CAFE DU COIN"]
    assert data.get(f"/api/transactions/{coffee['id']}/similar").json() == {
        "count": 2,
        "examples": ["CARTE X9999 CAFE DU COIN 03/03"],
    }
    r = data.patch(
        f"/api/transactions/{coffee['id']}/category",
        json={"category": "Loisirs", "apply_to_similar": True, "reason": "  café  avec des amis "},
    )
    assert r.json() == {"updated": 3}
    with Session(get_engine()) as s:
        assert s.exec(select(Correction.reason)).all() == ["café avec des amis"]

    # A later import of the same kind of label follows the user's choice, without the model.
    upload(data, ("e.pdf", b"%PDF-E"))
    assert operations(data)["CARTE X0000 CAFE DU COIN 01/04"]["category_source"] == "rule"
    run()
    assert all("CAFE" not in call[2] for call in llm.calls)


def test_old_llm_memory_is_forgotten(data, llm):
    from bankparse_api.categorize.service import forget_llm_memory, rules_by_key

    with Session(get_engine()) as s:
        s.add(MerchantRule(merchant_key="LOYER", category="Voyages", source="llm", example_label="VIR SEPA LOYER"))
        s.add(MerchantRule(merchant_key="SALAIRE", category="Revenus", source="user", example_label="VIR SALAIRE"))
        s.commit()
        assert set(rules_by_key(s)) == {"SALAIRE"}  # LLM answers are never reused
        forget_llm_memory(s)
        assert s.exec(select(MerchantRule.source)).all() == ["user"]


def test_rename_delete_and_filters(data, llm):
    run()
    cats = {c["name"]: c for c in data.get("/api/categories").json()}
    assert cats["Restaurants"]["transaction_count"] == 2
    data.patch(f"/api/categories/{cats['Restaurants']['id']}", json={"name": "Cafés"})
    assert operations(data, category="Cafés").keys() == {"CARTE CAFE DU COIN"}
    data.delete(f"/api/categories/{cats['Logement']['id']}")
    assert operations(data)["VIR SEPA LOYER"]["category"] == "Inconnu"
    assert data.post("/api/categories", json={"name": "Animaux"}).status_code == 201
    assert data.post("/api/categories", json={"name": "Animaux"}).status_code == 400
    upload(data, ("d.pdf", b"%PDF-D"))
    assert operations(data, uncategorized=True).keys() == {"CARTE X9999 GARAGE MYSTERE 05/03"}


def test_reparse_keeps_categories(data, llm):
    run()
    rent = operations(data)["VIR SEPA LOYER"]
    data.patch(f"/api/transactions/{rent['id']}/category", json={"category": "Autre"})
    for f in data.get("/api/files").json():
        assert data.post(f"/api/files/{f['id']}/reparse").json()["status"] == "imported"
    ops = operations(data)
    assert (ops["VIR SEPA LOYER"]["category"], ops["VIR SEPA LOYER"]["category_source"]) == ("Autre", "user")
    assert ops["CARTE CAFE DU COIN"]["category"] == "Restaurants"


def test_status_models_conflict_and_cancel(data, llm):
    s = data.get("/api/categorize/status").json()
    assert s["ollama_ok"] and s["never_categorized"] and s["uncategorized"] == 4
    # Precise runs suggest the configured model, fast runs a smaller one (smallest installed as a fallback).
    assert (s["default_model"], s["fast_model"], s["default_batch_size"]) == ("gemma4:latest", "tiny:1b", 10)
    assert [m["name"] for m in s["models"]] == ["tiny:1b", "gemma4:latest"]
    assert data.post("/api/categorize", json={"model": "absent:7b"}).status_code == 400

    with Session(get_engine()) as session:
        session.add(CategorizationJob(status="running"))
        session.commit()
    assert data.post("/api/categorize", json={"model": "tiny:1b"}).status_code == 409
    with Session(get_engine()) as session:
        session.exec(delete(CategorizationJob))
        session.commit()

    # Cancel requested during the first operation: stops before the second one.
    llm.on_call = lambda: runner.request_cancel(data.get("/api/categorize/jobs/latest").json()["id"])
    j = job(run())
    assert j.status == "cancelled" and len(llm.calls) == 1
    assert data.get("/api/categorize/status").json()["uncategorized"] == 3


def test_previous_manual_choices_become_examples(data, llm):
    from bankparse_api.categorize.service import backfill_corrections, user_examples

    run()
    rent = operations(data)["VIR SEPA LOYER"]
    with Session(get_engine()) as s:  # simulate a choice made before corrections were recorded
        t = s.get(Transaction, rent["id"])
        t.category, t.category_source = "Abonnements", "user"
        s.add(t)
        s.exec(delete(Correction))
        s.commit()
        assert backfill_corrections(s) == 1 and backfill_corrections(s) == 0
        [example] = user_examples(s)
        assert (example.label, example.category, example.reason) == ("VIR SEPA LOYER", "Abonnements", None)


def test_existing_database_gets_new_columns(tmp_path):
    """A database created by an older version (columns missing) is upgraded in place."""
    import sqlite3

    from bankparse_api.db import add_missing_columns
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel

    path = tmp_path / "old.db"
    engine = create_engine(f"sqlite:///{path}")
    SQLModel.metadata.create_all(engine)
    engine.dispose()
    with sqlite3.connect(path) as conn:  # simulate the previous version
        conn.execute("ALTER TABLE categorizationjob DROP COLUMN model")
        conn.execute('ALTER TABLE "transaction" DROP COLUMN category_model')
        conn.execute("ALTER TABLE category DROP COLUMN description")
    add_missing_columns(create_engine(f"sqlite:///{path}"))
    with sqlite3.connect(path) as conn:
        assert "model" in {r[1] for r in conn.execute("PRAGMA table_info(categorizationjob)")}
        assert "category_model" in {r[1] for r in conn.execute('PRAGMA table_info("transaction")')}
        assert "description" in {r[1] for r in conn.execute("PRAGMA table_info(category)")}


def test_fast_mode_sends_several_operations_per_request(data, llm):
    upload(data, ("d.pdf", b"%PDF-D"))
    j = job(run(batch_size=10))
    assert j.status == "done" and j.batch_size == 10 and j.done == 5
    assert len(llm.calls) == 1  # 5 operations, one request
    model, system, user = llm.calls[0]
    assert "juge chacune séparément" in system and '{"results"' in system
    assert user.count("« ") == 5 and "1. « " in user
    ops = operations(data)
    # Each operation got its own answer; the one without answer is Inconnu (nothing copied).
    assert ops["VIR SEPA LOYER"]["category"] == "Logement"
    assert ops["CARTE X9999 GARAGE MYSTERE 05/03"]["category"] == "Inconnu"
    assert data.get("/api/categorize/status").json()["default_batch_size"] == 1  # precise afterwards


@pytest.mark.parametrize(
    "ollama_status, expected_reason",
    [
        (OllamaStatus(False, [], "Ollama ne répond pas"), "Ollama ne répond pas"),
        (OllamaStatus(True, [], "Aucun modèle installé"), "Aucun modèle installé"),
    ],
)
def test_no_usable_model_disables_categorization(data, llm, monkeypatch, ollama_status, expected_reason):
    monkeypatch.setattr(FakeLLM, "status", lambda self: ollama_status)
    s = data.get("/api/categorize/status").json()
    assert s["reason"] == expected_reason and s["models"] == []
    assert s["default_model"] is None and s["fast_model"] is None
    assert data.post("/api/categorize", json={"model": "gemma4:latest"}).status_code == 400


def test_missing_suggested_model_is_reported(data, llm):
    # Fake installs "tiny:1b" and "gemma4:latest": the fast suggestion (gemma4:e2b) is missing.
    s = data.get("/api/categorize/status").json()
    assert s["missing_models"] == ["gemma4:e2b"]


def test_validated_proposals_are_never_sent_to_the_model_again(data, llm):
    run()
    ops = operations(data)
    rent, coffee = ops["VIR SEPA LOYER"], ops["CARTE CAFE DU COIN"]
    assert data.get("/api/categorize/status").json()["to_review"] == 4

    r = data.post(f"/api/transactions/{rent['id']}/validation", json={"validated": True})
    assert r.json() == {"updated": 1}
    rent = operations(data)["VIR SEPA LOYER"]
    assert (rent["category"], rent["category_source"], rent["category_model"]) == ("Logement", "validated", "tiny:1b")
    assert data.get("/api/categorize/status").json()["to_review"] == 3
    assert "VIR SEPA LOYER" not in operations(data, to_review=True)

    # "Everything except the user's choices" skips validated operations too.
    assert data.get("/api/categorize/count", params={"mode": "all"}).json() == {"count": 3}
    calls = len(llm.calls)
    run("all")
    assert len(llm.calls) == calls + 3 and all("LOYER" not in c[2] for c in llm.calls[calls:])

    # Un-validating puts it back in the list to review.
    data.post(f"/api/transactions/{rent['id']}/validation", json={"validated": False})
    assert operations(data)["VIR SEPA LOYER"]["category_source"] == "llm"

    # A manual correction is not an "LLM proposal": validating it changes nothing.
    data.patch(f"/api/transactions/{coffee['id']}/category", json={"category": "Loisirs"})
    assert data.post(f"/api/transactions/{coffee['id']}/validation", json={}).json() == {"updated": 0}


def test_bulk_validation_follows_the_list_filters(data, llm):
    run()
    r = data.post("/api/transactions/validation", params={"category": "Restaurants"})
    assert r.json() == {"updated": 2}  # the two coffees only
    ops = operations(data)
    assert {ops["CARTE CAFE DU COIN"]["category_source"], ops["VIR SALAIRE"]["category_source"]} == {"validated", "llm"}
    assert set(operations(data, to_review=True)) == {"VIR SEPA LOYER", "VIR SALAIRE"}
    assert data.post("/api/transactions/validation").json() == {"updated": 2}  # everything left
    assert data.get("/api/categorize/status").json()["to_review"] == 0
