"""Saneado ONE-SHOT de titulares SEC persistidos en inglés (quick win UX 4).

Contexto: la ingesta es insert-only con dedup por URL antes que por título,
así que un deploy del conector NO reescribe NewsEvent.title de filas ya
persistidas. Este script retitula SOLO esas filas históricas al formato
español actual («{TICKER} {form} presentado ante la SEC», mismo resultado
que compone la ingesta F175 para las nuevas).

Seguridad (requisitos de revisión):
- DRY-RUN por defecto: no escribe nada sin --apply explícito.
- Match estricto: metadata.connector == "sec" AND url de sec.gov AND
  patrón inglés conocido (fecha entre paréntesis, « filed » o doble
  prefijo de ticker). Cualquier fila que no case los TRES criterios se
  ignora y se reporta como fuera de alcance.
- Colisiones: si ya existe otra fila de la misma compañía con el título
  destino, la fila se SALTA y se reporta (nunca se fusionan ni borran).
- Backup/rollback: --apply exige --backup ruta.json y vuelca
  {id, tenant_id, title} ANTES de tocar nada; --rollback backup.json
  restaura los títulos de ese archivo. Una única transacción; error =
  rollback completo.
- Ejecutarlo sobre la BD de producción es una decisión aparte que
  requiere aprobación explícita del propietario con alcance y preview.

Uso:
    python -m scripts.retitle_sec_news_es                    # dry-run
    python -m scripts.retitle_sec_news_es --apply --backup /tmp/sec-titles.json
    python -m scripts.retitle_sec_news_es --rollback /tmp/sec-titles.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Company, NewsEvent

# Patrones ingleses conocidos del conector SEC histórico:
#   «COST 8-K (2026-09-24)», «8-K filed 2026-09-24», doble prefijo F175.
_DATE_PARENS = re.compile(r"\(\d{4}-\d{2}-\d{2}\)\s*$")
_FILED_EN = re.compile(r"\bfiled\b", re.IGNORECASE)
# Allowlist explícita de formularios SEC: un regex amplio casaría con
# cualquier token «LETRAS-dígito» y acabaría afirmando un form inventado.
_KNOWN_FORMS = [
    "8-K/A", "8-K", "10-K/A", "10-K", "10-Q/A", "10-Q", "11-K", "20-F", "40-F",
    "6-K", "S-1/A", "S-1", "S-3", "S-4", "S-8", "S-11", "F-1/A", "F-1", "F-3",
    "F-4", "F-6", "F-10", "424B2", "424B3", "424B4", "424B5", "SC 13D/A",
    "SC 13D", "SC 13G/A", "SC 13G", "SC13D", "SC13G", "13F-HR", "13F-NT",
    "DEF 14A", "DEFA14A", "PRE 14A", "POS AM", "SD", "ARS", "144",
]
_FORM = re.compile(
    r"\b(" + "|".join(re.escape(form) for form in _KNOWN_FORMS) + r")\b"
)


def _english_pattern(title: str) -> bool:
    return bool(_DATE_PARENS.search(title) or _FILED_EN.search(title))


def _strip_ticker_prefixes(text: str, ticker: str) -> str:
    """Quita prefijos repetidos del ticker (bug F175: «COST COST 8-K ...»)."""
    if not ticker:
        return text
    pattern = re.compile(rf"^(?:{re.escape(ticker)}\s+){{1,2}}", re.IGNORECASE)
    return pattern.sub("", text.strip())


def _new_title(row: NewsEvent, ticker: str) -> str | None:
    """Título destino o None si el form no se puede determinar con certeza."""
    headline = (row.metadata_ or {}).get("source_headline") or row.title
    base = _strip_ticker_prefixes(headline, ticker)
    base = _DATE_PARENS.sub("", base).strip()
    base = re.sub(r"\bfiled\b", "", base, flags=re.IGNORECASE).strip()
    match = _FORM.search(base)
    form = match.group(1) if match else None
    if form is None and not _english_pattern(headline):
        # Sin form reconocible y sin patrón inglés en el titular original:
        # no tocar lo incierto.
        return None
    # Form irreconocible en una fila SEC con patrón inglés claro: «filing»,
    # el mismo fallback honesto del conector (nunca un form inventado).
    title = f"{form or 'filing'} presentado ante la SEC"
    if ticker:
        title = f"{ticker} {title}"
    return title


def _candidates(db) -> list[tuple[NewsEvent, str]]:
    rows = db.scalars(
        select(NewsEvent).where(NewsEvent.url.isnot(None))
    ).all()
    out: list[tuple[NewsEvent, str]] = []
    for row in rows:
        metadata = row.metadata_ or {}
        if metadata.get("connector") != "sec":
            continue
        if "sec.gov" not in (row.url or ""):
            continue
        if not _english_pattern(row.title):
            continue
        ticker = ""
        if row.company_id is not None:
            company = db.get(Company, row.company_id)
            ticker = (company.ticker if company else "") or ""
        out.append((row, ticker))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="escribe los cambios (sin esto es dry-run)")
    parser.add_argument("--backup", help="ruta JSON de backup (obligatoria con --apply)")
    parser.add_argument("--rollback", help="restaura títulos desde un backup JSON y termina")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.rollback:
            with open(args.rollback, encoding="utf-8") as fh:
                backup = json.load(fh)
            restored = 0
            for entry in backup:
                row = db.get(NewsEvent, entry["id"])
                if row is not None and row.tenant_id == entry["tenant_id"]:
                    row.title = entry["title"]
                    restored += 1
            db.commit()
            print(f"rollback: {restored} títulos restaurados desde {args.rollback}")
            return 0

        candidates = _candidates(db)
        planned: list[dict] = []
        collisions: list[dict] = []
        undetermined: list[int] = []
        for row, ticker in candidates:
            new_title = _new_title(row, ticker)
            if new_title is None or new_title == row.title:
                undetermined.append(row.id)
                continue
            clash = db.scalar(
                select(NewsEvent.id).where(
                    NewsEvent.tenant_id == row.tenant_id,
                    NewsEvent.company_id == row.company_id,
                    NewsEvent.title == new_title,
                    NewsEvent.id != row.id,
                ).limit(1)
            )
            if clash is not None:
                collisions.append({"id": row.id, "title": new_title, "clash_with": clash})
                continue
            planned.append({"id": row.id, "tenant_id": row.tenant_id,
                            "old": row.title, "new": new_title})

        mode = "APPLY" if args.apply else "DRY-RUN"
        print(f"[{mode}] candidatas SEC+url+patrón inglés: {len(candidates)}")
        print(f"[{mode}] a retitular: {len(planned)}; colisiones saltadas: {len(collisions)}; "
              f"sin form determinable o ya correctas: {len(undetermined)}")
        for item in planned:
            print(f"  #{item['id']}: {item['old']!r} -> {item['new']!r}")
        for item in collisions:
            print(f"  COLISIÓN #{item['id']}: destino {item['title']!r} ya existe en #{item['clash_with']}")

        if not args.apply:
            print("dry-run: sin escrituras. Repite con --apply --backup ruta.json para aplicar.")
            return 0
        if not args.backup:
            print("error: --apply exige --backup ruta.json", file=sys.stderr)
            return 2
        with open(args.backup, "w", encoding="utf-8") as fh:
            json.dump([{"id": p["id"], "tenant_id": p["tenant_id"], "title": p["old"]}
                       for p in planned], fh, ensure_ascii=False, indent=2)
        print(f"backup escrito en {args.backup} ({len(planned)} filas)")
        for item in planned:
            row = db.get(NewsEvent, item["id"])
            if row is not None:
                row.title = item["new"]
        db.commit()
        print(f"aplicado: {len(planned)} títulos retitulados en UNA transacción")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
