"""LCL parser on a synthetic statement (fictitious data, word positions copied from the real layout)."""

from datetime import date
from decimal import Decimal

from bankparse.parsers._common import Document, Line, Page
from bankparse.parsers.lcl import parse_lcl

DEBIT_X1, CREDIT_X1 = 480.2, 558.1  # right edges of the amounts in the DEBIT / CREDIT columns


def _w(x0: float, x1: float, top: float, text: str) -> dict:
    return {"x0": x0, "x1": x1, "top": top, "text": text}


def _op(top, day, label, value, amount, debit=False):
    x1 = DEBIT_X1 if debit else CREDIT_X1
    return [_w(42.5, 65.0, top, day), _w(74.8, 215.0, top + 0.8, label), _w(365.6, 400.7, top, value),
            _w(x1 - 60, x1, top, amount)]


def _header(top):
    return [_w(41.6, 66.1, top, "DATE"), _w(197.1, 234.6, top, "LIBELLE"), _w(364.8, 401.7, top, "VALEUR"),
            _w(432.8, 459.8, top, "DEBIT"), _w(504.4, 537.8, top, "CREDIT")]


def _document() -> Document:
    page0 = [
        _w(131.8, 243.5, 57.2, "RELEVE DE COMPTE"),
        _w(349.3, 560.1, 89.4, "du 02.12.2030 au 05.01.2031 - N° 7"),
        _w(314.4, 444.1, 162.5, "MME JEANNE DUPONT"),
        _w(38.9, 236.6, 185.9, "------------------- Titulaire du compte-------------------"),
        _w(314.4, 415.2, 186.4, "12345 VILLE"),
        _w(38.9, 148.4, 197.8, "MME JEANNE DUPONT"),
        *_header(527.1),
        _w(41.9, 64.4, 551.0, "01.12"), _w(268.6, 354.1, 551.0, "ANCIEN SOLDE"), _w(420.4, DEBIT_X1, 551.0, "50,00"),
        *_op(574.9, "28.12", "VIR INST SOCIETE EXEMPLE", "28.12.30", "1 200,00"),
        _w(80.8, 188.4, 587.7, "LIBELLE:SALAIRE DECEMBRE"),
        *_op(598.8, "31.12", "CB BOULANGERIE", "31.12.30", "4,50", debit=True),
        _w(506.8, 559.3, 598.8, "."),
        _w(519.6, 560.5, 820.7, "Page 1 / 2"),
        _w(35.9, 571.4, 832.6, "Crédit Lyonnais-SA au capital de ... euros"),
    ]
    page1 = [
        _w(131.8, 243.5, 57.2, "RELEVE DE COMPTE"),
        _w(38.9, 74.9, 126.1, "Indicatif :"),
        *_header(150.0),
        _w(80.8, 160.0, 160.0, "PARIS"),  # label continued from the previous page
        *_op(174.0, "02.01", "PRLV SEPA OPERATEUR", "03.01.31", "20,00", debit=True),
        _w(92.8, 242.4, 186.0, "SOLDE INTERMEDIAIRE A FIN DECEMBRE"), _w(492.9, CREDIT_X1, 186.0, "1 145,50"),
        _w(316.5, 353.5, 198.0, "TOTAUX"), _w(420.4, DEBIT_X1, 198.0, "74,50"),
        _w(492.9, CREDIT_X1, 198.0, "1 200,00"),
        _w(41.9, 64.4, 210.0, "05.01"), _w(263.4, 354.0, 210.0, "SOLDE EN EUROS"),
        _w(492.9, CREDIT_X1, 210.0, "1 125,50"),
        _w(41.9, 300.0, 240.0, "LCL vous informe sur : 10,00"),
    ]
    lines0 = [
        Line("RELEVE DE COMPTE", 57.2),
        Line("du 02.12.2030 au 05.01.2031 - N° 7", 89.4),
        Line("30002 01234 0000123456X 17", 269.5),
    ]
    text0 = "\n".join(line.text for line in lines0)
    return Document(
        pages=[
            Page(number=0, text=text0, lines=lines0, tables=[], words=page0),
            Page(number=1, text="RELEVE DE COMPTE\nIndicatif :1234 Compte : 123456 X", tables=[], words=page1,
                 lines=[Line("RELEVE DE COMPTE", 57.2), Line("Indicatif :1234 Compte : 123456 X", 126.1)]),
        ]
    )


def test_parse_synthetic_lcl_statement():
    s = parse_lcl(_document())

    assert (s.bank, s.bank_code, s.owner) == ("LCL", "LCL", "Jeanne Dupont")
    assert s.statement_date == date(2031, 1, 5)
    assert [(a.account_id, a.label) for a in s.accounts] == [("01234123456", "Compte de dépôts")]
    assert [(t.operation_date, t.value_date, t.amount, t.label) for t in s.transactions] == [
        (date(2030, 12, 28), date(2030, 12, 28), Decimal("1200.00"),
         "VIR INST SOCIETE EXEMPLE LIBELLE:SALAIRE DECEMBRE"),
        (date(2030, 12, 31), date(2030, 12, 31), Decimal("-4.50"), "CB BOULANGERIE PARIS"),
        (date(2031, 1, 2), date(2031, 1, 3), Decimal("-20.00"), "PRLV SEPA OPERATEUR"),
    ]
    # The opening balance is in the DEBIT column: the account was overdrawn.
    assert [(b.date, b.amount) for b in s.balances] == [
        (date(2030, 12, 1), Decimal("-50.00")),
        (date(2031, 1, 5), Decimal("1125.50")),
    ]
    assert s.is_consistent is True
