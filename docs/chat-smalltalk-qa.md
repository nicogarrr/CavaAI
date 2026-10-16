# QA: respuestas breves por categoría

2026-10-16. Base exacta b7e2a333704b10cf014504d6895099a087376a92.

Antes, gracias/adiós/ok/vale devolvían la presentación del asistente y varias
variantes con acentos no se reconocían. Ahora agradecimiento -> “De nada.”,
despedida -> “Hasta luego.”, confirmación -> “De acuerdo.”, y el saludo conserva
la presentación existente. No se llama al LLM ni se consulta cartera para esas
frases puras. Una frase que añade una consulta no entra en el fast path.

Once canarios de categoría y acentos, más suite de chat/tickers/determinista:
58/58, exit 0. Ruff de los dos archivos: exit 0. El test anterior combinado tenía
13 fallos de 19 incluyendo conceptos en inglés; esa parte se retiró a #1085 por
raíz común. No se atribuye ese número a los once canarios de esta PR.

No corrige conceptos (A2), cartera/órdenes (A3), no añade contexto privado ni toca
sesión, proveedores, claves o configuración. No se usan cuentas de producción.

R2: CodeQL detectó backtracking polinómico por dos cuantificadores de espacios con signo opcional entre ambos. Se agrupa el signo con su espacio posterior para evitar dos recorridos del mismo prefijo. Canario adversario de 200000 espacios + x termina bajo 1 s. Pendiente reanálisis CodeQL del nuevo SHA.
