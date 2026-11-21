"""Spaces: statements of different account holders are kept apart."""

import sqlite3
from datetime import date
from decimal import Decimal

import bankparse
import pytest
from bankparse.models import Account, BalanceSnapshot, ParsedStatement, Transaction
from bankparse_api import ingest
from bankparse_api.spaces import owner_key

DAY = date(2025, 3, 3)


def statement(owner: str | None, account: str, label: str = "CARTE BOULANGERIE", bank_code: str = "CM"):
    t = Transaction(account, DAY, DAY, label, Decimal("-4.20"))
    return ParsedStatement(
        bank="Crédit Mutuel" if bank_code == "CM" else "Crédit Agricole",
        bank_code=bank_code,
        owner=owner,
        statement_date=DAY,
        accounts=[Account(account, "COMPTE COURANT")],
        transactions=[t],
        balances=[BalanceSnapshot(account, DAY, Decimal(100))],
    )


@pytest.fixture
def statements(monkeypatch):
    by_content: dict[bytes, ParsedStatement] = {
        b"%PDF-ben-cm": statement("Benjamin Parent", "111"),
        b"%PDF-ben-ca": statement("Parent Benjamin", "222", bank_code="CA"),
        b"%PDF-marie": statement("Marie Dupont", "333"),
        b"%PDF-ben-noname": statement(None, "111", label="CARTE PRIMEUR"),
        b"%PDF-stranger-noname": statement(None, "999"),
    }
    def parse(content: bytes) -> ParsedStatement:
        if content.startswith(b"%PDF-receipt"):
            raise bankparse.UnsupportedStatementError("not a statement")
        return by_content[content]

    monkeypatch.setattr(ingest.bankparse, "parse", parse)


def test_every_file_belongs_to_exactly_one_user(client, statements):
    [ben] = upload(client, b"%PDF-ben-cm")
    emma = client.post("/api/spaces", json={"name": "Emma"}).json()

    def files_of(space_id: int) -> set[str]:
        return {f["filename"] for f in client.get("/api/files", params={"space_id": space_id}).json()}

    # Unsupported document imported for Emma: Emma's only.
    r = upload_for(client, emma["id"], b"%PDF-receipt-1")
    assert r["status"] == "unsupported"
    assert files_of(emma["id"]) == {"%PDF-receipt-1.pdf"}
    assert "%PDF-receipt-1.pdf" not in files_of(ben["space_id"])

    # Automatic detection, holder unknowable: the user shown in the app.
    client.post(
        "/api/uploads",
        files=[("files", ("receipt-2.pdf", b"%PDF-receipt-2", "application/pdf"))],
        data={"fallback_space_id": str(ben["space_id"])},
    )
    assert "receipt-2.pdf" in files_of(ben["space_id"]) and "receipt-2.pdf" not in files_of(emma["id"])
    assert client.get("/api/summary", params={"space_id": emma["id"]}).json()["files_total"] == 1


def upload(client, *contents: bytes) -> list[dict]:
    files = [("files", (f"{c.decode()}.pdf", c, "application/pdf")) for c in contents]
    response = client.post("/api/uploads", files=files)
    assert response.status_code == 200
    return response.json()


def spaces(client) -> dict[str, dict]:
    return {s["name"]: s for s in client.get("/api/spaces").json()}


def test_owner_key_ignores_order_case_and_accents():
    assert owner_key("Parent Benjamin") == owner_key("BENJAMIN PARENT") == "benjamin parent"
    assert owner_key("Hélène Dupré") == owner_key("DUPRE Helene")
    assert owner_key(None) is None and owner_key("  ") is None


def test_each_holder_gets_a_space(client, statements):
    ben_cm, ben_ca, marie = upload(client, b"%PDF-ben-cm", b"%PDF-ben-ca", b"%PDF-marie")
    assert ben_cm["space_created"] and not ben_ca["space_created"] and marie["space_created"]
    assert ben_cm["space_id"] == ben_ca["space_id"] != marie["space_id"]
    assert marie["space_name"] == "Marie Dupont"

    sp = spaces(client)
    assert set(sp) == {"Benjamin Parent", "Marie Dupont"}
    ben, mar = sp["Benjamin Parent"]["id"], sp["Marie Dupont"]["id"]
    assert sp["Benjamin Parent"]["account_count"] == 2

    assert client.get("/api/transactions", params={"space_id": ben}).json()["total"] == 2
    assert client.get("/api/transactions", params={"space_id": mar}).json()["total"] == 1
    assert client.get("/api/transactions").json()["total"] == 3  # no space: everything
    assert {a["account_number"] for a in client.get("/api/accounts", params={"space_id": mar}).json()} == {"333"}
    assert len(client.get("/api/files", params={"space_id": ben}).json()) == 2
    assert client.get("/api/summary", params={"space_id": mar}).json()["transactions"] == 1

    renamed = client.patch(f"/api/spaces/{mar}", json={"name": "Marie"}).json()
    assert renamed["name"] == "Marie"


def test_unreadable_holder(client, statements):
    [ben] = upload(client, b"%PDF-ben-cm")
    # Known account: stays in its holder's space.
    [again] = upload(client, b"%PDF-ben-noname")
    assert again["space_id"] == ben["space_id"] and not again["space_created"]
    # Unknown account: goes to the "unknown holder" space.
    [stranger] = upload(client, b"%PDF-stranger-noname")
    assert stranger["space_name"] == "Titulaire inconnu" and stranger["space_created"]


def test_rules_and_corrections_stay_in_their_space(client, statements):
    upload(client, b"%PDF-ben-cm", b"%PDF-marie")
    sp = spaces(client)
    ben, mar = sp["Benjamin Parent"]["id"], sp["Marie Dupont"]["id"]
    [ben_tx] = client.get("/api/transactions", params={"space_id": ben}).json()["items"]

    # Same label in Marie's space, but Benjamin's "apply to similar" choice must not touch it.
    assert client.get(f"/api/transactions/{ben_tx['id']}/similar").json()["count"] == 0
    r = client.patch(
        f"/api/transactions/{ben_tx['id']}/category", json={"category": "Alimentation", "apply_to_similar": True}
    )
    assert r.json()["updated"] == 1
    [mar_tx] = client.get("/api/transactions", params={"space_id": mar}).json()["items"]
    assert mar_tx["category"] is None

    from bankparse_api.categorize.service import rules_by_key, user_examples
    from bankparse_api.db import get_engine
    from sqlmodel import Session

    with Session(get_engine()) as s:
        assert rules_by_key(s, mar) == {} and len(rules_by_key(s, ben)) == 1
        assert user_examples(s, mar) == [] and len(user_examples(s, ben)) == 1


def test_move_account_to_another_space(client, statements):
    upload(client, b"%PDF-ben-cm", b"%PDF-marie")
    sp = spaces(client)
    ben, mar = sp["Benjamin Parent"]["id"], sp["Marie Dupont"]["id"]
    [acc] = client.get("/api/accounts", params={"space_id": mar}).json()

    moved = client.patch(f"/api/accounts/{acc['id']}", json={"space_id": ben}).json()
    assert moved["space_id"] == ben and moved["label"] == "COMPTE COURANT"  # label untouched
    assert client.get("/api/transactions", params={"space_id": ben}).json()["total"] == 2
    assert len(client.get("/api/files", params={"space_id": ben}).json()) == 2
    assert "Marie Dupont" not in spaces(client)  # empty spaces are hidden
    assert client.patch(f"/api/accounts/{acc['id']}", json={"space_id": 999}).status_code == 404


def test_migration_of_a_database_created_before_spaces(tmp_path, monkeypatch):
    """An old database: no space table, no space_id columns, merchant rules unique on merchant_key."""
    path = tmp_path / "bankparse.db"
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE account (id INTEGER PRIMARY KEY, bank_code VARCHAR NOT NULL, bank VARCHAR NOT NULL,
            account_number VARCHAR NOT NULL, label VARCHAR NOT NULL, custom_label VARCHAR, owner VARCHAR,
            UNIQUE (bank_code, account_number));
        CREATE TABLE merchantrule (id INTEGER PRIMARY KEY, merchant_key VARCHAR NOT NULL, category VARCHAR NOT NULL,
            source VARCHAR NOT NULL, example_label VARCHAR NOT NULL, updated_at DATETIME NOT NULL);
        CREATE UNIQUE INDEX ix_merchantrule_merchant_key ON merchantrule (merchant_key);
        INSERT INTO account VALUES (1, 'CA', 'Crédit Agricole', '222', 'CCHQ', NULL, 'Parent Benjamin');
        INSERT INTO account VALUES (2, 'CM', 'Crédit Mutuel', '111', 'C/C', NULL, 'Benjamin Parent');
        INSERT INTO merchantrule VALUES (1, 'BOULANGERIE', 'Alimentation', 'user', 'CARTE BOULANGERIE',
            '2025-01-01 00:00:00');
        """
    )
    con.commit()
    con.close()

    from bankparse_api import config, db

    monkeypatch.setenv("BANKPARSE_DATA_DIR", str(tmp_path))
    config.get_settings.cache_clear()
    db.reset_engine()
    try:
        db.get_engine()
        db.reset_engine()
        db.get_engine()  # idempotent
    finally:
        db.reset_engine()
        config.get_settings.cache_clear()

    con = sqlite3.connect(path)
    assert con.execute("SELECT id, name FROM space").fetchall() == [(1, "Parent Benjamin")]
    assert con.execute("SELECT DISTINCT space_id FROM account").fetchall() == [(1,)]
    assert con.execute("SELECT space_id FROM merchantrule").fetchall() == [(1,)]
    # The same label key can now exist in another space, but not twice in the same one.
    con.execute(
        "INSERT INTO merchantrule (space_id, merchant_key, category, source, example_label, updated_at) "
        "VALUES (2, 'BOULANGERIE', 'Alimentation', 'user', 'x', '2025-01-01')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO merchantrule (space_id, merchant_key, category, source, example_label, updated_at) "
            "VALUES (1, 'BOULANGERIE', 'Alimentation', 'user', 'x', '2025-01-01')"
        )
    con.close()


def upload_for(client, space_id: int, content: bytes) -> dict:
    response = client.post(
        "/api/uploads",
        files=[("files", (f"{content.decode()}.pdf", content, "application/pdf"))],
        data={"space_id": str(space_id)},
    )
    assert response.status_code == 200
    return response.json()[0]


def test_add_a_user_then_import_for_them(client, statements):
    r = client.post("/api/spaces", json={"name": "Emma"})
    assert r.status_code == 201
    emma = r.json()
    assert emma["account_count"] == 0
    assert "Emma" in spaces(client)  # listed before any statement
    assert client.post("/api/spaces", json={"name": "EMMA"}).status_code == 400  # already exists
    assert client.post("/api/spaces", json={"name": "  "}).status_code == 400

    # Imported for Emma although the name read is "Marie Dupont": Emma's space learns that holder...
    r = upload_for(client, emma["id"], b"%PDF-marie")
    assert r["space_id"] == emma["id"] and not r["space_created"]
    # ...so later statements of that holder, uploaded without a choice, are recognized as Emma's.
    assert not r["warnings"]
    from bankparse_api.db import get_engine
    from bankparse_api.models import Space
    from sqlmodel import Session

    with Session(get_engine()) as s:
        assert s.get(Space, emma["id"]).owner_key == "dupont marie"


def test_chosen_user_wins_over_the_name_read(client, statements):
    [ben] = upload(client, b"%PDF-ben-cm")
    marie = client.post("/api/spaces", json={"name": "Marie Dupont"}).json()

    # Read as Benjamin Parent, imported for Marie: a warning says so (Marie's space has a holder already).
    upload_for(client, marie["id"], b"%PDF-marie")
    r = upload_for(client, marie["id"], b"%PDF-ben-ca")
    assert r["space_id"] == marie["id"]
    assert any("Parent Benjamin" in w for w in r["warnings"])

    # A file imported before is moved when imported again for another user, with its account.
    again = upload_for(client, marie["id"], b"%PDF-ben-cm")
    assert again["status"] == "already_imported" and again["space_id"] == marie["id"]
    assert set(spaces(client)) == {"Marie Dupont"}  # Benjamin's space has no account left: hidden
    assert len(client.get("/api/files", params={"space_id": marie["id"]}).json()) == 3

    # Re-analysis keeps the choice.
    assert client.post(f"/api/files/{ben['file_id']}/reparse").json()["space_id"] == marie["id"]
    assert client.post("/api/uploads", files=[("files", ("x.pdf", b"%PDF-marie", "application/pdf"))],
                       data={"space_id": "999"}).status_code == 404


def test_delete_an_empty_user(client, statements):
    [ben] = upload(client, b"%PDF-ben-cm")
    emma = client.post("/api/spaces", json={"name": "Emma"}).json()
    assert client.delete(f"/api/spaces/{ben['space_id']}").status_code == 400  # still has accounts
    assert client.delete(f"/api/spaces/{emma['id']}").status_code == 204
    assert set(spaces(client)) == {"Benjamin Parent"}


def test_cli_import_for_a_user(client, statements, tmp_path, capsys):
    from bankparse_api.cli import _import

    (tmp_path / "a.pdf").write_bytes(b"%PDF-ben-cm")
    assert _import([str(tmp_path)], user="Marie Dupont") == 0
    out = capsys.readouterr().out
    assert "New user: Marie Dupont" in out and "-> Marie Dupont" in out
    assert set(spaces(client)) == {"Marie Dupont"}
