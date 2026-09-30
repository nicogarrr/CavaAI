"""Formato de la query GDELT por empresa.

Regresion: la API DOC 2.0 rechaza consultas con terminos OR que no van
entre parentesis ("Queries containing OR'd terms must be surrounded by
()."). La query se construia como `"Nombre" OR TICKER` y el carril de
noticias de empresa (tracked 30 min + universo 6h) fallaba en silencio:
cero eventos GDELT de empresa ingeridos.
"""

from types import SimpleNamespace

from app.workers.dramatiq_app import _gdelt_company_query


def _company(name: str, ticker: str):
    return SimpleNamespace(name=name, ticker=ticker)


def test_or_terms_wrapped_in_parens():
    query = _gdelt_company_query(_company("AST SpaceMobile", "ASTS"))
    assert query == '("AST SpaceMobile" OR ASTS)'


def test_whole_or_expression_is_parenthesized():
    query = _gdelt_company_query(_company("Amazon.com Inc", "AMZN"))
    assert query.startswith("(") and query.endswith(")")
    inner = query[1:-1]
    assert '"Amazon.com Inc"' in inner
    assert " OR AMZN" in inner
    # Ningun OR suelto fuera del par de parentesis exterior.
    assert " OR " in inner and " OR " not in query[len(inner):]


def test_company_name_stays_quoted_ticker_bare():
    query = _gdelt_company_query(_company("Banco Santander", "SAN.MC"))
    assert query == '("Banco Santander" OR SAN.MC)'
