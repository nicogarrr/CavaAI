# La cobertura se documenta en `docs/COVERAGE.md`

Este documento **se movio** a [`docs/COVERAGE.md`](../docs/COVERAGE.md). La
documentacion vive en `docs/`, no en el paquete: lo que describe es como el
**repo** mide a `data-engine`, y su ruta estable tiene que ser la del repo.

Este fichero se queda como enlace porque la ruta `data-engine/COVERAGE.md` estaba
citada desde comentarios de `.coveragerc`, de `scripts/run_coverage_gate.py` y de
`.github/workflows/coverage.yml`, y porque quien este mirando el motor lo lee
desde aqui.

Si llegaste por un enlace a este fichero y quieres el texto entero, sigue el
enlace. Si buscas el indice de todos los gates de calidad (cobertura, evals del
RAG, de los motores de valoracion, de las capas LLM y de la ingesta), es
[`docs/QUALITY_GATES.md`](../docs/QUALITY_GATES.md).

Lo que hay aqui, resumido:

```bash
cd data-engine
python scripts/run_coverage_gate.py          # mide + gatea (lo que usa CI)
python scripts/run_coverage_gate.py --report # imprime y sale 0 siempre
```

- Configuracion de medicion: [`data-engine/.coveragerc`](.coveragerc) (unica
  fuente; no hay `[tool.coverage]` en `pyproject.toml`).
- Umbrales por paquete: [`data-engine/coverage_baseline.json`](coverage_baseline.json).
- Gate: [`data-engine/scripts/run_coverage_gate.py`](scripts/run_coverage_gate.py).
- Donde corre: [`.github/workflows/coverage.yml`](../.github/workflows/coverage.yml).
- Por que esos numeros: [`docs/COVERAGE.md`](../docs/COVERAGE.md).
