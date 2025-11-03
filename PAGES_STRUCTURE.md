# Estructura de Páginas - CavaAI

## Páginas Principales de la Aplicación

### 1. Dashboard (/)
**Descripción:** Página principal con overview completo del mercado  
**Características:**
- Vista de mercado con TradingView widgets
- Heatmap de acciones
- Cotizaciones en tiempo real
- Noticias del mercado
- Sección de ProPicks IA

**Ideal para:** Vista rápida del estado general del mercado

---

### 2. Screener (/screener)
**Descripción:** Herramienta avanzada para filtrar y encontrar acciones según criterios específicos  
**Características:**
- ✅ **MEJORADO** - Filtros completamente funcionales conectados a resultados
- Filtros por capitalización de mercado, precio, P/E, P/B, ROE
- Filtros por sector, exchange y tipo de activo
- Sistema de scoring configurable (Value, Quality, Momentum, Size)
- Exportación de resultados a CSV
- Guardado de criterios de búsqueda
- Persistencia de filtros mediante URL params

**Ideal para:** Inversores que buscan acciones específicas basadas en fundamentales y técnicos

**Cómo usar:**
1. Ajusta los filtros en la barra lateral según tus criterios
2. Haz clic en "Buscar" para aplicar los filtros
3. Ajusta los pesos de scoring en la parte superior de resultados
4. Exporta los resultados a CSV si lo necesitas
5. Guarda tus criterios para uso futuro

---

### 3. Portfolio/Cartera (/portfolio)
**Descripción:** ✨ **NUEVA PÁGINA** - Seguimiento completo de tus inversiones personales  
**Características:**
- **Resumen de Cartera:**
  - Valor total de inversiones
  - Costo total de adquisición
  - Ganancia/Pérdida total en $ y %
  - Rendimiento global de la cartera

- **Posiciones Actuales:**
  - Lista de todas tus posiciones abiertas
  - Cantidad de acciones por símbolo
  - Precio promedio de compra vs precio actual
  - Ganancia/Pérdida individual por posición

- **Historial de Transacciones:**
  - Registro completo de compras y ventas
  - Fechas, cantidades, precios y totales
  - Notas opcionales por transacción
  - Opción de eliminar transacciones

- **Agregar Transacciones:**
  - Formulario intuitivo para registrar compras/ventas
  - Validación de datos
  - Actualización automática de la cartera

**Ideal para:** Seguimiento detallado de tu portafolio personal de inversiones

**Cómo usar:**
1. Haz clic en "Agregar Transacción"
2. Ingresa el símbolo, tipo (compra/venta), cantidad, precio y fecha
3. La cartera se actualiza automáticamente calculando:
   - Precio promedio ponderado por acción
   - Ganancias/pérdidas realizadas y no realizadas
   - Rendimiento total de la cartera

---

### 4. ProPicks (/propicks)
**Descripción:** Selecciones de acciones generadas por IA  
**Características:**
- Estrategias de inversión configurables
- Análisis multifactorial (Valor, Crecimiento, Rentabilidad, etc.)
- Rankings y scores por acción
- Razones detalladas de cada recomendación
- Actualización mensual

**Ideal para:** Obtener ideas de inversión respaldadas por análisis de IA

---

### 5. Búsqueda (/search)
**Descripción:** Búsqueda rápida de acciones mediante Command+K  
**Características:**
- Búsqueda instantánea
- Sugerencias de acciones populares
- Acceso directo desde cualquier página
- Integración con Finnhub

**Ideal para:** Acceso rápido a información de cualquier acción

---

### 6. Detalles de Acción (/stocks/[symbol])
**Descripción:** Información completa sobre una acción específica  
**Características:**
- Gráficos interactivos de TradingView
- Perfil de empresa
- Métricas financieras
- Noticias relacionadas
- Análisis técnico

**Ideal para:** Investigación profunda de una acción específica

---

### 7. Detalles de Fondo/ETF (/funds/[symbol])
**Descripción:** Información detallada sobre ETFs y fondos  
**Características:**
- Holdings principales
- Performance histórico
- Métricas de riesgo
- Comparación con índices

**Ideal para:** Análisis de fondos y ETFs

---

## Páginas Futuras Sugeridas

### 8. Watchlist (Planeada)
**Descripción:** Lista personalizada de seguimiento de acciones  
**Características sugeridas:**
- Agregar/remover acciones favoritas
- Vista rápida de precios y cambios
- Alertas de precio
- Organización por categorías

### 9. Alertas (Planeada)
**Descripción:** Sistema de alertas de precio y eventos  
**Características sugeridas:**
- Alertas de precio (arriba/abajo de X)
- Alertas de cambio porcentual
- Notificaciones por email
- Historial de alertas activadas

### 10. Análisis Comparativo (Planeada)
**Descripción:** Comparar múltiples acciones lado a lado  
**Características sugeridas:**
- Comparación de métricas fundamentales
- Gráficos comparativos de performance
- Tablas comparativas personalizables
- Exportación de comparaciones

---

## Navegación Actualizada

La barra de navegación ahora incluye:
- Dashboard
- Search (Command+K)
- Screener
- **Cartera** ✨ (nuevo)
- **ProPicks** (ahora visible en navegación)

---

## Mejoras Implementadas

### Screener
1. ✅ Filtros completamente funcionales
2. ✅ Sincronización entre filtros y resultados mediante URL params
3. ✅ Exportación a CSV
4. ✅ Guardado de criterios de búsqueda en localStorage
5. ✅ Reset de filtros funcional
6. ✅ Sistema de scoring configurable

### Portfolio
1. ✅ Modelo de datos completo para transacciones
2. ✅ Cálculo automático de precios promedio ponderados
3. ✅ Seguimiento de ganancias/pérdidas realizadas y no realizadas
4. ✅ Interfaz intuitiva para gestión de transacciones
5. ✅ Integración con API de Finnhub para precios actuales
6. ✅ Resumen visual del portafolio

### Navegación
1. ✅ Agregada página de Portfolio
2. ✅ Agregada página de ProPicks a navegación principal

---

## Recomendaciones de Uso

**Para inversores principiantes:**
- Comienza con el Dashboard para familiarizarte con el mercado
- Usa ProPicks para obtener ideas de inversión respaldadas por IA
- Utiliza el Portfolio para registrar tus primeras inversiones

**Para inversores intermedios:**
- Usa el Screener para encontrar acciones según tu estrategia
- Mantén tu Portfolio actualizado para seguimiento preciso
- Combina ProPicks con tu propio análisis

**Para inversores avanzados:**
- Configura criterios personalizados en el Screener
- Ajusta los pesos de scoring según tu metodología
- Exporta datos para análisis adicional
- Utiliza el Portfolio para backtesting de estrategias

---

## Tecnologías Utilizadas

- **Next.js 15** - Framework principal
- **MongoDB** - Base de datos para portfolio y transacciones
- **Finnhub API** - Datos de mercado en tiempo real
- **TradingView Widgets** - Gráficos y visualizaciones
- **Tailwind CSS** - Estilización
- **shadcn/ui** - Componentes de UI

---

## Notas de Desarrollo

- Todas las páginas requieren autenticación
- Los datos de mercado tienen revalidación automática
- El Portfolio calcula automáticamente métricas en tiempo real
- El Screener usa caché inteligente para optimizar llamadas a la API
- Los filtros del Screener persisten en la URL para compartir

---

**Última actualización:** 2025-11-03  
**Versión:** 1.0.0
