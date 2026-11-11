import pytest
from bankparse import UnsupportedStatementError, detect_bank, parse


def test_credit_agricole_mentioning_boursobank_is_still_ca():
    text = "CREDIT AGRICOLE RELEVE DE COMPTES\nDate d'arrêté : 06 Janvier 2025\nVirement depuis BoursoBank 100,00"
    assert detect_bank(text) == "CA"


def test_old_credit_mutuel_layout():
    # 2014-2016 statements only say "CCM <city>" in the footer.
    assert detect_bank("RELEVE ET INFORMATIONS BANCAIRES Caisse 05260\n31 décembre 2014") == "CM"


def test_bourso_account_statement():
    assert detect_bank("BOURSORAMA\nB.I.C. BOUSFRPPXXX\nMOUVEMENTS EN EUR") == "BOURSO"


def test_bourso_brokerage_statement_is_unsupported():
    with pytest.raises(UnsupportedStatementError, match="espèces"):
        detect_bank("Boursorama Relevé espèces PEA")


def test_unknown_bank():
    with pytest.raises(UnsupportedStatementError):
        detect_bank("BNP PARIBAS relevé")


def test_not_a_pdf():
    with pytest.raises(UnsupportedStatementError):
        parse(b"this is not a pdf")
