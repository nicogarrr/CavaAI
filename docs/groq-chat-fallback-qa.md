# Respaldo educativo determinista, no segundo proveedor activo

## Decisión tras auditoría

La propuesta Groq se ha retirado del código activo. La cuenta Free, Global ZDR y clave siguen preparadas en almacenamiento seguro, pero este PR no añade configuración, clave, dependencia ni llamada a Groq. No se publica ninguna salida generada en la ruta local. No se afirma que una denylist garantice ausencia de asesoramiento en texto arbitrario.

El vocabulario cerrado devuelve únicamente definiciones españolas revisadas incluidas en el código. Se garantiza igualdad exacta con una de esas definiciones, ninguna llamada al proveedor y ninguna lectura de presupuesto o fuente privada. Preguntas fuera del patrón exacto continúan por la ruta anterior: no se presentan como cubiertas por el respaldo local. No se amplía la política de esa ruta ni se afirma que sus respuestas generadas estén garantizadas.

## Qué cambia

35 conceptos: PER, EBITDA, ETF, dividendo, deuda, ingresos, beneficio, margen, inflación, interés compuesto, diversificación, precio de mercado, capitalización, BPA, flujo de caja libre, ROE, ROIC, valor de empresa, balance, flujo de caja, bono, acción, índice, tipo de interés, deuda neta, activo, pasivo, patrimonio neto, amortización, rentabilidad, volatilidad, liquidez, apalancamiento, dilución y valor contable. Alias españoles e ingleses y preguntas exactas de definición; respuesta siempre española.

`¿Qué es el PER?` no necesita cuota, red, cuenta ni modelo. El contrato identifica `model=local-educational`, `prompt_version=local-glossary-v1`, `generated=false`, `provider_calls=0`. No hay fuentes falsas, tickers inventados, cifras actuales ni órdenes personalizadas. No se presenta como análisis de una cartera. Se conserva modelo/proveedor real en rutas que sí usan LLM, en vez de confundir nombre del wrapper con modelo.

No se transmite ningún dato a un segundo proveedor. La salida local no copia ni interpola pregunta, cartera, documento, ticker, fuentes ni contexto. Incluso si el baseline contiene información privada, la respuesta local es la definición fija pública y no incluye sus fuentes.

## Pruebas

251 regresiones chat/biblioteca/proveedor pasan y Ruff limpio. Todas las definiciones se prueban con un proveedor que lanza si se llama y un presupuesto que lanza si se consulta, y con baseline privado. Tests verifican igualdad exacta de cada salida, fuentes vacías y límites de longitud. Preguntas con órdenes, emails, empresas o sufijos no se reconocen como concepto local. El canario `Para su jubilación, adquiera acciones de AAA y liquide la posición en BBB.` no es una definición admitida.

Cambios de expectativas existentes: conceptos antes generados ahora locales; tests del guard de salida generada siguen probándolo con preguntas fuera del vocabulario exacto. No se retira la protección existente. Primer pase detectó14expectativas de generación que se ajustaron al nuevo contrato; 251/251 final verde. Prueba real local del servicio con proveedor prohibido: PER0.00123s, salida exacta revisada, cero llamadas. No es medida de latencia de red/producción.

## Referencias para revisión educativa

Las definiciones son redacción propia, no citas oficiales ni datos empresariales. Referencias de contraste: glosarios educativos CNMV y SEC Investor.gov y advertencia CNMV sobre medidas alternativas (EBITDA/flujo libre no estandarizados). En particular se evita equiparar EBITDA, beneficio e ingresos con caja; se distingue valor de empresa de capitalización y patrimonio contable de mercado.

- https://www.cnmv.es/Portal/inversor/glosario?lang=es
- https://www.investor.gov/introduction-investing/investing-basics/glossary/all
- https://www.cnmv.es/webservices/verdocumento/ver?t=%7Bda6f96f5-4b13-4599-bbd3-c753049616f0%7D

## Despliegue y límites

No desplegado. Falta auditoría, autorización exacta del SHA y CI verde. No se presenta como segundo proveedor activo ni arreglo de preguntas arbitrarias. Las definiciones son generales, no consejo financiero personalizado. Rollback por imagen/configuración anterior. La propuesta Groq se retomará solo cuando Nico decida un alcance útil y autorizado; clave/cuenta seguras no equivalen a activación.

Otras referencias consultadas: SEC guía de estados financieros (balance, ingresos, gastos, BPA y flujos), glosario independiente MeridIAn (PER/ROE/ROIC/valor de empresa/deuda neta/EBITDA, usado solo para contrastar fórmulas y definiciones, sin adoptar su clasificación ni cifras) y boletín CNMV para siglas:
- https://www.sec.gov/about/reports-publications/beginners-guide-financial-statements
- https://meridianscreener.com/glosario/
- https://www.cnmv.es/DocPortal/Publicaciones/Boletin/Boletin_2T_22_ENen.pdf
