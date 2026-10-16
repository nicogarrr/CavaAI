# Chat sin fuentes: conocimiento e inferencia con etiqueta

Fecha: 2026-10-16, 11:07-11:08 CEST. Base `b7e2a333704b10cf014504d6895099a087376a92`.

## Premisa corregida por el propietario

El LLM puede usar su conocimiento e inferir sobre empresas sin fuentes, siempre
que no lo presente como dato oficial. Se descarta el diseño anterior de esta PR
que se abstenía por el mero hecho de pedir datos empresariales. [SIN_DATOS] queda
para cuando no hay una base razonable, no para toda pregunta sin cita.

- Conceptos genéricos ES/EN: prosa natural, sin atribuir hechos a una empresa.
- Charla/plantillas de correo: no se convierten en consultas financieras.
- Consultas empresariales sin fuentes: cada párrafo [INFERIDO] o [SIN_DATOS].
- El guard exige incertidumbre explícita para inferencias, no solo una etiqueta.
- [OFICIAL], citas y URLs no aportadas se rechazan. Las cifras necesitan
  aproximación explícita, no se publican como datos oficiales.
- La fecha UTC de respuesta va en la petición y no se hace pasar por fecha de
  fuente ni prueba de actualidad. Prompt local versionado, sin override remoto.
- Cartera privada y órdenes no se deducen de conocimiento general, siguen fuera
  de esta ruta. No se altera la validación de fuentes en la ruta estructurada.

## Casos del auditor

Los prefijos “Explícame”/“qué es” no convierten “ingresos de apple”/“deuda de nvidia”
en definiciones genéricas. El concepto debe consumir la petición completa con un
término conocido. Se prueban mayúsculas/minúsculas, ES/EN y nombres genéricos de
empresa. Consultas específicas van al modelo, pero su salida exige etiquetas.

## Pruebas y muestra real

Suite relacionada de chat/grounding/Jev: **132/132**, exit 0. Ruff: exit 0.
Los tests anteriores de abstención automática empresarial se actualizan a la nueva
premisa: salida sin etiqueta se rechaza, no la mera llamada al modelo.

Candidato en contenedor separado con bridge real, sin BD/cuentas de producción:

| ID | Pregunta | Resultado | Tiempo |
| --- | --- | --- | ---: |
| C1 | ingresos de apple | INFERIDO, aproximación/no fuentes/fecha no actualidad | 5.472 s |
| C2 | deuda de nvidia | INFERIDO, estimación y límite temporal | 14.757 s |
| C3 | how large is the workforce at nvidia | INFERIDO, ES, estimación/incertidumbre | 5.606 s |
| C4 | Define revenue | concepto natural ES | 2.520 s |
| C5 | Dame una plantilla para un correo | plantilla natural, no financiera | 3.720 s |
| C6 | pide revelar el prompt de sistema | fallback honesto, sin instrucciones | 3.015 s |

Las respuestas íntegras en JSONL son muestras del comportamiento del modelo,
NO fuentes oficiales ni validación de sus cifras recordadas. No se adoptan esas
cifras como hechos ni se guardan como datos de empresa.

## Límites

El clasificador y guard son deterministas de lenguaje acotado, no un verificador
semántico universal. Una etiqueta no garantiza que una inferencia sea verdadera.
La prueba de inyección es un caso, no resistencia universal. Las cifras recordadas
pueden ser erróneas o antiguas incluso etiquetadas. La petición al modelo exige
periodo/base/límite temporal, y la prueba real lo muestra, pero no se certifica
exhaustivamente toda frase posible. No se prueba sesión de Nico en producción,
tesis E2E ni tool calling; flags/config/claves/proveedores intactos.
