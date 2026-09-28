"""Generador del fichero del Modelo 720 (declaración informativa, bienes en
el extranjero).

Diseño de registro verificado contra la especificación OFICIAL de AEAT:
"Modelo 720. Diseños físicos y lógicos para la presentación telemática"
(sede.agenciatributaria.gob.es, DR_Resto_Mod/archivos/modelo_720.pdf).
Registros de 500 bytes, ISO-8859-1, numéricos ajustados a la derecha con
ceros, alfanuméricos a la izquierda con blancos, en mayúsculas sin acentos.

Enfoque de referencia: DeclaRenta (GPL-3.0) — solo como guía de dominio.
Su layout tiene discrepancias con la spec oficial (valoraciones 13+2 en vez
de 12+2, subclave vacía, valor de adquisición en valoración 1 para clave V,
ID de cuenta en posiciones de ISIN); aquí se implementa el layout OFICIAL,
sin copia de código.

Honestidad (sin verde falso):
- Sin NIF del declarante (input manual) no se genera fichero:
  ``available=false``. El fichero es una ayuda de cómputo, nunca una
  declaración lista para presentar sin revisión.
- Una posición sin valoración en EUR a 31/12 NO entra en el fichero: se
  lista en ``excluded`` para valoración y declaración manual.
- Un valor sin ISIN no puede declararse con clave de identificación 1: se
  excluye y se lista (la clave 2 exige "Z"+país emisor, dato que no
  tenemos de forma fiable).
- País de la cuenta de efectivo: sin dato fiable de ubicación de la cuenta
  (no confundir con la divisa), la cuenta se excluye y se lista.
- La regla de redeclaración por incremento >20.000 € (origen M) solo se
  aplica con los ISINs de la declaración anterior aportados manualmente.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.models import Tenant
from app.services.portfolio_fx_service import PortfolioFXService
from app.services.tax_modelo720_service import Modelo720Service

# --- Layout oficial (spec AEAT, verificado campo a campo) -------------------

RECORD_LEN = 500
CODING = "iso-8859-1"


def _text(value: str, length: int, align_right: bool = False, zero_pad: bool = False) -> str:
    """Campo alfanumérico: mayúsculas, sin caracteres de control, ancho fijo.

    La spec exige mayúsculas sin vocales acentuadas ni caracteres especiales
    (ISO-8859-1); los caracteres de control se sustituyen por espacio ANTES
    de recortar para no desplazar columnas.
    """
    clean = "".join(
        ch if " " <= ch <= "~" or ch in "ÑÇ" else " "
        for ch in str(value)
    ).upper()
    # Transliteración mínima de acentuadas a ASCII (spec: sin vocales acentuadas).
    clean = clean.translate(str.maketrans("ÁÉÍÓÚÜ", "AEIOUU"))
    clean = clean[:length]
    if align_right:
        return clean.rjust(length, "0" if zero_pad else " ")
    return clean.ljust(length)


def _num(value: Decimal | int | str, int_len: int, dec_len: int) -> str:
    """Campo numérico: parte entera + decimal, sin coma, ceros a la izquierda.

    Redondeo ROUND_HALF_UP ANTES de separar parte entera y decimal. Si el
    redondeo desborda la parte entera se falla en voz alta: rellenar
    silenciosamente desplazaría todos los bytes siguientes del registro.
    """
    dec = Decimal(str(value)).copy_abs().quantize(
        Decimal(1).scaleb(-dec_len), rounding=ROUND_HALF_UP
    )
    int_digits = str(int(dec))
    if len(int_digits) > int_len:
        raise ValueError(
            f"Modelo 720: importe {dec} excede el campo de {int_len} dígitos enteros"
        )
    frac = int((dec - int(dec)) * (10 ** dec_len))
    return int_digits.zfill(int_len) + str(frac).zfill(dec_len)


def _money_field(value: Decimal, sign_pos: bool = True) -> tuple[str, str]:
    """Signo + importe de 14 posiciones (12 enteras + 2 decimales)."""
    sign = "N" if value < 0 else " "
    return sign, _num(value, 12, 2)


class Modelo720FileService:
    """Genera el fichero de 500 bytes/registro del Modelo 720."""

    def generate(self, db: Session, fiscal_year: int) -> dict:
        """Genera el fichero o explica por qué no puede (available=false).

        Los datos identificativos del declarante son datos fiscales
        PERSONALES y se leen de la metadata del tenant del portfolio activo
        (nunca de query params ni de configuración global), bajo la clave
        ``tax_declarant``::

            {
              "nif": "12345678A",                 # obligatorio
              "apellidos_nombre": "GARCIA, NICO", # obligatorio
              "telefono": "600000000",
              "cash_country": "IE",               # país de la cuenta (EHA/3496/2011)
              "previous_year_isins": ["US0378331005"],
              "numero_declaracion": "7202024000001",
              "declaracion_anterior": "7202024000001",
              "complementaria": false,
              "sustitutiva": false
            }

        Solo genera fichero para categorías con ``exceeds`` True (tri-estado:
        "desconocido" NO genera; el chequeo de umbrales explica qué falta).
        """
        thresholds = Modelo720Service().check_thresholds(db, fiscal_year)
        portfolio = PortfolioFXService().portfolio(db)
        tenant = (
            db.get(Tenant, portfolio.tenant_id)
            if portfolio is not None and portfolio.tenant_id is not None
            else None
        )
        declarant = (tenant.metadata_ or {}).get("tax_declarant") if tenant else None
        if not isinstance(declarant, dict) or not declarant.get("nif") or not declarant.get("apellidos_nombre"):
            return {
                "available": False,
                "reason": (
                    "Faltan datos identificativos del declarante: el registro "
                    "de tipo 1 exige NIF y apellidos y nombre, y no se "
                    "inventan. Guárdalos en la metadata del tenant bajo la "
                    "clave 'tax_declarant' (nif, apellidos_nombre, y "
                    "opcionalmente telefono, cash_country, "
                    "previous_year_isins...)."
                ),
                "thresholds": thresholds,
            }
        nif = str(declarant["nif"])
        apellidos_nombre = str(declarant["apellidos_nombre"])
        telefono = declarant.get("telefono")
        contacto = declarant.get("contacto")
        numero_declaracion = declarant.get("numero_declaracion")
        complementaria = bool(declarant.get("complementaria"))
        sustitutiva = bool(declarant.get("sustitutiva"))
        declaracion_anterior = declarant.get("declaracion_anterior")
        previous_year_isins = declarant.get("previous_year_isins") or []
        cash_country = declarant.get("cash_country")
        first_dates = {
            str(k).upper(): str(v).replace("-", "")
            for k, v in (declarant.get("first_acquisition_dates") or {}).items()
        }
        previous_isins = {str(i).upper() for i in previous_year_isins}

        detail_records: list[str] = []
        excluded: list[dict] = (
            list(thresholds.get("unvalued") or [])
            + list(thresholds.get("foreign_unverified") or [])
            + list(thresholds.get("short_positions") or [])
        )
        sum_val1 = Decimal("0")
        sum_val2 = Decimal("0")

        valores = thresholds["categories"]["valores"]
        if valores["exceeds"] is True:
            for pos in valores["positions"]:
                isin = (pos.get("isin") or "").upper()
                if not isin:
                    excluded.append({
                        "ticker": pos["ticker"],
                        "reason": "Sin ISIN: la clave 2 (valores sin ISIN) exige 'Z'+país emisor, dato no disponible. Declarar manualmente.",
                    })
                    continue
                value = Decimal(str(pos["value_base"]))
                origin = "M" if isin in previous_isins else "A"
                first_date = first_dates.get(isin, "")
                detail_records.append(
                    self._detail_valores(
                        fiscal_year, nif, apellidos_nombre, pos, isin,
                        value, origin, first_date,
                    )
                )
                sum_val1 += value
            # Bajas: ISINs declarados el año anterior que ya no se poseen.
            held = {
                (p.get("isin") or "").upper()
                for p in valores["positions"]
            }
            held.discard("")
            for isin in sorted(previous_isins - held):
                detail_records.append(
                    self._detail_baja(fiscal_year, nif, apellidos_nombre, isin)
                )

        cuentas = thresholds["categories"]["cuentas"]
        if cuentas["exceeds"] is True:
            if not cash_country:
                excluded.append({
                    "ticker": "cash",
                    "reason": "Falta el país donde está situada la cuenta (obligatorio, posiciones 129-130): aporta 'cash_country'. Cuentas excluidas del fichero.",
                })
            else:
                for bal in cuentas["balances"]:
                    value = Decimal(str(bal["value_base"]))
                    detail_records.append(
                        self._detail_cuenta(
                            fiscal_year, nif, apellidos_nombre, bal,
                            value, cash_country,
                        )
                    )
                    sum_val1 += value

        if not detail_records:
            return {
                "available": False,
                "reason": (
                    "Ninguna categoría supera los 50.000 € o todos los "
                    "registros quedaron excluidos por datos incompletos. "
                    "Sin obligación de fichero (o pendiente de valoración "
                    "manual; ver 'excluded')."
                ),
                "excluded": excluded,
                "thresholds": thresholds,
            }

        summary = self._summary_record(
            fiscal_year, nif, apellidos_nombre,
            telefono=telefono, contacto=contacto,
            numero_declaracion=numero_declaracion,
            complementaria=complementaria, sustitutiva=sustitutiva,
            declaracion_anterior=declaracion_anterior,
            detail_count=len(detail_records),
            sum_val1=sum_val1, sum_val2=sum_val2,
        )
        content = "\n".join([summary, *detail_records]) + "\n"
        return {
            "available": True,
            "encoding": CODING,
            "record_length": RECORD_LEN,
            "detail_records": len(detail_records),
            "content": content,
            "excluded": excluded,
            "thresholds": thresholds,
            "notas": [
                "Fichero conforme al diseño de registro oficial AEAT "
                "(500 bytes, ISO-8859-1): AYUDA DE CÓMPUTO — revisar antes "
                "de presentar por TGVI Online.",
                "Origen A/M determinado con los ISINs de la declaración "
                "anterior aportados manualmente; la regla del incremento "
                ">20.000 € requiere contrastar los importes de la última "
                "declaración.",
                "Cuentas: saldo medio del 4.º trimestre no disponible; "
                "valoración 2 de cuentas va a ceros (completar a mano).",
            ],
        }

    # --- Registros -----------------------------------------------------------

    def _summary_record(
        self, fiscal_year, nif, apellidos_nombre, *, telefono, contacto,
        numero_declaracion, complementaria, sustitutiva,
        declaracion_anterior, detail_count, sum_val1, sum_val2,
    ) -> str:
        r = "1"                                    # 1: tipo de registro
        r += "720"                                 # 2-4: modelo
        r += str(fiscal_year)                      # 5-8: ejercicio
        r += _text(nif, 9, align_right=True, zero_pad=True)   # 9-17: NIF
        r += _text(apellidos_nombre, 40)           # 18-57: apellidos y nombre
        r += "T"                                   # 58: tipo de soporte
        r += _text(telefono or "", 9, align_right=True, zero_pad=True)  # 59-67
        r += _text(contacto or apellidos_nombre, 40)  # 68-107: con quien relacionarse
        r += _text(numero_declaracion or "", 13, align_right=True, zero_pad=True)  # 108-120
        r += "C" if complementaria else " "        # 121: complementaria
        r += "S" if sustitutiva else " "           # 122: sustitutiva
        r += _text(declaracion_anterior or "", 13, align_right=True, zero_pad=True)  # 123-135
        r += str(detail_count).zfill(9)            # 136-144: total registros
        s1, v1 = _money_field(sum_val1)            # 145 signo
        r += s1 + _num(sum_val1, 15, 2)            # 146-162: suma valoración 1
        s2, v2 = _money_field(sum_val2)
        r += s2 + _num(sum_val2, 15, 2)            # 163-180: suma valoración 2
        r += " " * 320                             # 181-500: blancos
        assert len(r) == RECORD_LEN, f"tipo 1: {len(r)} bytes"
        return r

    def _detail_head(self, fiscal_year, nif, apellidos_nombre, clave_bien, subclave, pais) -> str:
        r = "2"                                    # 1: tipo de registro
        r += "720"                                 # 2-4: modelo
        r += str(fiscal_year)                      # 5-8: ejercicio
        r += _text(nif, 9, align_right=True, zero_pad=True)   # 9-17: NIF declarante
        r += _text(nif, 9, align_right=True, zero_pad=True)   # 18-26: NIF declarado
        r += " " * 9                               # 27-35: NIF representante
        r += _text(apellidos_nombre, 40)           # 36-75: nombre declarado
        r += "1"                                   # 76: condición = titular
        r += " " * 25                              # 77-101: tipo titularidad
        r += clave_bien                            # 102: clave tipo de bien
        r += subclave                              # 103: subclave
        r += " " * 25                              # 104-128: derecho real inmueble
        r += _text(pais, 2)                        # 129-130: código de país
        return r

    def _detail_tail(
        self, fecha_incorporacion, origen, fecha_extincion,
        val1, val2, representacion, cantidad,
    ) -> str:
        r = _text(fecha_incorporacion, 8)          # 415-422: fecha incorporación
        r += origen                                # 423: origen A/M/C
        r += _text(fecha_extincion, 8)             # 424-431: fecha extinción
        r += ("N" if val1 < 0 else " ")            # 432: signo valoración 1
        r += _num(val1, 12, 2)                     # 433-446: valoración 1
        r += ("N" if val2 < 0 else " ")            # 447: signo valoración 2
        r += _num(val2, 12, 2)                     # 448-461: valoración 2
        r += representacion                        # 462: representación (V/I)
        r += _num(cantidad, 10, 2)                 # 463-474: número de valores
        r += " "                                   # 475: clave inmueble (B)
        r += _num(100, 3, 2)                       # 476-480: % participación
        r += " " * 20                              # 481-500: blancos
        return r

    def _detail_valores(
        self, fiscal_year, nif, apellidos_nombre, pos, isin,
        value, origin, first_date,
    ) -> str:
        pais = isin[:2] if len(isin) >= 2 else "  "
        r = self._detail_head(fiscal_year, nif, apellidos_nombre, "V", "1", pais)
        r += "1"                                   # 131: identificación por ISIN
        r += _text(isin, 12)                       # 132-143: ISIN
        r += " "                                   # 144: clave ID cuenta (no C)
        r += " " * 11                              # 145-155: BIC
        r += " " * 34                              # 156-189: código cuenta
        r += _text(pos.get("name") or pos["ticker"], 41)  # 190-230: entidad
        r += " " * 20                              # 231-250: NIF entidad
        r += " " * 164                             # 251-414: domicilio entidad
        r += self._detail_tail(
            first_date, origin, "",
            value, Decimal("0"), "A",
            Decimal(str(pos.get("quantity") or 0)),
        )
        assert len(r) == RECORD_LEN, f"detalle V: {len(r)} bytes"
        return r

    def _detail_baja(self, fiscal_year, nif, apellidos_nombre, isin) -> str:
        pais = isin[:2] if len(isin) >= 2 else "  "
        r = self._detail_head(fiscal_year, nif, apellidos_nombre, "V", "1", pais)
        r += "1"                                   # 131: ISIN
        r += _text(isin, 12)                       # 132-143
        r += " " * (1 + 11 + 34)                   # 144-189
        r += " " * 41                              # 190-230: entidad (desconocida)
        r += " " * 20                              # 231-250
        r += " " * 164                             # 251-414
        r += self._detail_tail(
            "", "C", f"{fiscal_year}1231",
            Decimal("0"), Decimal("0"), "A", Decimal("0"),
        )
        assert len(r) == RECORD_LEN, f"baja V: {len(r)} bytes"
        return r

    def _detail_cuenta(
        self, fiscal_year, nif, apellidos_nombre, bal, value, cash_country,
    ) -> str:
        r = self._detail_head(fiscal_year, nif, apellidos_nombre, "C", "1", cash_country)
        r += "0"                                   # 131: sin contenido (no V/I)
        r += " " * 12                              # 132-143: solo V/I
        r += "O"                                   # 144: otra identificación
        r += " " * 11                              # 145-155: BIC (sin dato)
        r += _text(bal["currency"], 34)            # 156-189: código de cuenta
        r += _text("ENTIDAD GESTORA DE LA CUENTA", 41)  # 190-230
        r += " " * 20                              # 231-250
        r += " " * 164                             # 251-414
        r += self._detail_tail(
            "", "A", "",
            value, Decimal("0"), " ",
            Decimal("0"),
        )
        assert len(r) == RECORD_LEN, f"detalle C: {len(r)} bytes"
        return r
