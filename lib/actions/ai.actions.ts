'use server';

import { getAuth } from '@/lib/better-auth/auth';
import { headers } from 'next/headers';

export async function generatePortfolioSummary(input: {
  portfolio: PortfolioPerformance;
  history: { t: number[]; v: number[] };
}): Promise<string> {
  const auth = await getAuth();
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session?.user) throw new Error('Usuario no autenticado');

  const apiKey = process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY;
  if (!apiKey) {
    return 'IA desactivada: falta la clave de Gemini en el entorno.';
  }

  const system = `Eres un analista financiero. Resume claramente en español: distribución, rendimiento reciente, riesgos y 2 recomendaciones accionables.`;

  const payload = {
    contents: [
      {
        role: 'user',
        parts: [
          {
            text: `${system}\n\nPORTFOLIO:\n${JSON.stringify(input.portfolio)}\n\nHISTORY:\n${JSON.stringify(input.history)}`,
          },
        ],
      },
    ],
  };

  try {
    const model = process.env.GEMINI_MODEL || 'gemini-2.5-flash';
    // Usar endpoint v1 (v1beta puede no soportar el modelo)
    const endpoint = `https://generativelanguage.googleapis.com/v1/models/${model}:generateContent?key=${apiKey}`;
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      cache: 'no-store',
    });
    const json = await res.json().catch(() => ({} as any));

    if (!res.ok) {
      const apiError = json?.error?.message || JSON.stringify(json);
      console.error('Gemini API error', res.status, apiError);
      return `IA desactivada temporalmente: (${res.status}) ${apiError}`;
    }
    const text: string | undefined = json?.candidates?.[0]?.content?.parts?.[0]?.text;
    return text || 'No se pudo generar el resumen en este momento.';
  } catch (e) {
    console.error('Gemini error', e);
    return 'Error al generar el resumen con IA.';
  }
}

// Nueva función combinada que integra DCF + Tesis de Inversión
export async function generateCombinedAnalysis(input: {
  symbol: string;
  companyName: string;
  financialData: any;
  currentPrice: number;
}): Promise<string> {
  const auth = await getAuth();
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session?.user) throw new Error('Usuario no autenticado');

  const apiKey = process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY;
  if (!apiKey) {
    return 'IA desactivada: falta la clave de Gemini en el entorno.';
  }

  // Usar el sistema prompt de InvestmentThesis mejorado pero incluyendo DCF completo
  const system = String.raw`Eres un analista financiero profesional y experto inversor especializado en due diligence exhaustivo de nivel institucional. Genera un ANÁLISIS COMPLETO DE INVERSIÓN que INTEGRA la TESIS DE INVERSIÓN y el ANÁLISIS DCF en UN SOLO documento exhaustivo en español, siguiendo EXACTAMENTE esta estructura y estilo (basado en análisis profesionales de referencia como Novo Nordisk de HatedMoats):

## Estructura Obligatoria del Análisis Completo (Usar "Parte I", "Parte II", etc.)

### Parte I: Resumen Ejecutivo y Veredicto Final

#### 1. Título del Análisis
- Formato: "[Nombre Empresa]: Análisis de Inversión Exhaustivo"
- Subtítulo: "[Símbolo] - Valoración DCF y Tesis de Inversión"
- Fecha de análisis

#### 2. Veredicto Final Destacado (al inicio)
**OBLIGATORIO: Crear visualización en texto de tres tarjetas lado a lado:**

**Tarjeta 1: Precio vs Valor Intrínseco**
- Gráfico de barras en texto:
  Ejemplo:
  "===== Precio Actual: PRECIO_ACTUAL
  ============================== Valor Intrínseco: VALOR_INTRINSEO"
- Texto: "El precio actual es significativamente menor que su valor intrínseco calculado."

**Tarjeta 2: Margen de Seguridad**
- Gráfico donut en texto: mostrar el porcentaje grande
- Fórmula: "Basado en: 1 - (Precio Actual / Valor Intrínseco)"
- Número prominente: "XX.X%"

**Tarjeta 3: VEREDICTO FINAL**
- Fondo verde (descrito en texto)
- Verdicto en mayúsculas: "SEVERAMENTE INFRAVALORADA" / "JUSTAMENTE VALORADA" / "SOBREVALORADA"
- Texto explicativo

#### 3. Resumen Rápido y Tesis de Inversión
- **Tesis Alcista**: 4-5 puntos clave con números específicos
- **Tesis Bajista**: 4-5 riesgos materiales específicos
- **Factores Clave de Inversión**: Lista numerada con métricas
- **Riesgos Principales**: Lista de riesgos y por qué son manejables
- **Desconexión de Valoración**: Comparación PER vs competidores/sector
- **Mi Análisis Muestra**: Valor intrínseco significativamente por encima del precio actual

### Parte II: El Fundamento del Negocio y la Ciencia/Modelo

#### 2.1. El Eje Central: [Tema Clave]
[Igual que en InvestmentThesis]

#### 2.2. Los Productos/Servicios Relevantes
**OBLIGATORIO: Tabla 1: Comparativa de Productos/Servicios Clave**

#### 2.3. Las "Trampas"
[Igual que en InvestmentThesis]

### Parte III: El Modelo de Crecimiento

[Igual que en InvestmentThesis]

### Parte IV: Valoración mediante Flujo de Caja Descontado (DCF) - Supuestos y Metodología

#### 4.1. Proyección de Ingresos (Años 1-10)
**OBLIGATORIO: Crear Tabla de Proyección de Ingresos en formato Markdown correcto**

**INSTRUCCIONES PARA TABLAS:**
- **FORMATO DE TABLAS**: CRÍTICO - Usa el formato EXACTO de Markdown para tablas:
  * Fila encabezados: | Columna1 | Columna2 | Columna3 |
  * Fila separadora OBLIGATORIA: |:---:|:---:|:---:| (con guiones IGUALES o mínimo 3)
  * Filas datos: | Dato1 | Dato2 | Dato3 |
  * IMPORTANTE: Todas las filas DEBEN tener el MISMO número de pipes (|)
  * IMPORTANTE: Cada fila DEBE empezar y terminar con pipe (|)
  * EJEMPLO: 
    | Año | Ingresos | Crecimiento |
    |:---:|:--------:|:-----------:|
    | 2024 | 157.980,1 | - |
- Incluye siempre la fila separadora: |-----|----------|----------|
- Asegúrate de que todas las columnas estén alineadas correctamente
- Usa números formateados con comas para miles y puntos para decimales (ej: 1.234,56 o $1.234,56)

**Tabla de Proyección de Ingresos:**
| Año | Ingresos (M USD) | Crecimiento Año a Año | CAGR 10 Años | Justificación |
|-----|------------------|------------------------|--------------|---------------|
| 2024 (Base) | VALOR_BASE | - | - | Datos históricos |
| 2025 | VALOR_2025 | PORCENTAJE% | - | Justificación específica |
| ... | ... | ... | ... | ... |
| 2034 | VALOR_2034 | PORCENTAJE% | CAGR% | Valor Terminal |

- Explicar el punto de anclaje (Año 0)
- Justificar cada año o rango de años con:
  - Guía del management si está disponible
  - Tendencias de mercado
  - Crecimiento histórico
  - Factores competitivos
  - Ciclos de productos

#### 4.2. Rentabilidad (EBIT → NOPAT)
**OBLIGATORIO: Crear Tabla de Proyección de Rentabilidad en formato Markdown**

**Tabla de Proyección de Rentabilidad:**
| Año | Ingresos (M USD) | Margen EBIT | EBIT (M USD) | Tasa Impositiva | NOPAT (M USD) |
|-----|-----------------|-------------|-------------|-----------------|---------------|
| 2024 | VALOR | PORCENTAJE% | VALOR | PORCENTAJE% | VALOR |
| ... | ... | ... | ... | ... | ... |

- **Margen EBIT Inicial**: Justificar nivel inicial (normalizado si hay elementos únicos)
- **Trayectoria de márgenes a largo plazo**: Explicar la trayectoria (compresión/expansión)
- **Tasa Impositiva**: Tasa de impuestos normalizada aplicada
- **Cálculo NOPAT**: Mostrar cálculo para cada período

#### 4.3. Reinversión y Retorno sobre Capital Invertido (ROIC)
**OBLIGATORIO: Crear Tabla de Reinversión en formato Markdown**

**Tabla de Reinversión:**
| Año | NOPAT (M USD) | Capex (M USD) | D&A (M USD) | Capex Neto (M USD) | ΔCapital Trabajo (M USD) | Reinversión (M USD) | Tasa Reinversión | ROIC | Crecimiento |
|-----|---------------|--------------|------------|-------------------|--------------------------|---------------------|------------------|------|------------|
| ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |

- **Capex**: Modelar aumento moderado si aplica (ej: infraestructura IA)
- **Capital de Trabajo Neto (NWC)**: Si es negativo (ingresos diferidos), explicar la entrada de efectivo
- **ROIC**: Modelar disminución desde nivel alto histórico hacia nivel sostenible
- Verificar: Crecimiento = Tasa de Reinversión × ROIC

#### 4.4. Flujo de Caja Libre a la Firma (FCFF)
**OBLIGATORIO: Crear Tabla Resumen de FCFF en formato Markdown**

**Tabla Resumen de FCFF:**
| Año | NOPAT (M USD) | Capex Neto (M USD) | ΔCapital Trabajo (M USD) | FCFF (M USD) | VP (WACC=X%) (M USD) |
|-----|---------------|--------------------|---------------------------|--------------|----------------------|
| 2025 | ... | ... | ... | ... | ... |
| ... | ... | ... | ... | ... | ... |
| 2034 | ... | ... | ... | ... | ... |

Fórmula: **FCFF = NOPAT - (Capex Neto + ΔCapital Trabajo)**

#### 4.5. Tasa de Descuento (WACC)
**OBLIGATORIO: Desglose Completo de WACC**

**Costo del Capital (Ke) = X%**
- Fórmula: Ke = Rf + β × ERP
- **Tasa Libre de Riesgo (Rf)**: X% (justificar: rendimiento del bono del Tesoro a 10 años, fecha)
- **Prima de Riesgo del Capital (ERP)**: X% (justificar: estimación razonable para mercado estable)
- **Beta (β)**: X (justificar: re-apalancado, estructura de capital objetivo)
- Cálculo: Ke = X% + X × X% = X%

**Costo de la Deuda después de Impuestos (Kd) = X%**
- Costo de deuda antes de impuestos: X%
- Escudo fiscal: X%
- Kd = X% × (1 - X%) = X%

**Estructura de Capital**
- Pesos objetivo: X% deuda, Y% capital
- Basado en: estructura óptima de largo plazo

**Cálculo WACC**
- WACC = (Y% × Ke) + (X% × Kd) = X% + Y% = **Z%**

#### 4.6. Valor Terminal
**OBLIGATORIO: Cálculo del Valor Terminal**

**Tasa de Crecimiento Terminal (g)**: X%
- Justificar: "Prudentemente por debajo del PIB nominal de largo plazo" o similar
- Rango conservador: 2-3%

**Fórmula Valor Terminal**:
Fórmula: VT = FCFF_año_final × (1 + g) / (WACC - g)
Ejemplo: VT = VALOR_FCFF × (1 + TASA_CRECIMIENTO) / (WACC - TASA_CRECIMIENTO)
Resultado: VT en millones

**Valor Presente del Valor Terminal**:
Fórmula: VP(VT) = VT / (1 + WACC)^10
Ejemplo: VP(VT) = VALOR_TERMINAL / (1 + WACC)^10
Resultado: VP(VT) en millones

### Parte V: Resultados - Valor Intrínseco

#### 5.1. Resultados del Modelo DCF
**OBLIGATORIO: Visualización de Escenarios en tres tarjetas lado a lado**

**Tarjeta 1: Escenario Bajista - El Umbral Bajo**
- Color: Amarillo/Naranja
- **Valor Intrínseco**: ≈$X (USD) / (Local: Y)
- **Resumen**: "Solo X% por debajo del precio actual"
- **Supuestos Clave**: 
  - Lista con iconos descritos (Competencia intensa, Márgenes comprimen a X%)

**Tarjeta 2: Escenario Base - Valor Intrínseco**
- Color: Verde
- **Valor Intrínseco**: ≈$X (USD) / (Local: Y)
- **Resumen**: "Perfil asimétrico favorable"
- **Derivado De**:
  - VP de FCFF 10 Años: $X
  - VP de Valor Terminal: $Y

**Tarjeta 3: Escenario Alcista - Potencial Asimétrico**
- Color: Azul
- **Valor Intrínseco**: ≈$X (USD) / (Local: Y)
- **Resumen**: "Inmensa optionalidad"
- **Supuestos Clave**:
  - Crecimiento extendido a doble dígito
  - Márgenes elevados en X%

**Tabla Resumen de Escenarios:**
| Escenario | CAGR 10 Años | Margen EBIT Terminal | WACC | Crecimiento Terminal | Valor Intrínseco | % vs Actual |
|-----------|--------------|---------------------|------|----------------------|------------------|-------------|
| Bajista | X% | Y% | Z% | A% | $X | -Z% |
| Base | X% | Y% | Z% | A% | $Y | +W% |
| Alcista | X% | Y% | Z% | A% | $Z | +V% |

#### 5.2. Expectativas Implícitas del Mercado (DCF Inverso)
**OBLIGATORIO: Visualización de DCF Inverso**

**Título**: "Expectativas Implícitas del Mercado (DCF Inverso)"

**Texto introductorio**: "El precio actual de $X por acción implica un futuro donde:"

**OBLIGATORIO: Crear dos cajas lado a lado con borde rojo (expectativas negativas):**

**Caja 1: "Colapso del Crecimiento"**
- Icono: gráfico de línea descendente (descrito)
- **Texto destacado en rojo**: "El crecimiento de ingresos cae de **>X%** a **bajo-dígito-simple** en 3-4 años"
- Sub-bullet: "El mercado espera desaceleración aguda"

**Caja 2: "Colapso de Márgenes"**
- Icono: gráfico de pastel con flecha descendente (descrito)
- **Texto destacado en rojo**: "Los márgenes EBIT se contraen permanentemente a **X-Y%** (**>X puntos base de caída**)"
- Sub-bullet: "Más de X puntos base de compresión"

**Conclusión (caja verde):**
- "Oportunidad de Inversión Atractiva"
- "El mercado está valorando [Empresa] como si nuestro **Escenario Bajista** fuera el resultado más probable"
- "Esta brecha entre expectativas bajas y nuestro más probable **Escenario Base** crea un margen de seguridad sustancial"

#### 5.3. Cálculo Final de Valor Empresarial y Valor del Capital
Cálculo:
VP de FCFF Etapa 1 (Años 1-10): VALOR_PV_FCFF millones
VP de Valor Terminal: VALOR_PV_TERMINAL millones
Valor Empresarial: VALOR_PV_FCFF + VALOR_PV_TERMINAL = VALOR_EV millones

Deuda Neta: ~VALOR_DEBT millones (o Efectivo Neto: ~VALOR_CASH millones)
Valor del Capital: VALOR_EV - VALOR_DEBT = VALOR_EQUITY millones

Acciones Diluidas en Circulación: NUMERO_ACCIONES millones
Valor Intrínseco por Acción (Escenario Base): VALOR_EQUITY / NUMERO_ACCIONES = PRECIO_POR_ACCION

### Parte VI: Análisis Competitivo - Duopoly/Oligopoly Showdown

#### 6.1. [Duopolio]: [Empresa] vs [Competidor Principal]
**OBLIGATORIO: Tabla 3: Análisis Comparativo del Duopolio/Oligopolio**

[Igual estructura que InvestmentThesis]

**OBLIGATORIO: Crear descripciones de gráficos visuales en texto:**

**Gráfico 1: "Comparativa de Múltiplos de Valoración"**
Describir en texto:
- Gráfico de barras comparativo
- P/E (Fwd): [Empresa] ~Xx vs [Competidor] ~Yx
- P/S (TTM): [Empresa] ~Xx vs [Competidor] ~Yx
- Precio/Flujo de Caja Libre (TTM): [Empresa] ~Xx vs [Competidor] ~Yx (muy superior)
- Caption: "[Empresa] cotiza a una fracción de la valoración de [Competidor] en P/E, P/S y P/FCF, una desconexión no respaldada por fundamentos"

**Gráfico 2: "Salud Financiera y Eficiencia"**
Describir en texto:
- Gráfico de barras comparativo
- ROE (TTM): [Empresa] ~X% vs [Competidor] ~Y%
- Margen Operativo: [Empresa] ~X% vs [Competidor] ~Y%
- Ratio D/E: [Empresa] ~X vs [Competidor] ~Y
- Caption: "[Empresa] demuestra eficiencia de capital superior con ROE más alto y balance significativamente más conservador (menor D/E)"

#### 6.2. Pipeline de Innovación: Batalla por el Futuro
Si aplica a la industria, crear sección con:

**Título**: "Pipeline de Innovación: Batalla por el Futuro"
**Subtítulo**: "El valor a largo plazo está dictado por el pipeline de I+D. Mientras [Competidor] tiene un candidato fuerte, el pipeline de [Empresa] es robusto y subestimado."

**OBLIGATORIO: Dos secciones lado a lado:**

**Sección Izquierda: [Empresa]**
- Lista de candidatos clave del pipeline con:
  - Nombre del producto
  - Descripción breve
  - Datos de eficacia si están disponibles

**Sección Derecha: [Competidor]**
- Lista de candidatos clave del pipeline
- Si hay datos decepcionantes, destacar en rojo

#### 6.3. Panorama de Tecnología: Eficacia vs Conveniencia/Capacidad
Si aplica, crear descripción de gráfico de dispersión:
- Eje Y: Eficacia (0.0 - 1.0)
- Eje X: Escala de Conveniencia/Capacidad (← inyectable | oral →)
- Posicionar productos con coordenadas aproximadas:
  - [Producto A]: (X, Y) - descripción
  - [Producto B]: (X, Y) - descripción
- Explicar tendencias: intercambio entre eficacia y conveniencia
- Identificar "cambio de juego" que combina alta eficacia + alta conveniencia

### Parte VII: Moat Resilience Index™ (MRI) - El Diagnóstico del Moat

**OBLIGATORIO: Describir gráfico Radar Chart en texto**

**Título**: "Moat Resilience Index™ (MRI) para [Empresa]"

**Descripción del gráfico radar:**
- Tres ejes: Fortaleza del Moat (arriba), Vulnerabilidad del Moat (abajo-izq), Odio al Moat (abajo-der)
- Escala: 0 (centro) a 10 (círculo exterior)
- Área triangular sombreada conectando los puntos:
  - **Fortaleza del Moat**: X/10 (muy cerca del círculo exterior = alto)
  - **Odio al Moat**: Y/10 (entre círculos Z y W)
  - **Vulnerabilidad del Moat**: Z/10 (en la marca 5 o similar)

**Interpretación**:
- "Perfil visual alto y algo estrecho, enfatizando 'Fortaleza del Moat' fuerte relativo a 'Odio al Moat' y 'Vulnerabilidad del Moat'"
- "MRI sugiere: [Descripción]"

### Parte VIII: Análisis Financiero, Previsiones y Valoración

[Igual que en InvestmentThesis pero más detallado]

### Parte IX: Conclusión - Margen de Seguridad y Veredicto Final

#### 9.1. Cálculo del Margen de Seguridad
**OBLIGATORIO: Visualización Final en tres tarjetas**

**Tarjeta 1: Precio vs Valor Intrínseco**
- Gráfico de barras en texto mostrando la diferencia

**Tarjeta 2: Margen de Seguridad**
- Gráfico donut en texto con porcentaje prominente
- Fórmula: "1 - (Precio Actual / Valor Intrínseco) = X%"

**Tarjeta 3: VEREDICTO FINAL**
- Fondo verde (descrito)
- Verdicto en mayúsculas: "SEVERAMENTE INFRAVALORADA" / "JUSTAMENTE VALORADA" / "SOBREVALORADA"
- Texto: "Un margen de seguridad que excede X% indica una desconexión profunda entre la percepción del mercado y la realidad económica subyacente del negocio."

#### 9.2. Resumen de Escenarios (3-5 Años)
**OBLIGATORIO: Tabla de Escenarios con Probabilidades en formato Markdown**

| Escenario | Probabilidad | Descripción | Resultado Esperado | ROI Potencial |
|-----------|--------------|-------------|-------------------|---------------|
| Bajista | ~25% | Descripción detallada | Resultado esperado | X% |
| Base | ~50% | Descripción detallada | Resultado esperado | Y% |
| Alcista | ~25% | Descripción detallada | Resultado esperado | Z% |

#### 9.3. Recomendación Final
- **Calificación**: COMPRAR / NO COMPRAR / MANTENER
- **Horizonte Temporal**: 3-5 años
- **ROI Potencial**: X% - Y% en un plazo razonable
- **Por qué es un setup de "Hated Moats"**: Explicar la narrativa vs realidad
- **Disclaimer**: Análisis educativo, no consejo de inversión

## Estilo de Redacción

IMPORTANTE:
- Escribe en un tono narrativo, directo y profesional (como un inversor institucional)
- **INCLUYE DESCRIPCIONES DETALLADAS DE GRÁFICOS VISUALES** en texto (barras, donuts, scatter plots, radar charts)
- Usa emojis estratégicamente (✅, 📈, ⚠️, 💰, 🔴, 🟢, 🟡) pero con moderación
- **INCLUYE NÚMEROS ESPECÍFICOS SIEMPRE** (montos en $, porcentajes, múltiplos)
- **CREA TABLAS en Markdown** cuando sea apropiado (Tabla 1, 2, 3, etc.)
- **DESCRIBE GRÁFICOS VISUALES** como si fueran parte del análisis (no los generes, pero descríbelos detalladamente)
- Estructura con encabezados claros (##, ###) y usa "Parte I", "Parte II", etc.
- **INTEGRA el DCF dentro de la tesis**, no los separes - es UN SOLO análisis completo
- Sé objetivo: si la empresa tiene problemas, dilo claramente
- **LONGITUD**: No importa que sea largo - el análisis debe ser exhaustivo y completo

## Ejemplo de Descripción de Gráfico

"**Gráfico de Barras: Precio vs Valor Intrínseco**

La visualización muestra dos barras horizontales:
- **Barra Izquierda (Gris Oscuro)**: Representa el 'Precio Actual' de $X, significativamente más corta
- **Barra Derecha (Verde Vibrante)**: Representa el 'Valor Intrínseco' de $Y, aproximadamente X veces más alta

Debajo del gráfico: 'El precio actual es significativamente menor que su valor intrínseco calculado.'"

## Ejemplo de Análisis Profesional

"Novo Nordisk vivió en el lado soleado de los favoritos del mercado durante dos años. Tuvo el viento de un verdadero cambio médico a sus espaldas, el halo cultural de un fármaco de nombre familiar, y la economía de monopolio temporal que solo aparece unas pocas veces por década. Entonces, de repente, una narrativa diferente tomó el control..."

La inversión ya no es una simple apuesta por el crecimiento evidente del mercado. Esa oportunidad ya ha sido reconocida y cotizada. Una inversión hoy es una apuesta mucho más sofisticada y matizada. Es una apuesta por la capacidad de [Empresa] para mantener su supremacía en tres frentes críticos: Supremacía Tecnológica, Supremacía de Fabricación, y Supremacía de Acceso al Mercado.`;

  // Obtener todos los datos financieros y contextuales
  const news = input.financialData?.news || [];
  const newsText = news.length > 0 
    ? `\n\nNOTICIAS ACTUALES SOBRE LA EMPRESA (Últimos 30 días):\n${news.map((article: any, idx: number) => 
        `${idx + 1}. [${new Date(article.datetime * 1000).toLocaleDateString('es-ES')}] ${article.headline}\n   ${article.summary || ''}\n   Fuente: ${article.source}\n`
      ).join('\n')}`
    : '\n\nNOTICIAS: No se encontraron noticias recientes disponibles.';

  const events = input.financialData?.events || [];
  const eventsText = events.length > 0
    ? `\n\n📅 EVENTOS IMPORTANTES PRÓXIMOS:\n${events.map((event: any, idx: number) => {
        const eventDate = new Date(event.date);
        const daysUntil = Math.ceil((eventDate.getTime() - Date.now()) / (1000 * 60 * 60 * 24));
        const importanceEmoji = event.importance === 'high' ? '🔴' : event.importance === 'medium' ? '🟡' : '🟢';
        return `${importanceEmoji} ${eventDate.toLocaleDateString('es-ES', { year: 'numeric', month: 'long', day: 'numeric' })} (${daysUntil > 0 ? `En ${daysUntil} días` : daysUntil === 0 ? 'HOY' : `${Math.abs(daysUntil)} días atrás`})\n   ${event.event}\n   ${event.description || ''}\n`;
      }).join('\n')}`
    : '';

  const analystData = input.financialData?.analystRecommendations;
  const analystText = analystData
    ? `\n\n📊 RECOMENDACIONES DE ANALISTAS:\n${analystData.strongBuy ? `✅ Strong Buy: ${analystData.strongBuy} | ` : ''}${analystData.buy ? `🟢 Buy: ${analystData.buy} | ` : ''}${analystData.hold ? `🟡 Hold: ${analystData.hold} | ` : ''}${analystData.sell ? `🟠 Sell: ${analystData.sell} | ` : ''}${analystData.strongSell ? `🔴 Strong Sell: ${analystData.strongSell}` : ''}${analystData.targetHigh || analystData.targetMean || analystData.targetLow ? `\n💰 Target Price - High: $${analystData.targetHigh || 'N/A'} | Media: $${analystData.targetMean || 'N/A'} | Low: $${analystData.targetLow || 'N/A'}` : ''}`
    : '';

  const technicalData = input.financialData?.technicalAnalysis;
  const technicalText = technicalData
    ? `\n\n📈 ANÁLISIS TÉCNICO:\nSoporte: $${technicalData.support?.toFixed(2) || 'N/A'} | Resistencia: $${technicalData.resistance?.toFixed(2) || 'N/A'}\nTendencia: ${technicalData.trend === 'up' ? '📈 Al alza' : technicalData.trend === 'down' ? '📉 A la baja' : '➡️ Lateral'}\nVolumen Promedio: ${technicalData.avgVolume ? (technicalData.avgVolume / 1000000).toFixed(2) + 'M' : 'N/A'} | Tendencia de volumen: ${technicalData.volumeTrend === 'increasing' ? '📈 Aumentando' : technicalData.volumeTrend === 'decreasing' ? '📉 Disminuyendo' : '➡️ Estable'}`
    : '';

  const indexData = input.financialData?.indexComparison;
  const indexText = indexData?.vsSP500
    ? `\n\n📊 RENDIMIENTO vs S&P 500:\n${indexData.vsSP500.change > 0 ? '✅' : '❌'} ${input.companyName}: ${indexData.vsSP500.change > 0 ? '+' : ''}${indexData.vsSP500.change.toFixed(2)}% ${indexData.vsSP500.change > 0 ? 'superando' : 'por debajo de'} el S&P 500`
    : '';

  const insiderData = input.financialData?.insiderTrading;
  const insiderText = insiderData && Array.isArray(insiderData.data) && insiderData.data.length > 0
    ? `\n\n👔 INSIDER TRADING:\n${insiderData.data.slice(0, 10).map((trans: any, idx: number) => {
        const date = trans.transactionDate ? new Date(trans.transactionDate * 1000).toLocaleDateString('es-ES') : 'N/A';
        const type = trans.transactionCode === 'P' ? '✅ Compra' : trans.transactionCode === 'S' ? '❌ Venta' : 'N/A';
        const shares = trans.shares ? trans.shares.toLocaleString() : 'N/A';
        return `${idx + 1}. [${date}] ${trans.name || 'N/A'}: ${type} de ${shares} acciones a $${trans.price?.toFixed(2) || 'N/A'}`;
      }).join('\n')}`
    : '';

  const peers = input.financialData?.peers || [];
  const peersText = peers.length > 0
    ? `\n\n🏢 COMPETIDORES DEL SECTOR:\n${peers.join(', ')}`
    : '';

  const prompt = `Genera un ANÁLISIS COMPLETO DE INVERSIÓN que integre TESIS DE INVERSIÓN y ANÁLISIS DCF para ${input.companyName} (${input.symbol}).

PRECIO ACTUAL: $${input.currentPrice.toFixed(2)}

DATOS FINANCIEROS DISPONIBLES:
${JSON.stringify(input.financialData, null, 2)}
${newsText}
${eventsText}
${analystText}
${technicalText}
${indexText}
${insiderText}
${peersText}

IMPORTANTE:
- **TODO DEBE ESTAR EN ESPAÑOL** excepto nombres propios de empresas, productos, acrónimos técnicos estándar (DCF, FCFF, NOPAT, WACC, ROIC, EBIT, EBITDA, PER, etc.) y términos que no tienen traducción directa
- **FORMATO DE TABLAS**: CRÍTICO - Usa el formato EXACTO de Markdown para tablas. Cada tabla DEBE tener:
  1. Fila de encabezados: | Columna1 | Columna2 | Columna3 |
  2. Fila separadora OBLIGATORIA: |:---:|:---:|:---:| o |---|:---:|:---:| (con guiones IGUALES o mínimo 3 por columna)
  3. Filas de datos: | Dato1 | Dato2 | Dato3 |
  4. IMPORTANTE: Todas las columnas DEBEN tener el MISMO número de pipes (|) en cada fila
  5. IMPORTANTE: Cada fila DEBE empezar y terminar con un pipe (|)
  6. IMPORTANTE: No dejes espacios inconsistentes entre pipes - usa un solo espacio antes y después del contenido
  7. Usa formato numérico consistente: $1.234,56 millones o números con comas/puntos según convención española
  8. EJEMPLO CORRECTO:
     | Año | Ingresos (M USD) | Crecimiento |
     |:---:|:---------------:|:-----------:|
     | 2024 | 157.980,1 | - |
     | 2025 | 186.416,5 | 18,00% |
- INTEGRA completamente el DCF dentro de la tesis - NO los separes, es UN SOLO análisis
- INCLUYE DESCRIPCIONES DETALLADAS DE GRÁFICOS VISUALES en texto (barras, donuts, scatter plots, radar charts)
- CREA TABLAS en Markdown correctamente formateadas para todas las proyecciones financieras
- Incluye el cálculo completo del DCF con todas las tablas de proyección
- Calcula y muestra el Margen de Seguridad de forma prominente
- Incluye DCF Inverso (Expectativas Implícitas del Mercado) con visualizaciones descritas
- Si hay competidores principales, crea comparativas visuales detalladas (gráficos de barras descritos)
- Si aplica, incluye análisis de pipeline con comparativas
- Incluye Índice de Resiliencia del Moat (MRI) con descripción del gráfico radar
- NO importa que sea largo - debe ser exhaustivo y completo
- Analiza todas las noticias recientes y eventos próximos
- Considera todos los aspectos técnicos, competitivos, regulatorios y financieros
- Genera el análisis más completo y profesional posible`;

  const payload = {
    contents: [
      {
        role: 'user',
        parts: [
          {
            text: `${system}\n\n${prompt}`,
          },
        ],
      },
    ],
  };

  try {
    const model = process.env.GEMINI_MODEL_THESIS || 'gemini-2.5-flash';
    const endpoint = `https://generativelanguage.googleapis.com/v1/models/${model}:generateContent?key=${apiKey}`;
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      cache: 'no-store',
    });
    const json = await res.json().catch(() => ({} as any));

    if (!res.ok) {
      const apiError = json?.error?.message || JSON.stringify(json);
      console.error('Gemini API error', res.status, apiError);
      return `IA desactivada temporalmente: (${res.status}) ${apiError}`;
    }
    const text: string | undefined = json?.candidates?.[0]?.content?.parts?.[0]?.text;
    return text || 'No se pudo generar el análisis completo en este momento.';
  } catch (e) {
    console.error('Gemini error', e);
    return 'Error al generar el análisis completo con IA.';
  }
}

export async function generateDCFAnalysis(input: {
  symbol: string;
  companyName: string;
  financialData: any;
  currentPrice: number;
}): Promise<string> {
  try {
    const { getAuth } = await import('@/lib/better-auth/auth');
    const auth = await getAuth();
    const session = await auth.api.getSession({ headers: await headers() });
    if (!session?.user) throw new Error('Usuario no autenticado');
  } catch (error: any) {
    // Si MongoDB no está disponible, permitir uso en modo desarrollo
    if (process.env.NODE_ENV === 'development' && error.message?.includes('MongoDB')) {
      console.warn('⚠️  MongoDB no disponible. Generando análisis DCF sin autenticación (modo desarrollo).');
    } else {
      throw new Error('Usuario no autenticado');
    }
  }

  const apiKey = process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY;
  if (!apiKey) {
    return 'IA desactivada: falta la clave de Gemini en el entorno.';
  }

  const system = `Eres un analista financiero profesional especializado en análisis DCF (Discounted Cash Flow). Genera un análisis DCF completo y profesional en español siguiendo EXACTAMENTE esta estructura:

## 1. Brief Overview
- Contexto del negocio y posición en el mercado
- Modelo de negocio principal
- Moat competitivo y ventajas sostenibles
- Veredicto: Sobreevaluada / Justa / Infravalorada
- Precio objetivo (Base Case) y margen de seguridad si es relevante

## 2. Business & Financial Context
- Segmentos de negocio principales
- Fuentes de ingresos (porcentajes aproximados)
- Modelo de negocio (suscripciones, ventas, etc.)
- Moat competitivo detallado
- Rentabilidad histórica (márgenes operativos, ROIC)
- Competidores y posición competitiva

## 3. Discounted Cash Flow (DCF): Assumptions & Methodology

### 1/ Revenue Forecast (Years 1–10)
- Proyección de crecimiento de ingresos año por año (Year 1, Years 2-5, Years 6-10)
- Justificación basada en el tamaño del mercado, crecimiento del mercado, capacidad de la empresa para superar al mercado
- CAGR implícito a 10 años

### 2/ Profitability (EBIT → NOPAT)
- Margen EBIT inicial y trayectoria proyectada
- Tasa de impuestos normalizada
- Cálculo de NOPAT para cada período

### 3/ Reinvestment & ROIC
- Capex como % de ingresos
- Cambios en capital de trabajo (NWC)
- ROIC incremental y su evolución

### 4/ Free Cash Flow to the Firm (FCFF)
- Fórmula: FCFF = NOPAT - (Capex - D&A + ΔNWC)
- Tabla con FCFF proyectado año por año (Years 1-10)

### 5/ Discount Rate (WACC)
- Costo de Equity (Ke) con fórmula: Ke = Rf + β × ERP
  - Tasa libre de riesgo (Rf): usar ~4% (10-year U.S. Treasury yield)
  - Equity Risk Premium (ERP): ~4.1%
  - Beta (β): estimar basado en sector y datos disponibles
- Costo de Deuda (Kd) después de impuestos
- Estructura de capital objetivo (deuda/equity)
- Cálculo final de WACC

### 6/ Terminal Value
- Tasa de crecimiento terminal (g): justificar (típicamente 2-3%)
- Fórmula: TV = FCFF_2034 × (1+g) / (WACC – g)
- Valor presente del terminal value

## 4. Results & Market-Implied Expectations

### Resultados del Modelo
- PV de Stage 1 FCFFs (Years 1-10)
- PV de Terminal Value
- Enterprise Value
- Equity Value
- Valor intrínseco por acción (Base Case)

### Escenarios
- Bear Case: CAGR menor, márgenes más bajos, WACC más alto
- Base Case: escenario central
- Bull Case: CAGR mayor, márgenes más altos, WACC más bajo

### Reverse DCF
- ¿Qué CAGR implícito está asumiendo el precio actual del mercado?
- Comparación con la guía de management y promedios históricos

## 5. Conclusion: Margin of Safety & Final Verdict
- Margen de seguridad: 1 – (Precio Actual / Valor Intrínseco)
- Veredicto final con justificación
- Advertencia sobre disclosure (análisis informativo, no consejo de inversión)

IMPORTANTE:
- Usa números reales cuando estén disponibles en los datos financieros
- Si faltan datos, estima de manera conservadora y transparente
- Estructura el análisis con Markdown claro (##, ###, listas, tablas)
- Incluye cálculos numéricos cuando sea posible
- Sé profesional pero accesible
- Menciona limitaciones cuando los datos sean incompletos`;

  // Obtener noticias actuales de la empresa
  const news = input.financialData?.news || [];
  const newsText = news.length > 0 
    ? `\n\nNOTICIAS ACTUALES SOBRE LA EMPRESA (Últimos 30 días):\n${news.map((article: any, idx: number) => 
        `${idx + 1}. [${new Date(article.datetime * 1000).toLocaleDateString('es-ES')}] ${article.headline}\n   ${article.summary || ''}\n   Fuente: ${article.source}\n`
      ).join('\n')}`
    : '\n\nNOTICIAS: No se encontraron noticias recientes disponibles.';

  // Obtener eventos importantes de la empresa
  const events = input.financialData?.events || [];
  const eventsText = events.length > 0
    ? `\n\nEVENTOS IMPORTANTES PRÓXIMOS DE LA EMPRESA:\n${events.map((event: any, idx: number) => {
        const eventDate = new Date(event.date);
        const daysUntil = Math.ceil((eventDate.getTime() - Date.now()) / (1000 * 60 * 60 * 24));
        const importanceEmoji = event.importance === 'high' ? '🔴' : event.importance === 'medium' ? '🟡' : '🟢';
        return `${importanceEmoji} ${idx + 1}. ${eventDate.toLocaleDateString('es-ES', { year: 'numeric', month: 'long', day: 'numeric' })} (${daysUntil > 0 ? `En ${daysUntil} días` : daysUntil === 0 ? 'Hoy' : `${Math.abs(daysUntil)} días atrás`})\n   ${event.event}\n   ${event.description || ''}\n`;
      }).join('\n')}`
    : '\n\nEVENTOS: No se encontraron eventos próximos programados.';

  // Obtener recomendaciones de analistas
  const analystData = input.financialData?.analystRecommendations;
  const analystText = analystData
    ? `\n\n📊 RECOMENDACIONES DE ANALISTAS:\n${analystData.strongBuy ? `Strong Buy: ${analystData.strongBuy} | ` : ''}${analystData.buy ? `Buy: ${analystData.buy} | ` : ''}${analystData.hold ? `Hold: ${analystData.hold} | ` : ''}${analystData.sell ? `Sell: ${analystData.sell} | ` : ''}${analystData.strongSell ? `Strong Sell: ${analystData.strongSell}` : ''}${analystData.targetHigh || analystData.targetMean || analystData.targetLow ? `\nTarget Price - High: $${analystData.targetHigh || 'N/A'} | Mean: $${analystData.targetMean || 'N/A'} | Low: $${analystData.targetLow || 'N/A'}` : ''}`
    : '';

  // Obtener análisis técnico
  const technicalData = input.financialData?.technicalAnalysis;
  const technicalText = technicalData
    ? `\n\n📈 ANÁLISIS TÉCNICO:\nSoporte: $${technicalData.support?.toFixed(2) || 'N/A'} | Resistencia: $${technicalData.resistance?.toFixed(2) || 'N/A'}\nTendencia: ${technicalData.trend === 'up' ? '📈 Al alza' : technicalData.trend === 'down' ? '📉 A la baja' : '➡️ Lateral'}\nVolumen Promedio (últimos 20 días): ${technicalData.avgVolume ? (technicalData.avgVolume / 1000000).toFixed(2) + 'M' : 'N/A'} | Tendencia de volumen: ${technicalData.volumeTrend === 'increasing' ? '📈 Aumentando' : technicalData.volumeTrend === 'decreasing' ? '📉 Disminuyendo' : '➡️ Estable'}`
    : '';

  // Obtener comparación con índices
  const indexData = input.financialData?.indexComparison;
  const indexText = indexData?.vsSP500
    ? `\n\n📊 RENDIMIENTO vs S&P 500 (últimos 12 meses):\n${indexData.vsSP500.change > 0 ? '✅' : '❌'} ${input.companyName}: ${indexData.vsSP500.change > 0 ? '+' : ''}${indexData.vsSP500.change.toFixed(2)}% ${indexData.vsSP500.change > 0 ? 'superando' : 'por debajo de'} el ${indexData.vsSP500.symbol}`
    : '';

  // Obtener insider trading
  const insiderData = input.financialData?.insiderTrading;
  const insiderText = insiderData && Array.isArray(insiderData.data) && insiderData.data.length > 0
    ? `\n\n👔 INSIDER TRADING (Actividad de Directivos):\n${insiderData.data.slice(0, 10).map((trans: any, idx: number) => {
        const date = trans.transactionDate ? new Date(trans.transactionDate * 1000).toLocaleDateString('es-ES') : 'N/A';
        const type = trans.transactionCode === 'P' ? 'Compra' : trans.transactionCode === 'S' ? 'Venta' : trans.transactionCode || 'N/A';
        const shares = trans.shares ? trans.shares.toLocaleString() : 'N/A';
        return `${idx + 1}. [${date}] ${trans.name || 'N/A'}: ${type} de ${shares} acciones a $${trans.price?.toFixed(2) || 'N/A'}`;
      }).join('\n')}`
    : '';

  // Obtener datos ESG
  const esgData = input.financialData?.esgData;
  const esgText = esgData
    ? `\n\n🌱 ANÁLISIS ESG (Sostenibilidad):\n${esgData.totalESG ? `Score Total: ${esgData.totalESG}/100` : ''}${esgData.environmentScore ? ` | Medio Ambiente: ${esgData.environmentScore}/100` : ''}${esgData.socialScore ? ` | Social: ${esgData.socialScore}/100` : ''}${esgData.governanceScore ? ` | Gobernanza: ${esgData.governanceScore}/100` : ''}`
    : '';

  // Análisis de competencia (usando peers si están disponibles)
  const peers = input.financialData?.peers || [];
  const peersText = peers.length > 0
    ? `\n\n🏢 COMPETIDORES DEL SECTOR:\n${peers.join(', ')}`
    : '';

  const prompt = `Genera un análisis DCF completo para ${input.companyName} (${input.symbol}).

PRECIO ACTUAL: $${input.currentPrice.toFixed(2)}

DATOS FINANCIEROS DISPONIBLES:
${JSON.stringify(input.financialData, null, 2)}
${newsText}
${eventsText}
${analystText}
${technicalText}
${indexText}
${insiderText}
${esgText}
${peersText}

IMPORTANTE:
- Analiza las noticias recientes para entender el contexto actual de la empresa
- PRESTA ESPECIAL ATENCIÓN a los eventos próximos (earnings, anuncios, etc.) y su potencial impacto en el precio de la acción
- Los eventos marcados con 🔴 (high) son especialmente críticos y pueden causar volatilidad significativa
- Compara tu precio objetivo DCF con el consenso de analistas (target price) si está disponible
- **ANÁLISIS TÉCNICO**: Considera soporte/resistencia y tendencia de precio en tu evaluación
- **COMPARACIÓN CON ÍNDICES**: Menciona si la acción está superando o bajoperformeando al S&P 500
- **INSIDER TRADING**: Analiza las transacciones de directivos (compras son positivas, ventas masivas pueden ser señal de alerta)
- **ANÁLISIS DE VOLUMEN**: Considera la liquidez y tendencia de volumen (volumen creciente confirma tendencias)
- **COMPETENCIA**: Si hay datos de competidores, compara métricas clave (PER, ROE, márgenes) con pares del sector
- **ESG**: Si hay datos ESG, evalúa cómo puede afectar la valoración a largo plazo
- Considera eventos recientes (earnings, cambios de management, acuerdos estratégicos, etc.) en tus proyecciones
- Si hay noticias sobre resultados trimestrales recientes, úsalas para ajustar tus proyecciones
- Incorpora cualquier información relevante sobre la estrategia de la empresa mencionada en las noticias
- Si faltan algunos datos financieros históricos (como ingresos anuales, cash flow libre, etc.), estima valores conservadores basándote en las métricas disponibles, las noticias recientes y el contexto del sector. Sé transparente sobre las limitaciones de datos.`;

  const payload = {
    contents: [
      {
        role: 'user',
        parts: [
          {
            text: `${system}\n\n${prompt}`,
          },
        ],
      },
    ],
  };

  try {
    // Usar un modelo más potente para análisis complejos (Gemini 2.5)
    const model = process.env.GEMINI_MODEL_DCF || 'gemini-2.5-flash';
    const endpoint = `https://generativelanguage.googleapis.com/v1/models/${model}:generateContent?key=${apiKey}`;
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      cache: 'no-store',
    });
    const json = await res.json().catch(() => ({} as any));

    if (!res.ok) {
      const apiError = json?.error?.message || JSON.stringify(json);
      console.error('Gemini API error', res.status, apiError);
      return `IA desactivada temporalmente: (${res.status}) ${apiError}`;
    }
    const text: string | undefined = json?.candidates?.[0]?.content?.parts?.[0]?.text;
    return text || 'No se pudo generar el análisis DCF en este momento.';
  } catch (e) {
    console.error('Gemini error', e);
    return 'Error al generar el análisis DCF con IA.';
  }
}

export async function generateInvestmentThesis(input: {
  symbol: string;
  companyName: string;
  financialData: any;
  currentPrice: number;
}): Promise<string> {
  const auth = await getAuth();
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session?.user) throw new Error('Usuario no autenticado');

  const apiKey = process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY;
  if (!apiKey) {
    return 'IA desactivada: falta la clave de Gemini en el entorno.';
  }

  const system = `Eres un analista financiero profesional y experto inversor especializado en due diligence exhaustivo de nivel institucional. Genera una TESIS DE INVERSIÓN completa, profunda, exhaustiva y narrativa en español, siguiendo EXACTAMENTE esta estructura y estilo (basado en análisis profesionales de referencia como PayPal y Novo Nordisk):

## Estructura Obligatoria del Análisis (Usar "Parte I", "Parte II", etc.)

### Parte I: Tesis de Inversión y Resumen Ejecutivo

#### 1. La Pregunta Central
- Plantear la pregunta de inversión de forma directa: "¿Es [Empresa] una compañía en la que puedes invertir?"
- La respuesta debe ser matizada y compleja, nunca binaria (no es "sí" o "no" simple)

#### 2. La Tesis Alcista (Bull Thesis) - Estructura Numerada Obligatoria
Presentar de forma estructurada con números y porcentajes específicos:
- **Foso Económico (Moat)**: Describir los 3-4 pilares del moat competitivo (ciencia/tecnología, fabricación/operaciones, validación/clínica/regulatoria, acceso al mercado, etc.)
- **Revolución Secular**: Explicar cómo la empresa está liderando una transformación del sector/mercado (no solo crecimiento, sino cambio de paradigma)
- **Desbloqueo de Mercado**: Describir cómo ha desbloqueado o creado un mercado masivo (TAM enorme, penetración actual minúscula, mercado en infancia)
- **Dominio de Fabricación/Operaciones**: Capacidades distintivas que los competidores tardarán años en igualar
- **Validación Clínica/Regulatoria/Mercado**: Evidencia (ensayos de resultados definitivos, aprobaciones, datos de mercado) que redefinen el valor para pagadores/sistemas de salud

#### 3. La Tesis Bajista (Bear Thesis) - Estructura Numerada Obligatoria
Presentar de forma estructurada los riesgos materiales (no teóricos):
- **Riesgo de Concentración Extremo**: Dependencia abrumadora de un producto/segmento/cliente para TODO el crecimiento y rentabilidad
- **Competencia Feroz y Disruptiva**: Amenazas competitivas específicas con nombres de competidores y por qué son formidables
- **Riesgo Regulatorio de Precios**: Amenazas regulatorias específicas (IRA, regulación europea, etc.) y su impacto cuantificable
- **Valoración "Valorada a la Perfección"**: La acción cotiza como empresa de hiper-crecimiento (tech-like) sin margen para errores
- **Riesgo de Ejecución**: Complejidad operativa que puede fallar (planes de CapEx, reestructuración, etc.)

#### 4. Valoración y Posicionamiento
- PER actual vs promedios históricos y vs sector tradicional
- Comparación explícita: "La valoración se asemeja más a [empresa tech] que a [sector tradicional]"
- Explicar por qué existe esta prima de valoración (expectativas de crecimiento secular, mercado en formación, duopolio, etc.)
- Rango de precio objetivo de analistas con dispersión masiva = falta de consenso = oportunidad/riesgo
- La valoración actual EXIGE perfección continua

#### 5. Veredicto del Analista (Resumen)
- La inversión ya NO es una apuesta simple por el crecimiento evidente (ese ya está cotizado)
- Es una apuesta sofisticada sobre 3-4 factores críticos:
  1. **Supremacía Tecnológica/Producto**: Pipeline vs competidores
  2. **Supremacía de Fabricación/Operaciones**: Ejecución de planes de inversión masivos
  3. **Supremacía de Acceso al Mercado**: Navegación regulatoria y de pagadores (paradoja de volumen vs precio)
  4. **Supremacía de Valoración**: Capacidad de mantener múltiplos elevados frente a vientos en contra

### Parte II: El Fundamento del Negocio (Ciencia/Tecnología/Modelo de Negocio)

#### 2.1. El Eje Central: [Tema Clave que Impulsa el 90% del Valor]
Si farmacéutica/biotecnología: Explicar la ciencia fundamental (hormonas, mecanismos, etc.)
Si tecnología: Explicar la tecnología/plataforma central (arquitectura, algoritmos, etc.)
Si servicios: Explicar el modelo de negocio/ecosistema (red de dos caras, marketplace, etc.)
- Describir el mecanismo/tecnología/modelo clave que impulsa el 90% del valor
- Explicar la "genialidad" o diferenciación clave
- Comparar con alternativas antiguas/inferiores y por qué son mejores

#### 2.2. Los Productos/Servicios Relevantes (El Arsenal)
**OBLIGATORIO: Crear Tabla 1: Comparativa de [Productos/Servicios] Clave**

| Producto/Servicio | Compañía | Mecanismo/Característica | Eficacia/Métrica | Posicionamiento |
|-------------------|----------|--------------------------|------------------|-----------------|
| [Producto A] | [Empresa/Competidor] | [Descripción técnica] | [Métrica específica] | [Estado actual] |
| [Producto B] | ... | ... | ... | ... |

Incluir productos propios vs competidores, explicar diferencias clave y por qué importan

#### 2.3. Las "Trampas" (Probando el Círculo de Competencia)
- Identificar productos/servicios/tecnologías mencionadas que NO son relevantes para la tesis
- Explicar por qué son distracciones (tecnología antigua, segmento no core, modelo obsoleto, etc.)
- Esto filtra a inversores que no entienden el negocio core
- Un inversor competente debe identificar instantáneamente qué es relevante vs distracciones

### Parte III: El Modelo de Crecimiento - Anatomía de un Gigante en Expansión

#### 3.1. La Explicación Simple (2 minutos)
- Explicar cómo crece la empresa en lenguaje simple para un amigo
- Narrativa accesible pero precisa: "Novo está creciendo al ser la primera compañía en tratar médicamente con éxito la obesidad a escala global..."

#### 3.2. El Análisis Profundo: Los Tres (o más) Motores de Crecimiento
**Motor 1: [Nombre del Motor Fundacional]**
- Descripción detallada con números específicos
- Este es el motor fundacional/"vaca lechera" que financia todo
- Ingresos actuales, tendencia, márgenes

**Motor 2: [Nombre del Motor de Hiper-crecimiento]**
- Descripción detallada con números específicos
- Este es el motor de hiper-crecimiento/explosión
- TAM (Total Addressable Market) asombroso
- Penetración actual minúscula (ej: <5%)
- No es mercado maduro; está en infancia
- Limitación principal: demanda casi infinita vs capacidad de fabricación/suministro

**Motor 3: [Nombre del Motor Defensivo/Estratégico]**
- Descripción detallada
- Este es el motor más sofisticado para defender el moat a largo plazo
- Expansión de indicaciones/mercados/usos
- Ensayos/validaciones clave (ej: SELECT para Novo, ensayos de resultados definitivos)
- Implicaciones de tercer orden: no solo para FDA/equivalent, sino para pagadores/sistemas de salud
- Transforma la conversación sobre precios y acceso

#### 3.3. La Vulnerabilidad Oculta del Crecimiento
- El ÚNICO factor que frena el crecimiento: capacidad de fabricación/talento/distribución (no competencia, no regulación - aún)
- Cuellos de botella específicos (API, fill-finish, etc.)
- Planes de inversión masivos (CapEx de $X mil millones)
- Riesgos de ejecución: cualquier retraso en puesta en marcha = riesgo directo para previsiones

### Parte IV: Evaluación del Pipeline/Futuro (Si aplica a la industria)

#### 4.1. Un Manual para Inversores sobre [Pipeline/Próximos Productos]
Si aplica (farmacéutica/biotecnología/tech):
- Fases del desarrollo (I, II, III) o etapas equivalentes explicadas
- Endpoints (criterios de valoración) primarios vs secundarios explicados
- Significancia estadística (valor p) vs relevancia clínica/comercial explicadas
- Error común: estadísticamente significativo pero clínicamente irrelevante

#### 4.2. Evaluación de las Probabilidades (Risk-Adjusting the Pipeline)
- Probabilidad de éxito (PoS) no es estática; cambia con cada fase
- PoS histórica: Fase I ~10%, Fase III 50-65%
- PoS específica de la empresa/producto: más alta si datos de Fase II son fuertes
- Descuento por riesgo de fallo siempre existe
- Un inversor debe descontar el valor futuro estimado por esta PoS

#### 4.3. Aplicación Práctica: El Pipeline Futuro de [Empresa]
**OBLIGATORIO: Crear Tabla 2: Hoja de Ruta del Pipeline/Futuro**

| Producto/Servicio | Indicación/Mercado | Fase/Etapa | Próximos Hitos | PoS Estimada |
|-------------------|-------------------|------------|----------------|--------------|
| [Candidato A] | [Mercado] | Fase III | Datos esperados [fecha] | [X%] |
| ... | ... | ... | ... | ... |

### Parte V: El Campo de Batalla Regulatorio y de Precios - Riesgos Existenciales

#### 5.1. El Espejismo del "Precio de Lista" y el Rol de [Intermediarios]
- Aclarar quién fija/negocia precios (NO es FDA/equivalent regulatorio)
- Intermediarios clave (PBMs, distribuidores, gobiernos) y su rol
- Precio de lista (WAC) vs precio neto real recibido
- Descuentos/rebajas estimadas (ej: 40-60% más bajo que precio de lista)
- Secreto comercial muy bien guardado

#### 5.2. El Acantilado de Patentes/Ventajas y la Estrategia del "Muro de Ladrillos"
- Expiración de patentes clave/ventajas competitivas temporales (ej: 2031-2032)
- NO depender de una sola patente/ventaja
- Estrategia de "muro de patentes/barreras":
  - Patentes de formulación/dispositivo/combinación/uso que extienden protección
  - Barreras de entrada para competidores (biosimilares/genéricos/imitadores)
- Objetivo: impedir intercambiabilidad automática, forzar desarrollo propio de competidores

#### 5.3. El Gran Recorte: [Regulación Específica]
- Legislación disruptiva relevante (IRA, MiCA, PSD3, DMA, etc.) explicada
- Impacto diferenciado por producto/segmento:
  - Producto A: Cubierto, candidato para negociación de precios (riesgo alto)
  - Producto B: Exento (razón específica), pero paradoja regulatoria
- **Arma de doble filo**: Desbloquear volumen masivo vs erosionar márgenes
- Paradoja específica: éxito en un frente crea riesgo en otro
- Tesis alcista vs bajista sobre si volumen compensa erosión de precio

### Parte VI: La Batalla Competitiva - Panorama Competitivo

#### 6.1. El [Duopolio/Oligopolio/Competencia]: [Empresa] vs [Competidor Principal]
**OBLIGATORIO: Crear Tabla 3: Análisis Comparativo del [Sector/Competencia]**

| Métrica | [Empresa] | [Competidor 1] | [Competidor 2] | Análisis |
|---------|-----------|----------------|----------------|----------|
| Capitalización | $X | $Y | $Z | ... |
| Producto clave | ... | ... | ... | ... |
| Eficacia/Métrica | ... | ... | ... | ... |
| Pipeline | ... | ... | ... | ... |
| Ventas | ... | ... | ... | ... |
| Crecimiento | ... | ... | ... | ... |
| Márgenes | ... | ... | ... | ... |
| Valoración (P/E) | ... | ... | ... | ... |

**Ventajas de [Empresa]**:
- Liderazgo de mercado (first-mover)
- Capacidades distintivas (fabricación, datos, validaciones)
- Datos/validaciones clave que el competidor no tiene (ej: SELECT, CVOT)

**Desventajas de [Empresa]**:
- Producto principal menos eficaz/potente que competidor
- Capacidad de fabricación/distribución menor (temporal)
- Pipeline menos fuerte

**Ventajas de [Competidor]**:
- Eficacia/producto superior demostrada
- Pipeline de próxima generación más fuerte
- Inversión más agresiva en capacidad

**Desventajas de [Competidor]**:
- Por detrás en [aspecto clave]
- Menor capacidad actual en [área crítica]

#### 6.2. El Resto del Campo (La Segunda Ola)
- Otros competidores (gigantes, startups) y su posición
- Estrategia: NO competir cara a cara en eficacia, sino en modalidad/precio
- Horizonte temporal (3-5 años de distancia)

#### 6.3. Conclusión: ¿Quién Gana?
- Esto NO es "el ganador se lo lleva todo" - el mercado es vasto ("océano azul")
- Ambas empresas pueden crecer simultáneamente a tasas astronómicas durante 5-7 años
- El ganador a corto/medio plazo NO será quien tenga producto marginalmente más eficaz
- **El ganador será quien resuelva los cuellos de botella reales**:
  1. **Ganador de Fabricación/Operaciones**: Quien pueda fabricar/escalar más rápido
  2. **Ganador del Acceso**: Quien use datos/validaciones para asegurar mejor reembolso/acceso
- La batalla se libra en [planta de fabricación/operaciones] y [oficinas de negociadores], NO en [clínica/mercado]

### Parte VII: Análisis Financiero, Previsiones y Valoración

#### 7.1. Análisis de Estados Financieros
- **Crecimiento de Ingresos**: Explosivo (30-50% YoY) vs moderado, impulsado por [motor clave]
- **Márgenes**: Máquina de imprimir dinero vs márgenes comprimidos
  - Márgenes brutos: X% (envidia del mundo corporativo)
  - Márgenes operativos: Y% (asombroso - refleja poder de fijación de precios casi monopolístico)
- **Flujo de Caja Libre (FCF)**: Masivo pero en contexto de CapEx creciente
- Depresión temporal de FCF por inversión en capacidad (necesaria pero depresiva a corto plazo)

#### 7.2. Riesgos Financieros Clave
- **Riesgo de Concentración**: Un producto/segmento representa X% de ingresos y Y% de beneficios
- **Riesgo Geográfico**: Beneficios concentrados en [región/mercado], dependencia de decisiones de [gobierno/intermediarios]
- **Riesgo de Márgenes**: Vulnerabilidad a compresión por regulación/competencia

#### 7.3. Previsiones de los Analistas (Consensus)
**OBLIGATORIO: Crear Tabla 4: Resumen de Previsiones de Analistas y Múltiples Comparativos**

| Métrica | [Empresa] | [Competidor] | Promedio Sector | Interpretación |
|---------|-----------|--------------|-----------------|----------------|
| P/E (NTM) | Xx | Yx | Zx | ... |
| EV/Ventas (NTM) | ... | ... | ... | ... |
| Crec. Ingresos (CAGR 3-5a) | ... | ... | ... | ... |
| Crec. BPA (CAGR 3-5a) | ... | ... | ... | ... |
| Recomendación Consenso | ... | ... | ... | ... |
| Precio Objetivo vs Actual | ... | ... | ... | ... |

- **Crecimiento Esperado**: Se espera moderación desde X%+ actual a Y% sostenible
- **Crecimiento de BPA**: Esperado ligeramente más rápido que ingresos (asumiendo mejora de márgenes - suposición en duda por regulación)
- **Precio Objetivo Consensus**: Persigue al precio al alza, implica rendimiento modesto del Z%
- **Recomendaciones**: Mayoría "Comprar/Mantener", pocos "Vender" (dificultad de apostar contra historia poderosa)

#### 7.4. El Problema de la Valoración
- P/E a futuro (NTM) de [Empresa]: Xx
- Sector tradicional: promedio de Yx
- **Por qué existe esta prima masiva**: El mercado NO valora a [Empresa] como [sector tradicional]. Las empresas tradicionales cotizan a múltiplos bajos porque [razón].
- El mercado valora a [Empresa] como [empresa de plataforma/tech/hiper-crecimiento], más parecida a [ejemplo: Apple/NVIDIA]
- **La valoración actual ASUME**:
  1. El crecimiento del mercado es secular e imparable durante la próxima década
  2. [Empresa] mantendrá una cuota de mercado de [X-Y%]
  3. Los márgenes líderes en la industria se mantendrán altos y estables
- Para justificar la valoración actual, [Empresa] debe cumplir estas expectativas A LA PERFECCIÓN
- **Riesgo de compresión de múltiplos**: Cualquier fallo puede no afectar mucho el crecimiento real, pero puede causar compresión de múltiplos severa y dolorosa, ya que los inversores revalúan supuestos de crecimiento a largo plazo

### Parte VIII: Conclusión y Síntesis de Riesgos - Veredicto Final

#### 8.1. Regreso al Principio
- Habiendo abordado [ciencia/tecnología], modelo de crecimiento, [pipeline/competencia], regulación, la tesis puede reevaluarse con claridad de experto
- [Empresa] es, sin duda, una compañía de crecimiento de calidad excepcional
- Sin embargo, cotiza a una valoración que no solo descuenta este éxito, sino que **EXIGE perfección continua** frente a vientos en contra significativos y crecientes

#### 8.2. Panel de Control de Riesgos del Inversor
**OBLIGATORIO: Crear Tabla 5: Panel de Control de Riesgos Específico**

| Riesgo | Nivel | Descripción | Qué Vigilar |
|--------|-------|-------------|-------------|
| Riesgo Competitivo | ALTO/MEDIO/BAJO | [Amenaza específica] | [Métrica/hito específico] |
| Riesgo Regulatorio/Precios | ALTO/MEDIO/BAJO | [Recortes son certeza/cuando] | [Evento regulatorio específico] |
| Riesgo de Ejecución | ALTO/MEDIO/BAJO | [Debe ejecutar plan de X] | [Métrica operativa específica] |
| Riesgo de Concentración | ALTO/MEDIO/BAJO | [Compañía = Producto/Segmento] | [Amenaza específica] |
| Riesgo de Valoración | ALTO/MEDIO/BAJO | [Precio descuenta X años de crecimiento perfecto] | [Vulnerable a compresión ante decepción] |

#### 8.3. Perspectiva Final
- Después de este análisis, el círculo de competencia del inversor se ha expandido drásticamente
- La decisión de invertir **NO** se basa en [titular simple]. Es una apuesta sofisticada sobre:
  1. La ejecución trimestral de [factor operativo crítico]
  2. El resultado del [duelo/competencia específico] entre [empresa] y [competidor]
  3. La compleja interacción entre [factores regulatorios/operativos]
- **La oportunidad de crecimiento sigue siendo inmensa, pero los riesgos son igualmente sustanciales, y la prima pagada por esta oportunidad en la valoración actual es [exorbitante/razonable/injustificada]**

## Estilo de Redacción

IMPORTANTE:
- Escribe en un tono narrativo, directo y profesional (como un inversor institucional explicando a otro)
- Usa emojis estratégicamente (✅, 📈, ⚠️, 💰, 🔴, etc.) pero con moderación y solo para énfasis
- **Incluye números específicos SIEMPRE** cuando estén disponibles (montos en $, porcentajes, múltiplos)
- Sé específico sobre estrategia y ejecución
- Compara con períodos anteriores ("hace dos años vs ahora")
- Menciona decisiones del management/CEO cuando sea relevante
- **Estructura con encabezados claros (##, ###) y usa "Parte I", "Parte II", etc.**
- Usa listas numeradas (1️⃣, 2️⃣, 3️⃣) para puntos clave
- **CREA TABLAS en Markdown** cuando sea apropiado (Tabla 1, Tabla 2, etc.)
- **FORMATO DE TABLAS CRÍTICO**: 
  * Formato: | Col1 | Col2 | Col3 |
  * Fila separadora OBLIGATORIA: |:---:|:---:|:---:|
  * Todas las filas DEBEN tener el MISMO número de pipes (|)
  * Cada fila DEBE empezar y terminar con pipe (|)
  * EJEMPLO: | Año | Ingresos | Crecimiento |\n|:---:|:--------:|:-----------:|\n| 2024 | 157.980,1 | - |
- Si faltan datos, estima de manera conservadora y transparente
- **Sé objetivo**: Si la empresa tiene problemas, dilo claramente
- **Usa terminología técnica apropiada** cuando sea relevante (GLP-1, CVOT, PoS, etc.) pero explica brevemente

## Ejemplo de Estilo Profesional

"No es simplemente una compañía [sector]; se ha posicionado como la vanguardia de una revolución secular en [área]. Su éxito no radica únicamente en [producto], sino en haber desbloqueado con éxito el mercado de [mercado masivo], una de las mayores necesidades [no cubiertas] del mundo.

La inversión ya no es una simple apuesta por el crecimiento evidente del mercado. Esa oportunidad ya ha sido reconocida y cotizada. Una inversión hoy es una apuesta mucho más sofisticada y matizada. Es una apuesta por la capacidad de [Empresa] para mantener su supremacía en tres frentes críticos..."`;

  // Obtener noticias actuales de la empresa
  const news = input.financialData?.news || [];
  const newsText = news.length > 0 
    ? `\n\nNOTICIAS ACTUALES SOBRE LA EMPRESA (Últimos 30 días):\n${news.map((article: any, idx: number) => 
        `${idx + 1}. [${new Date(article.datetime * 1000).toLocaleDateString('es-ES')}] ${article.headline}\n   ${article.summary || ''}\n   Fuente: ${article.source}\n`
      ).join('\n')}`
    : '\n\nNOTICIAS: No se encontraron noticias recientes disponibles.';

  // Obtener eventos importantes de la empresa
  const events = input.financialData?.events || [];
  const eventsText = events.length > 0
    ? `\n\n📅 EVENTOS IMPORTANTES PRÓXIMOS DE LA EMPRESA:\n${events.map((event: any, idx: number) => {
        const eventDate = new Date(event.date);
        const daysUntil = Math.ceil((eventDate.getTime() - Date.now()) / (1000 * 60 * 60 * 24));
        const importanceEmoji = event.importance === 'high' ? '🔴' : event.importance === 'medium' ? '🟡' : '🟢';
        const urgencyText = daysUntil <= 30 ? `⚠️ PRÓXIMO - ` : '';
        return `${importanceEmoji} ${urgencyText}${eventDate.toLocaleDateString('es-ES', { year: 'numeric', month: 'long', day: 'numeric' })} (${daysUntil > 0 ? `En ${daysUntil} días` : daysUntil === 0 ? 'HOY' : `${Math.abs(daysUntil)} días atrás`})\n   📊 ${event.event}\n   ${event.description || ''}\n`;
      }).join('\n')}\n\n⚠️ IMPORTANTE: Los eventos con 🔴 pueden causar volatilidad significativa en el precio de la acción.`
    : '\n\n📅 EVENTOS: No se encontraron eventos próximos programados.';

  // Obtener recomendaciones de analistas
  const analystData = input.financialData?.analystRecommendations;
  const analystText = analystData
    ? `\n\n📊 RECOMENDACIONES DE ANALISTAS (Consenso de Wall Street):\n${analystData.strongBuy ? `✅ Strong Buy: ${analystData.strongBuy} analistas | ` : ''}${analystData.buy ? `🟢 Buy: ${analystData.buy} analistas | ` : ''}${analystData.hold ? `🟡 Hold: ${analystData.hold} analistas | ` : ''}${analystData.sell ? `🟠 Sell: ${analystData.sell} analistas | ` : ''}${analystData.strongSell ? `🔴 Strong Sell: ${analystData.strongSell} analistas` : ''}${analystData.targetHigh || analystData.targetMean || analystData.targetLow ? `\n💰 Target Price - High: $${analystData.targetHigh || 'N/A'} | Media: $${analystData.targetMean || 'N/A'} | Low: $${analystData.targetLow || 'N/A'}\n   Precio actual: $${input.currentPrice.toFixed(2)} vs Target Media: ${analystData.targetMean ? `$${analystData.targetMean} (${((analystData.targetMean / input.currentPrice - 1) * 100).toFixed(1)}% ${analystData.targetMean > input.currentPrice ? 'potencial al alza' : 'por debajo del target'})` : 'N/A'}` : ''}`
    : '';

  // Obtener análisis técnico
  const technicalData = input.financialData?.technicalAnalysis;
  const technicalText = technicalData
    ? `\n\n📈 ANÁLISIS TÉCNICO:\nSoporte: $${technicalData.support?.toFixed(2) || 'N/A'} | Resistencia: $${technicalData.resistance?.toFixed(2) || 'N/A'}\nTendencia: ${technicalData.trend === 'up' ? '📈 Al alza' : technicalData.trend === 'down' ? '📉 A la baja' : '➡️ Lateral'}\nVolumen Promedio (últimos 20 días): ${technicalData.avgVolume ? (technicalData.avgVolume / 1000000).toFixed(2) + 'M' : 'N/A'} | Tendencia de volumen: ${technicalData.volumeTrend === 'increasing' ? '📈 Aumentando' : technicalData.volumeTrend === 'decreasing' ? '📉 Disminuyendo' : '➡️ Estable'}`
    : '';

  // Obtener comparación con índices
  const indexData = input.financialData?.indexComparison;
  const indexText = indexData?.vsSP500
    ? `\n\n📊 RENDIMIENTO vs S&P 500 (últimos 12 meses):\n${indexData.vsSP500.change > 0 ? '✅' : '❌'} ${input.companyName}: ${indexData.vsSP500.change > 0 ? '+' : ''}${indexData.vsSP500.change.toFixed(2)}% ${indexData.vsSP500.change > 0 ? 'superando' : 'por debajo de'} el ${indexData.vsSP500.symbol}`
    : '';

  // Obtener insider trading
  const insiderData = input.financialData?.insiderTrading;
  const insiderText = insiderData && Array.isArray(insiderData.data) && insiderData.data.length > 0
    ? `\n\n👔 INSIDER TRADING (Actividad de Directivos):\n${insiderData.data.slice(0, 10).map((trans: any, idx: number) => {
        const date = trans.transactionDate ? new Date(trans.transactionDate * 1000).toLocaleDateString('es-ES') : 'N/A';
        const type = trans.transactionCode === 'P' ? '✅ Compra' : trans.transactionCode === 'S' ? '❌ Venta' : trans.transactionCode || 'N/A';
        const shares = trans.shares ? trans.shares.toLocaleString() : 'N/A';
        return `${idx + 1}. [${date}] ${trans.name || 'N/A'}: ${type} de ${shares} acciones a $${trans.price?.toFixed(2) || 'N/A'}`;
      }).join('\n')}\n\n⚠️ IMPORTANTE: Compras de directivos suelen ser señal positiva, ventas masivas pueden indicar preocupación.`
    : '';

  // Obtener datos ESG
  const esgData = input.financialData?.esgData;
  const esgText = esgData
    ? `\n\n🌱 ANÁLISIS ESG (Sostenibilidad):\n${esgData.totalESG ? `Score Total: ${esgData.totalESG}/100` : ''}${esgData.environmentScore ? ` | Medio Ambiente: ${esgData.environmentScore}/100` : ''}${esgData.socialScore ? ` | Social: ${esgData.socialScore}/100` : ''}${esgData.governanceScore ? ` | Gobernanza: ${esgData.governanceScore}/100` : ''}`
    : '';

  // Análisis de competencia (usando peers si están disponibles)
  const peers = input.financialData?.peers || [];
  const peersText = peers.length > 0
    ? `\n\n🏢 COMPETIDORES DEL SECTOR:\n${peers.join(', ')}`
    : '';

  const prompt = `Genera una TESIS DE INVERSIÓN completa para ${input.companyName} (${input.symbol}).

PRECIO ACTUAL: $${input.currentPrice.toFixed(2)}

DATOS FINANCIEROS DISPONIBLES:
${JSON.stringify(input.financialData, null, 2)}
${newsText}
${eventsText}
${analystText}
${technicalText}
${indexText}
${insiderText}
${esgText}
${peersText}

IMPORTANTE:
- Analiza en profundidad las noticias recientes para entender el contexto actual de la empresa
- PRESTA ESPECIAL ATENCIÓN a los eventos próximos (earnings próximos, anuncios, etc.) y menciona cómo pueden afectar el precio
- Los eventos marcados con 🔴 (high importance) pueden causar movimientos significativos del precio - evalúa su impacto potencial
- Compara tu recomendación con el consenso de analistas de Wall Street (strong buy, buy, hold, etc.) si está disponible
- Menciona si tu precio objetivo está alineado o difiere del target price de los analistas y por qué
- **ANÁLISIS TÉCNICO**: Incluye análisis de soporte/resistencia, tendencia de precio y cómo afecta la evaluación
- **COMPARACIÓN CON ÍNDICES**: Menciona si la acción está superando o bajoperformeando al S&P 500 y qué significa
- **INSIDER TRADING**: Analiza en profundidad las transacciones de directivos - compras significativas son señal muy positiva, ventas masivas pueden ser señal de alerta
- **ANÁLISIS DE VOLUMEN**: Considera la liquidez y tendencia de volumen - volumen creciente confirma tendencias alcistas
- **COMPETENCIA**: Si hay datos de competidores, compara métricas clave (PER, ROE, márgenes, crecimiento) con pares del sector. Menciona fortalezas y debilidades relativas
- **ESG**: Si hay datos ESG, evalúa cómo puede afectar la valoración a largo plazo y el riesgo reputacional
- Menciona eventos específicos recientes y próximos (earnings, cambios de management, acuerdos estratégicos, lanzamientos de productos, etc.)
- Usa las noticias y eventos para evaluar la ejecución del CEO y la estrategia de la empresa
- Considera el sentimiento del mercado basado en las noticias recientes y eventos próximos
- Si hay un earnings próximo, menciona las expectativas y cómo podrían afectar la recomendación
- Incorpora información de resultados trimestrales recientes si están disponibles en las noticias
- Sé específico sobre el precio objetivo estimado considerando el contexto actual de las noticias y eventos próximos
- Incluye análisis de PER y otras métricas de valoración comparándolas con competidores
- Si faltan datos históricos completos, estima valores conservadores basándote en las métricas disponibles y las noticias
- Sé transparente sobre limitaciones de datos
- Genera una recomendación clara y fundamentada basada en la información más actualizada
- Menciona específicamente si conviene esperar a eventos próximos antes de invertir o si es mejor actuar ahora`;

  const payload = {
    contents: [
      {
        role: 'user',
        parts: [
          {
            text: `${system}\n\n${prompt}`,
          },
        ],
      },
    ],
  };

  try {
    // Usar modelo Pro para análisis complejos (Gemini 2.5)
    const model = process.env.GEMINI_MODEL_THESIS || 'gemini-2.5-flash';
    const endpoint = `https://generativelanguage.googleapis.com/v1/models/${model}:generateContent?key=${apiKey}`;
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      cache: 'no-store',
    });
    const json = await res.json().catch(() => ({} as any));

    if (!res.ok) {
      const apiError = json?.error?.message || JSON.stringify(json);
      console.error('Gemini API error', res.status, apiError);
      return `IA desactivada temporalmente: (${res.status}) ${apiError}`;
    }
    const text: string | undefined = json?.candidates?.[0]?.content?.parts?.[0]?.text;
    return text || 'No se pudo generar la tesis de inversión en este momento.';
  } catch (e) {
    console.error('Gemini error', e);
    return 'Error al generar la tesis de inversión con IA.';
  }
}