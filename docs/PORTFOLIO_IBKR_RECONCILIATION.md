# Cartera IBKR: diagnóstico y límite de la reparación (17-oct-2026)

Esta PR no modifica saldos, posiciones, transacciones ni snapshots existentes y no ejecuta sincronizaciones. No es una recuperación de base de coste ni de rentabilidad histórica.

## Evidencia de solo lectura

- Flex Web Service descargado el 17-oct: XML SHA256 `31f53f6469cc37af253f258fcc5f48f66b8f6a911abb7e20478db841af1a7021`.
- Mensaje del proveedor: `Realized P/L is not ready and has been disabled for this statement.` Las ocho posiciones traen `costBasisPrice=0` y `costBasisMoney=0`. El guard existente rechaza el informe entero antes de escribir.
- Hay desfase entre ese extracto y las posiciones/caja persistidas. No se debe saltar el guard para refrescar cantidades con una base de coste falsa. Un saldo de caja negativo puede ser real y se conserva con signo; se muestra separado por divisa y con fecha, no se cambia a cero.
- Hay fotos guardadas, pero todos los retornos del historial inspeccionado son nulos. La foto más reciente tiene cobertura cero; otra mezcla precios y caja de fechas distintas. También hay valores antiguos incompatibles con una serie conciliada. No se usan como una gráfica verificada ni se borran.
- El importador actual no conserva el XML completo de cada importación pasada, por lo que las filas persistidas no bastan para verificar o corregir retroactivamente la base ni las cifras históricas.

El hash prueba qué respuesta se inspeccionó, no que sea una respuesta válida para importar. No se publica XML, cuenta, token, credencial ni identificador privado del usuario en esta nota.

## Lo que sí cambia

- El valor neto deja de titularse "Rendimiento Total": no es el beneficio del 1M seleccionado.
- Diagnóstico de coste y fechas de posiciones/caja, saldos por divisa y número de fotos/retornos válidos. Endpoint GET tenant-scoped y solo lectura.
- Los snapshots se consultan realmente: antes `getPortfolioScores` devolvía `history: undefined` siempre. El gráfico acepta solo una serie final completa y continua en validez, con retorno y TWR conocidos. No une huecos ni rellena ceros. No corrige la fuente, ni convierte rentabilidad por precio de compra en rentabilidad temporal.
- El aviso de estadísticas ya no ordena importar otra vez como si la ausencia de filas fuera el único motivo. Explica retornos no verificables y fotos incompletas.

## Qué falta para cerrar de verdad

1. Obtener una Flex regenerada con PyG lista, base de coste y cuenta/fecha correctas. Probar con el importador en dry-run y verificar cantidades, divisas, coste, caja y tipo de cambio contra el mismo extracto. No reutilizar el hash de esta descarga como aprobación.
2. Aprobación del cambio de datos y ejecución revisada con copia de seguridad. No borrar ni modificar manualmente snapshots para "desbloquear" métricas.
3. Para histórico: obtener extractos fechados originales de IBKR con posiciones, caja, FX y movimientos/flujos externos. Conciliar cada día de manera reproducible; mantener los días que no se puedan verificar como no disponibles. Un gráfico actual no acredita el pasado.
4. Verificar la API real, la UI móvil y las métricas en un usuario QA aislado. La sesión de Nico no es una cuenta de pruebas. Su comprobación final en producción queda pendiente tras despliegue aprobado.

No hay estimación de Sharpe, caída máxima ni rentabilidad mientras falten los datos. Un test sintético que dibuja una serie válida no demuestra que la cartera real ya tenga esa serie.
