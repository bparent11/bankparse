from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[3] / "packages" / "bankparse" / "tests" / "fixtures"


def upload(client, *files: tuple[str, bytes]):
    response = client.post("/api/uploads", files=[("files", (n, c, "application/pdf")) for n, c in files])
    assert response.status_code == 200, response.text
    return response.json()


def test_deduplication_and_delete(client, fake_parser):
    [a] = upload(client, ("a.pdf", b"%PDF-A"))
    assert (a["status"], a["inserted"], a["duplicates"]) == ("imported", 3, 0)

    [again] = upload(client, ("a-copy.pdf", b"%PDF-A"))
    assert again["status"] == "already_imported"

    [b] = upload(client, ("b.pdf", b"%PDF-B"))
    assert (b["inserted"], b["duplicates"]) == (1, 2)
    assert client.get("/api/transactions").json()["total"] == 4

    # Deleting A keeps what B also contains: 1 coffee + rent + salary.
    assert client.delete(f"/api/files/{a['file_id']}").status_code == 204
    page = client.get("/api/transactions").json()
    assert page["total"] == 3
    assert sorted(t["label"] for t in page["items"]) == ["CARTE CAFE DU COIN", "VIR SALAIRE", "VIR SEPA LOYER"]

    assert client.delete(f"/api/files/{b['file_id']}").status_code == 204
    assert client.get("/api/transactions").json()["total"] == 0
    assert client.get("/api/accounts").json() == []


def test_filters_totals_and_export(client, fake_parser):
    upload(client, ("a.pdf", b"%PDF-A"), ("b.pdf", b"%PDF-B"))

    page = client.get("/api/transactions").json()
    assert (page["total_credit"], page["total_debit"]) == (2000.0, -507.0)
    assert client.get("/api/transactions", params={"q": "loyer"}).json()["total"] == 1
    assert client.get("/api/transactions", params={"direction": "credit"}).json()["total"] == 1
    assert client.get("/api/transactions", params={"date_from": "2025-02-01"}).json()["total"] == 1
    assert client.get("/api/transactions", params={"max_amount": -100}).json()["total"] == 1
    page1 = client.get("/api/transactions", params={"page_size": 3, "sort": "amount", "order": "asc"}).json()
    assert [t["amount"] for t in page1["items"]] == [-500.0, -3.5, -3.5]

    csv = client.get("/api/transactions/export", params={"format": "csv"})
    assert csv.headers["content-type"].startswith("text/csv")
    lines = csv.content.decode("utf-8-sig").splitlines()
    assert lines[0].startswith("date_operation;date_valeur;banque")
    assert len(lines) == 5 and "-500,0" in csv.text

    json_rows = client.get("/api/transactions/export", params={"format": "json", "q": "salaire"}).json()
    assert json_rows[0]["montant"] == 2000.0 and json_rows[0]["date_operation"] == "2025-02-01"

    xlsx = client.get("/api/transactions/export", params={"format": "xlsx"})
    assert xlsx.content[:2] == b"PK"


def test_accounts_summary_and_rename(client, fake_parser):
    upload(client, ("a.pdf", b"%PDF-A"))
    [acc] = client.get("/api/accounts").json()
    assert acc["transaction_count"] == 3 and acc["last_balance"] == 1000.0

    renamed = client.patch(f"/api/accounts/{acc['id']}", json={"label": "Compte courant"}).json()
    assert renamed["label"] == "Compte courant" and renamed["statement_label"] == "C/C EUROCOMPTE"
    assert client.get("/api/transactions").json()["items"][0]["account_label"] == "Compte courant"

    summary = client.get("/api/summary").json()
    assert summary["transactions"] == 3 and summary["months"] == [{"month": "2025-01", "credit": 0.0, "debit": -507.0}]
    assert client.get(f"/api/accounts/{acc['id']}/balances").json() == [{"date": "2025-01-12", "amount": 1000.0}]


def test_rejected_and_unsupported_files(client, fake_parser):
    rejected, unsupported = upload(client, ("notes.txt", b"hello"), ("x.pdf", b"%PDF-unsupported"))
    assert rejected["status"] == "rejected"
    assert unsupported["status"] == "unsupported" and "not a statement" in unsupported["error"]
    [record] = client.get("/api/files").json()
    assert record["status"] == "unsupported"


@pytest.mark.skipif(not FIXTURES.exists() or not any(FIXTURES.glob("*.pdf")), reason="no private fixtures")
def test_real_statements_end_to_end(client):
    files = [(p.name, p.read_bytes()) for p in sorted(FIXTURES.glob("*.pdf"))]
    results = upload(client, *files)
    imported = [r for r in results if r["status"] == "imported"]
    assert {r["bank"] for r in imported} == {"Crédit Agricole", "Crédit Mutuel", "Boursorama"}
    assert all(r["check_ok"] is True for r in imported)
    assert all(r["inserted"] > 0 for r in imported)

    again = upload(client, *files)
    assert {r["status"] for r in again} <= {"already_imported", "unsupported"}

    [reparsed] = [client.post(f"/api/files/{imported[0]['file_id']}/reparse").json()]
    assert reparsed["status"] == "imported" and reparsed["inserted"] == imported[0]["inserted"]
    total = client.get("/api/transactions").json()["total"]
    assert total == sum(r["inserted"] for r in imported)
