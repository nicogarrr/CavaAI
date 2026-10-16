# PortfolioChat: fuentes visibles

Cambio separado del guard de respuesta. El backend ya devolvía sources; PortfolioChat descartaba citations. Ahora muestra el título y localizador de cada fuente, página cuando existe y un enlace solo cuando el backend entrega una URL http(s) sin credenciales. No construye enlaces a partir del título, dominio ni ID. CompanyChat conserva su mapper. El backend pasa source_url almacenada para document_chunk y la URL recuperada del documento tenant-validado para rag_chunk; cuando no existe, no añade ninguna.

## Verificación

- Tres contratos Node: mapeo, URL insegura/sin fuentes y conexión action/UI.
- ESLint dirigido sin avisos.
- Fixture local sin cuenta ni sesión, sin llamadas al modelo: inspección visual a390x844 y1280x900. Título largo ajusta, página y localizador legibles, registro interno sin enlace. Un único enlace a example.org/report.pdf, URL declarada de fixture, no fuente oficial ni datos reales.
- La ruta de fixture se eliminó antes del commit.
- No se ha probado con una conversación autenticada de producción ni con documentos de Nico. No se afirma que el fixture pruebe recuperación o exactitud de los documentos.
- Build de producción y TypeScript: EXIT0, sin ruta de fixture. Los dos primeros intentos fallaron por tipos de desarrollo de la ruta temporal eliminada; el build final usa un dist limpio.
- Backend6tests SQLite aislados pasan, incluido URL guardada/RAG y ausencia de URL. Ruff dirigido con la configuración real del repo pasa.
- Suite completa de guards: resultado en el cuerpo del PR.
