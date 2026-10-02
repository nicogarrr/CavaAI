"""Gate de la cadena de Alembic: un solo head, lineal y sin ciclos ni huerfanos.

Alembic indexa las migraciones por nombre de fichero: si dos ficheros comparten
prefijo de 4 digitos (`0047_*.py`) o la cadena se ramifica, `alembic heads` da
varios heads y `alembic upgrade head` aborta con "Multiple head revisions are
present for given argument 'head'". En FIX-1 tres hermanos 0047_* apuntando a
0046_inferred_inputs dejaron el contenedor de produccion sin arrancar
(`Dockerfile.prod` ejecuta `alembic upgrade head` antes de uvicorn).

Este test parsea `alembic/versions/*.py` con ast (sin ejecutar Alembic) y
vigila las invariantes de la cadena. Los casos negativos escriben migraciones
sinteticas en `tmp_path` y comprueban que cada regla detecta de verdad: un gate
que no sabe fallar no vigila nada.
"""

import ast
import re
from pathlib import Path

VERSIONS_DIR = Path(__file__).resolve().parents[1] / "alembic" / "versions"

# Deuda preexistente FUERA de la propiedad de FIX-1 (no se puede renombrar
# 0016 aqui): `0016_principle_jobs_and_portfolio_snapshots.py` declara
# revision `0016_principle_jobs_snapshots`, distinta del stem del fichero.
# La regla revision == stem es ESTRICTA; esta lista es exactamente la deuda
# conocida. Cualquier violacion NUEVA falla el test, y arreglar 0016 tambien
# (hay que vaciar la lista a proposito: es el recordatorio de que el nombre
# del fichero y la revision deben caminar juntos).
DEUDA_CONOCIDA = [
    "0016_principle_jobs_and_portfolio_snapshots.py: "
    "revision '0016_principle_jobs_snapshots' != fichero '0016_principle_jobs_and_portfolio_snapshots'",
]

# ---------------------------------------------------------------------
# PENDIENTE DE ENCADENAR AL MERGEAR (no es deuda, es una instruccion).
#
# En el worktree principal hay un 0047_instrument_references.py SIN COMMITEAR
# (autoria del agente que trabaja en chore/slop-dead-code-backend), declarado
# asi:
#
#     revision = "0047_instrument_references"
#     down_revision = "0046_inferred_inputs"
#
# Al mergearlo aqui tal cual rompe la cadena por partida doble: el prefijo
# 0047 ya lo tiene 0047_thesis_backtest, y su down_revision 0046_inferred_inputs
# convierte la cadena en una rama (dos hijos de 0046). Con este gate, el fallo
# que sale es exactamente:
#
#     - hay 2 heads (0047_instrument_references, 0049_backend_metrics); debe haber exactamente 1
#     - la cadena se ramifica en '0046_inferred_inputs': down_revision de
#       0047_instrument_references, 0047_thesis_backtest
#     - prefijo 0047 repetido en 0047_instrument_references.py, 0047_thesis_backtest.py
#
# Sin el gate, lo unico que se ve es el efecto secundario de
# `alembic upgrade head` ("Multiple head revisions are present..."), que
# deja el contenedor de produccion sin arrancar sin decir que fichero sobra.
#
# Encadenado exacto cuando ese fichero entre:
#
#     git mv data-engine/alembic/versions/0047_instrument_references.py \
#            data-engine/alembic/versions/0050_instrument_references.py
#     # cabeceras: revision = "0050_instrument_references"
#     #            down_revision = "0049_backend_metrics"
#
# Ojo al orden de llegada: 0050 es el siguiente libre HOY (head 0049). Si
# entra antes otra migracion, este pasa a 0051 y su down_revision al head que
# exista entonces, no a 0049. La regla la impone el propio test: revision ==
# stem del fichero, prefijo de 4 digitos unico y un solo head.
# ---------------------------------------------------------------------
MIGRACION_PENDIENTE_DE_ENCADENAR = (
    "0047_instrument_references.py (sin commitear en el worktree principal) "
    "llega con down_revision '0046_inferred_inputs': hay que renombrarlo a "
    "0050_instrument_references y encadenarlo con down_revision "
    "'0049_backend_metrics'."
)

STEM_PENDIENTE_DE_ENCADENAR = "0047_instrument_references"
HINT_MIGRACION_PENDIENTE = (
    "PENDIENTE DE ENCADENAR: " + MIGRACION_PENDIENTE_DE_ENCADENAR + " Ver el bloque de comentario de este modulo."
)

_PATRON_PREFIJO = re.compile(r"^\d{4}_.+")
_AUSENTE = object()


def _constante(nodo: ast.AST) -> object:
    """Valor de una asignacion a nivel de modulo: str, None o AUSENTE."""
    if isinstance(nodo, ast.Constant):
        return nodo.value
    return _AUSENTE


def _leer_declaraciones(path: Path) -> tuple[object, object]:
    """(revision, down_revision) declarados a nivel de modulo de un fichero."""
    arbol = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    revision: object = _AUSENTE
    down_revision: object = _AUSENTE
    for sentencia in arbol.body:
        if isinstance(sentencia, ast.Assign):
            nombres = [t.id for t in sentencia.targets if isinstance(t, ast.Name)]
            valor = _constante(sentencia.value)
        elif isinstance(sentencia, ast.AnnAssign) and isinstance(sentencia.target, ast.Name):
            nombres = [sentencia.target.id]
            valor = _constante(sentencia.value) if sentencia.value is not None else _AUSENTE
        else:
            continue
        if "revision" in nombres:
            revision = valor
        if "down_revision" in nombres:
            down_revision = valor
    return revision, down_revision


def violaciones_cadena(versions_dir: Path) -> list[str]:
    """Invariantees de la cadena de migraciones, como mensajes accionables.

    Reglas: exactamente un head; revision == stem del fichero; prefijo de 4
    digitos unico; exactamente un down_revision = None (la raiz); cada revision
    es down_revision de exactamente una migracion (linealidad); ningun
    down_revision huerfano (no apunta a una revision inexistente) y ninguna
    revision inalcanzable desde la raiz (ciclo o rama colgante).
    """
    entradas: list[tuple[Path, str, object, object]] = []
    problemas: list[str] = []
    for path in sorted(versions_dir.glob("*.py")):
        revision, down_revision = _leer_declaraciones(path)
        entradas.append((path, path.stem, revision, down_revision))
        if revision is _AUSENTE or not isinstance(revision, str):
            problemas.append(f"{path.name}: sin revision de cadena str")
            continue
        if down_revision is _AUSENTE:
            problemas.append(f"{path.name}: sin down_revision declarado (usa down_revision = None)")
            continue
        if down_revision is not None and not isinstance(down_revision, str):
            problemas.append(f"{path.name}: down_revision ni str ni None")
            continue
        if revision != path.stem:
            problemas.append(f"{path.name}: revision '{revision}' != fichero '{path.stem}'")
        if not _PATRON_PREFIJO.match(path.stem):
            problemas.append(f"{path.name}: el stem no empieza por prefijo de 4 digitos y '_'")

    prefijos: dict[str, list[str]] = {}
    stems: dict[str, str] = {}
    for path, stem, _revision, _down in entradas:
        prefijos.setdefault(stem[:4], []).append(path.name)
        stems[path.name] = stem
    for prefijo, nombres in sorted(prefijos.items()):
        if len(nombres) > 1:
            problemas.append(f"prefijo {prefijo} repetido en {', '.join(sorted(nombres))}")
            # Si el culpable es la migracion pendiente documentada arriba, el
            # gate dice QUE hacer en vez de solo que hay dos ficheros con el
            # mismo prefijo (que es lo que hace perder el rato a quien llega).
            if any(stems[nombre] == STEM_PENDIENTE_DE_ENCADENAR for nombre in nombres):
                problemas.append(HINT_MIGRACION_PENDIENTE)

    revisiones: dict[str, Path] = {}
    for path, _stem, revision, _down in entradas:
        if isinstance(revision, str) and revision is not _AUSENTE:
            if revision in revisiones:
                problemas.append(f"revision '{revision}' declarada en {revisiones[revision].name} y {path.name}")
            revisiones[revision] = path

    usadas: list[str] = []
    raices: list[str] = []
    hijos: dict[str, list[str]] = {}
    for path, _stem, revision, down_revision in entradas:
        if not isinstance(revision, str) or revision is _AUSENTE:
            continue
        if down_revision is _AUSENTE:
            continue
        if down_revision is None:
            raices.append(revision)
        elif isinstance(down_revision, str):
            usadas.append(down_revision)
            hijos.setdefault(down_revision, []).append(revision)
            if down_revision not in revisiones:
                problemas.append(f"{path.name}: down_revision '{down_revision}' no existe (salto o huerfano)")

    heads = sorted(set(revisiones) - set(usadas))
    if len(heads) != 1:
        problemas.append(f"hay {len(heads)} heads ({', '.join(heads)}); debe haber exactamente 1")
    if len(raices) != 1:
        problemas.append(f"hay {len(raices)} migraciones con down_revision = None; debe haber exactamente 1")

    for padre, hijos_del_padre in sorted(hijos.items()):
        if len(hijos_del_padre) > 1:
            problemas.append(
                f"la cadena se ramifica en '{padre}': down_revision de {', '.join(sorted(hijos_del_padre))}"
            )

    if len(raices) == 1:
        vistas: set[str] = set()
        cola = [raices[0]]
        while cola:
            actual = cola.pop()
            if actual in vistas:
                continue
            vistas.add(actual)
            cola.extend(hijos.get(actual, []))
        inalcanzables = sorted(set(revisiones) - vistas)
        if inalcanzables:
            problemas.append(f"revisiones inalcanzables desde la raiz (ciclo o rama): {', '.join(inalcanzables)}")

    return sorted(problemas)


def _migracion_sintetica(versions_dir: Path, stem: str, revision: str, down_revision: str | None) -> Path:
    down_repr = repr(down_revision)
    (versions_dir / f"{stem}.py").write_text(
        f'"""migracion sintetica para el gate de cadena."""\n'
        f"\n"
        f'revision = "{revision}"\n'
        f"down_revision = {down_repr}\n"
        f"\n"
        f"\n"
        f"def upgrade() -> None:\n"
        f"    pass\n"
        f"\n"
        f"\n"
        f"def downgrade() -> None:\n"
        f"    pass\n",
        encoding="utf-8",
    )
    return versions_dir / f"{stem}.py"


def _cadena_valida(versions_dir: Path) -> None:
    _migracion_sintetica(versions_dir, "0001_alpha", "0001_alpha", None)
    _migracion_sintetica(versions_dir, "0002_beta", "0002_beta", "0001_alpha")
    _migracion_sintetica(versions_dir, "0003_gamma", "0003_gamma", "0002_beta")


def test_cadena_real_un_head_lineal_y_sin_huerfanos():
    assert violaciones_cadena(VERSIONS_DIR) == DEUDA_CONOCIDA


def test_cadena_sintetica_valida_no_da_problemas(tmp_path):
    _cadena_valida(tmp_path)
    assert violaciones_cadena(tmp_path) == []


def test_dos_heads_se_detectan(tmp_path):
    _migracion_sintetica(tmp_path, "0001_alpha", "0001_alpha", None)
    _migracion_sintetica(tmp_path, "0002_beta", "0002_beta", "0001_alpha")
    _migracion_sintetica(tmp_path, "0003_gamma", "0003_gamma", "0001_alpha")
    problemas = violaciones_cadena(tmp_path)
    assert any("heads" in p for p in problemas), problemas
    assert any("ramifica" in p for p in problemas), problemas


def test_prefijo_de_4_digitos_duplicado_se_detecta(tmp_path):
    _migracion_sintetica(tmp_path, "0001_alpha", "0001_alpha", None)
    _migracion_sintetica(tmp_path, "0001_beta", "0001_beta", "0001_alpha")
    problemas = violaciones_cadena(tmp_path)
    assert any("prefijo 0001 repetido" in p for p in problemas), problemas


def test_el_prefijo_duplicado_dice_QUE_hacer_si_es_la_migracion_pendiente(tmp_path):
    # El caso real de este gate: la migracion de instrument_references llega
    # con el stem y el down_revision de su worktree de origen. «Prefijo 0047
    # repetido» no basta para arreglarlo; el gate tiene que recitar el
    # encadenado (0050 + down_revision 0049_backend_metrics).
    _migracion_sintetica(tmp_path, "0047_thesis_backtest", "0047_thesis_backtest", "0046_inferred_inputs")
    _migracion_sintetica(
        tmp_path,
        STEM_PENDIENTE_DE_ENCADENAR,
        STEM_PENDIENTE_DE_ENCADENAR,
        "0046_inferred_inputs",
    )
    problemas = violaciones_cadena(tmp_path)
    assert any("prefijo 0047 repetido" in p for p in problemas), problemas
    assert any("0050_instrument_references" in p for p in problemas), problemas
    assert any("0049_backend_metrics" in p for p in problemas), problemas


def test_el_hint_no_aparece_en_una_cadena_limpia(tmp_path):
    # El hint es un diagnostico, no una regla: en una cadena valida (y en la
    # real) no puede ensuciar la lista de problemas.
    _cadena_valida(tmp_path)
    assert violaciones_cadena(tmp_path) == []


def test_revision_distinta_del_nombre_de_fichero_se_detecta(tmp_path):
    _migracion_sintetica(tmp_path, "0001_alpha", "0001_delta", None)
    problemas = violaciones_cadena(tmp_path)
    assert any("revision '0001_delta' != fichero '0001_alpha'" in p for p in problemas), problemas


def test_ciclo_se_detecta(tmp_path):
    _migracion_sintetica(tmp_path, "0001_alpha", "0001_alpha", None)
    _migracion_sintetica(tmp_path, "0002_beta", "0002_beta", "0003_gamma")
    _migracion_sintetica(tmp_path, "0003_gamma", "0003_gamma", "0002_beta")
    problemas = violaciones_cadena(tmp_path)
    assert any("inalcanzables" in p for p in problemas), problemas


def test_salto_huerfano_se_detecta(tmp_path):
    _migracion_sintetica(tmp_path, "0002_beta", "0002_beta", "0001_alpha")
    problemas = violaciones_cadena(tmp_path)
    assert any("no existe (salto o huerfano)" in p for p in problemas), problemas
