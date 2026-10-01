"""13F via edgartools con el MISMO shape que ``connectors/form13f.py``.

- Snapshot/offline (produccion OCI): el snapshot guarda el information table
  XML crudo y se parsea con el tolerant-parser del repo: MISMO shape por
  construccion (CUSIP + nombre de emisor tal como filed; tickers jamas
  inferidos, como exige ``manager_holding_ingestion_service``).
- Live (dev): objeto edgartools con ``parse_infotable_xml``/``holdings`` o un
  DataFrame de ``thirteenf/parsers/infotable_xml.py`` (columnas verificadas en
  5.59.1: 'Issuer', 'Class', 'Cusip', 'Value', 'PutCall',
  'InvestmentDiscretion', 'OtherManager', 'SharesPrnAmount', 'Type'
  ('Shares'/'Principal'), 'SoleVoting', 'SharedVoting', 'NonVoting',
  'Ticker'). OJO: ese parser anade 'Ticker' via ``cusip_ticker_mapping()``
  (red / mapping externo): la normalizacion IGNORA esa columna a proposito
  para no inferir tickers nunca.

Todos los valores salen ``str | None`` como en ``parse_information_table``.
"""

from __future__ import annotations

from typing import Any

from app.services.connectors import form13f as form13f_connector

# Claves EXACTAS de cada fila de form13f.parse_information_table (mismo orden).
THIRTEENF_ROW_KEYS: tuple[str, ...] = (
    "name_of_issuer",
    "title_of_class",
    "cusip",
    "value_usd_thousands",
    "ssh_prnamt",
    "ssh_prnamt_type",
    "put_call",
    "investment_discretion",
    "voting_sole",
    "voting_shared",
    "voting_none",
)

_TYPE_TO_PRNAMT = {"Shares": "SH", "Principal": "PRN"}


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value != value:
        return None
    text = str(value).strip()
    return text or None


def holdings_from_edgartools_dataframe(df: Any) -> list[dict]:
    """Normaliza el DataFrame del parser 13F de edgartools al shape del repo.

    'Type' ('Shares'/'Principal') se reconvierte a 'SH'/'PRN'; la columna
    'Ticker' de edgartools se descarta (tickers nunca inferidos). Los votos
    numericos se devuelven como str para igualar ``parse_information_table``.
    """
    try:
        records = df.to_dict(orient="records")
    except Exception:
        return []
    rows: list[dict] = []
    for record in records:
        ssh_type = _str_or_none(record.get("Type"))
        if ssh_type in _TYPE_TO_PRNAMT:
            ssh_type = _TYPE_TO_PRNAMT[ssh_type]
        rows.append(
            {
                "name_of_issuer": _str_or_none(record.get("Issuer")),
                "title_of_class": _str_or_none(record.get("Class")),
                "cusip": _str_or_none(record.get("Cusip")),
                "value_usd_thousands": _str_or_none(record.get("Value")),
                "ssh_prnamt": _str_or_none(record.get("SharesPrnAmount")),
                "ssh_prnamt_type": ssh_type,
                "put_call": _str_or_none(record.get("PutCall")),
                "investment_discretion": _str_or_none(record.get("InvestmentDiscretion")),
                "voting_sole": _str_or_none(record.get("SoleVoting")),
                "voting_shared": _str_or_none(record.get("SharedVoting")),
                "voting_none": _str_or_none(record.get("NonVoting")),
            }
        )
    return rows


def infotable_holdings(source: Any) -> list[dict]:
    """Information table 13F al shape del repo desde XML o objeto edgartools.

    - ``str``: XML crudo (snapshot/offline) via el tolerant-parser del repo.
    - objeto con ``parse_infotable_xml``/``holdings``/``to_dataframe`` o
      DataFrame: normalizacion documentada arriba.
    """
    if isinstance(source, str):
        return form13f_connector.parse_information_table(source)
    if isinstance(source, bytes):
        return form13f_connector.parse_information_table(source.decode("utf-8", errors="replace"))
    for attr in ("parse_infotable_xml", "infotable", "holdings"):
        candidate = getattr(source, attr, None)
        if callable(candidate):
            try:
                return holdings_from_edgartools_dataframe(candidate())
            except TypeError:
                continue
        elif candidate is not None and hasattr(candidate, "to_dict"):
            return holdings_from_edgartools_dataframe(candidate)
    to_df = getattr(source, "to_dataframe", None)
    if callable(to_df):
        return holdings_from_edgartools_dataframe(to_df())
    if hasattr(source, "to_dict"):
        return holdings_from_edgartools_dataframe(source)
    raise TypeError(f"unsupported 13F source: {type(source).__name__}")
