'use server';

import { getAuth } from '@/lib/better-auth/auth';
import { headers } from 'next/headers';

// ============================================================================
// RAG CONTEXT RETRIEVAL - Knowledge Base Integration
// ============================================================================

/**
 * Retrieves relevant context from the knowledge base for stock analysis
 * This adds your personal investment criteria, past analyses, and references
 */
export async function getRAGContext(symbol: string, companyName: string): Promise<string> {
  try {
    const KB_API_URL = 'http://127.0.0.1:8000';

    const res = await fetch(`${KB_API_URL}/knowledge/context`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol, company_name: companyName }),
      cache: 'no-store',
    });

    if (!res.ok) {
      console.warn('RAG context fetch failed:', res.status);
      return '';
    }

    const data = await res.json();

    if (data.success && data.context) {
      return `\n\n📚 MI BASE DE CONOCIMIENTO (Análisis Previos y Criterios Personales):\n${data.context}\n`;
    }

    return '';
  } catch (error) {
    console.warn('RAG context unavailable:', error);
    return '';
  }
}

// ============================================
// Analista de Estrategia de Cartera (AI Strategy Analyst)
// ============================================

export async function generatePortfolioStrategyAnalysis(portfolioSummary: any): Promise<{
  alignmentScore: number;
  warnings: string[];
  opportunities: string[];
  strengths: string[];
  summary: string;
}> {
  try {
    const auth = await getAuth();
    if (!auth) throw new Error('Error de autenticación');
    const session = await auth.api.getSession({ headers: await headers() });
    if (!session?.user) throw new Error('Usuario no autenticado');

    const apiKey = process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY;
    if (!apiKey) {
      return {
        alignmentScore: 0,
        warnings: ['API Key no configurada'],
        opportunities: [],
        strengths: [],
        summary: 'Error de configuración de IA'
      };
    }

    // 1. Obtener contexto de estrategia personal
    const strategyContext = await getRAGContext('ESTRATEGIA', 'Reglas de Inversión y Gestión de Riesgo');

    // 2. Preparar datos de la cartera para el prompt
    const portfolioData = {
      totalValue: portfolioSummary.totalValue,
      totalGainPercent: portfolioSummary.totalGainPercent,
      holdingsCount: portfolioSummary.holdings.length,
      topHoldings: portfolioSummary.holdings.slice(0, 5).map((h: any) => ({
        symbol: h.symbol,
        weight: ((h.value / portfolioSummary.totalValue) * 100).toFixed(1) + '%',
        gain: h.gainPercent.toFixed(1) + '%'
      })),
      sectorAllocation: "Calculado por IA basado en holdings" // Gemini puede inferir esto o podríamos calcularlo si tuviéramos datos
    };

    const prompt = `Eres el Analista de Estrategia Personal del usuario. Tu trabajo es AUDITAR su cartera actual contra sus PROPIAS reglas de inversión definidas en su base de conocimiento.

CONTEXTO DE ESTRATEGIA (RAG - Reglas del Usuario):
${strategyContext || "No se encontraron documentos de estrategia específicos. Usa principios generales de Value Investing y Gestión de Riesgo prudente."}

CARTERA ACTUAL:
${JSON.stringify(portfolioData, null, 2)}

TAREA:
Analiza si la cartera cumple con la estrategia del usuario.
1. Calcula un "Score de Alineación" (0-100). 100 = Cumple todas las reglas perfectamente.
2. Identifica "Warnings": Violaciones de reglas (ej: mucha concentración, sector prohibido, falta de liquidez si se menciona).
3. Identifica "Strengths": Puntos fuertes donde se respeta la estrategia.
4. Identifica "Opportunities": Sugerencias basadas en sus reglas (ej: "Tu estrategia dice rebalancear si X sube mucho").

RESPONDE EN JSON EXACTO:
{
  "alignmentScore": number,
  "warnings": ["warning1", "warning2"],
  "opportunities": ["opp1", "opp2"],
  "strengths": ["str1", "str2"],
  "summary": "Breve resumen ejecutivo de 2 líneas"
}`;

    const payload = {
      contents: [{
        role: 'user',
        parts: [{ text: prompt }]
      }]
    };

    const model = 'gemini-2.0-flash'; // Usar modelo rápido y capaz
    const endpoint = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;

    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      cache: 'no-store'
    });

    if (!res.ok) throw new Error(`Gemini API error: ${res.status}`);

    const json = await res.json();
    const text = json?.candidates?.[0]?.content?.parts?.[0]?.text;

    if (!text) throw new Error('Empty response from AI');

    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) throw new Error('Invalid JSON format');

    return JSON.parse(jsonMatch[0]);

  } catch (error) {
    console.error('Error generating strategy analysis:', error);
    return {
      alignmentScore: 50,
      warnings: ['Error al analizar la estrategia'],
      opportunities: [],
      strengths: [],
      summary: 'No se pudo completar el análisis de estrategia en este momento.'
    };
  }
}


export async function generatePortfolioSummary(input: {
  portfolio: PortfolioPerformance;
  history: { t: number[]; v: number[] };
}): Promise<string> {
  const auth = await getAuth();
  if (!auth) throw new Error('Error de autenticación: no se pudo inicializar el sistema de autenticación');
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session?.user) throw new Error('Usuario no autenticado');

  const apiKey = process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY;
  if (!apiKey) {
    return 'IA desactivada: falta la clave de Gemini en el entorno.';
  }

  // 🧠 RAG: Obtener contexto para las acciones de la cartera
  const portfolioSymbols = input.portfolio.positions?.map(p => p.symbol) || [];
  let ragContext = '';
  if (portfolioSymbols.length > 0) {
    // Buscar contexto para los primeros 5 símbolos más grandes
    const topSymbols = portfolioSymbols.slice(0, 5);
    const contextPromises = topSymbols.map(s => getRAGContext(s, s));
    const contexts = await Promise.all(contextPromises);
    ragContext = contexts.filter(c => c).join('\n');
  }

  const system = `Eres un analista financiero experto. Resume claramente en español: distribución, rendimiento reciente, riesgos y 2 recomendaciones accionables.
${ragContext ? '\n\nUSA ESTE CONOCIMIENTO PERSONAL DEL USUARIO PARA PERSONALIZAR TU ANÁLISIS:' + ragContext : ''}`;

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
    // Forzar uso de gemini-3-flash-preview (eliminar variables de entorno obsoletas)
    const model = 'gemini-3-flash-preview';
    // Usar endpoint v1 (v1beta puede no soportar el modelo)
    const endpoint = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;
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
  if (!auth) throw new Error('Error de autenticación: no se pudo inicializar el sistema de autenticación');
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session?.user) throw new Error('Usuario no autenticado');

  const apiKey = process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY;
  if (!apiKey) {
    return 'IA desactivada: falta la clave de Gemini en el entorno.';
  }

  // Prompt enfocado en análisis narrativo profundo sin tablas ni gráficos - 100% IMPARCIAL
  const system = String.raw`Eres un analista financiero profesional e IMPARCIAL. Genera un ANÁLISIS COMPLETO DE INVERSIÓN en español, estilo tesis narrativa profesional para Substack: ameno, fluido y envolvente, como si estuvieras explicando la historia de inversión a otro inversor experto.

## PRINCIPIOS FUNDAMENTALES
- Analiza datos de forma 100% objetiva - deja que los datos hablen por sí mismos
- Presenta argumentos alcistas y bajistas equilibradamente
- NO fuerces conclusiones - derívelas naturalmente de los datos
- Si los datos muestran sobrevaloración o infravaloración, dilo claramente con evidencia

## ESTILO NARRATIVO (CRÍTICO)
- **FORMATO**: Prosa fluida y cautivadora, NO listas mecánicas de puntos
- **TABLAS**: Usa SOLO 1-2 tablas comparativas clave (competidores, escenarios), el resto en narrativa
- **FÓRMULAS**: NO muestres fórmulas matemáticas (VT = FCFF × (1+g) / (WACC-g)) - calcula internamente y presenta resultados en texto natural
- **NÚMEROS**: Incluye números específicos ($, %) pero integrados en la narrativa, no aislados
- **TONO**: Como artículo de Stratechery, Not Boring, o Acquired - profundo pero ameno
- **PÁRRAFOS**: Bien desarrollados (4-6 líneas), conectados entre sí, que cuenten una historia

## ESTRUCTURA DEL ANÁLISIS

### Parte I: El Planteamiento (Resumen Ejecutivo)
Comienza con un hook cautivador - ¿Por qué esta empresa merece atención AHORA?

**1. La Historia en Tres Actos**:
- Precio Actual vs Valor Calculado: Narra la desconexión (o no) en párrafo fluido
- Margen de Seguridad: Explica qué significa en términos prácticos, no solo el número
- VEREDICTO: Justifica con narrativa convincente basada en datos

**2. La Tesis de Inversión**:
- Caso Alcista: Párrafo cohesivo con 4-5 razones entrelazadas
- Caso Bajista: Párrafo sobre riesgos reales, no teoréticos
- La Desconexión: ¿Por qué el mercado valora así? Explica la narrativa vs realidad

### Parte II: El Negocio por Dentro
**NO uses viñetas mecánicas - escribe párrafos narrativos que expliquen:**
- El motor central del valor (tecnología/modelo/producto)
- Cómo ganan dinero realmente
- Qué los hace diferentes (moat explicado narrativamente)
- Productos clave vs competencia (máximo 1 tabla comparativa pequeña si realmente aporta)

### Parte III: Los Motores de Crecimiento
Narra la historia de crecimiento:
- 2-3 motores principales explicados con profundidad
- TAM y oportunidad (integrado en narrativa, no bullet points)
- Qué limita el crecimiento y cómo lo están resolviendo

### Parte IV: La Valoración - Historias que Cuentan los Números
**CRÍTICO: NO muestres tablas de proyecciones año por año. En su lugar:**

Explica narrativamente tu valoración DCF:
- "Proyectando los ingresos desde los actuales $X hasta $Y en 2034 (CAGR del Z%), basándome en [justificación]..."
- "Los márgenes EBIT deberían evolucionar de X% actual hacia Y% en 10 años debido a [factores]..."
- "Esto genera un flujo de caja libre promedio de $X millones anuales..."
- "Usando un WACC del X% (basado en tasa libre de riesgo del Y%, beta de Z, y prima de riesgo del W%)..."
- "El valor terminal, asumiendo crecimiento perpetuo conservador del X%, suma aproximadamente $Y millones en valor presente..."
- "Sumando todo: valor empresarial de $X, menos deuda neta de $Y, dividido entre Z millones de acciones..."
- "**Resultado: valor intrínseco de $X por acción**"

### Parte V: Los Escenarios Posibles
**Usa SOLO 1 tabla pequeña de escenarios (Bajista/Base/Alcista):**

| Escenario | Valor Intrínseco | CAGR | Margen Terminal | Supuestos Clave |
|-----------|------------------|------|-----------------|-----------------|
| Bajista | $X | Y% | Z% | Breve descripción |
| Base | $X | Y% | Z% | Breve descripción |
| Alcista | $X | Y% | Z% | Breve descripción |

Luego NARRA:
- **DCF Inverso**: "El precio actual de $X implica que el mercado espera [narrativa sobre expectativas implícitas]..."
- Qué tiene que pasar para cada escenario
- Probabilidades subjetivas y por qué

### Parte VI: El Campo de Batalla Competitivo
**Máximo 1 tabla comparativa con competidores:**

| Métrica | Empresa | Competidor 1 | Competidor 2 |
|---------|---------|--------------|--------------|
| P/E | X | Y | Z |
| Margen | X% | Y% | Z% |
| ROE | X% | Y% | Z% |

Luego NARRA el análisis competitivo:
- Ventajas y desventajas vs competencia
- Pipeline e innovación (sin tablas)
- Quién está ganando y por qué

### Parte VII: La Fortaleza del Moat
Evalúa narrativamente en 3 dimensiones (sin gráficos radar):
- **Fortaleza del Moat**: ¿Qué tan defendible es? (X/10 porque...)
- **Vulnerabilidad**: ¿Qué amenazas reales existen? (Y/10 porque...)
- **Sentimiento**: ¿Está odiada o amada por el mercado? (Z/10 porque...)

### Parte VIII: La Salud Financiera
Narra en párrafos:
- Crecimiento histórico y tendencias
- Márgenes y su evolución
- Generación de caja y solidez del balance
- Riesgos específicos identificados

### Parte IX: El Veredicto Final
**Cierra con fuerza narrativa:**

**Margen de Seguridad**: 
Explica en un párrafo potente qué significa el margen calculado (X%)

**Escenarios 3-5 años**:
Narra los posibles desenlaces con probabilidades (sin tabla)

**Recomendación Final**:
- Calificación: COMPRAR / MANTENER / NO COMPRAR
- Horizonte temporal y ROI esperado
- La razón de peso en un párrafo memorable
- Disclaimer estándar

## RECORDATORIOS CRÍTICOS
✅ HAZ: Narrativa fluida, párrafos bien desarrollados, historia convincente
✅ HAZ: Integra números en el texto natural
✅ HAZ: Usa emojis estratégicos (✅, 📈, ⚠️, 💰) con moderación
✅ HAZ: Máximo 2-3 tablas pequeñas en TODO el análisis

❌ NO HAGAS: Listas mecánicas de bullets sin conexión
❌ NO HAGAS: Tablas año por año de proyecciones DCF
❌ NO HAGAS: Fórmulas matemáticas explícitas (VT = FCFF × ...)
❌ NO HAGAS: Secciones con "Tabla 1:", "Tabla 2:", etc. por todas partes

**LONGITUD**: 2000-3500 palabras idealmente - profundo pero conciso y ameno`;

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

  // 🧠 RAG: Obtener contexto de tu base de conocimiento personal
  const ragContext = await getRAGContext(input.symbol, input.companyName);

  const prompt = `Escribe un ANÁLISIS COMPLETO DE INVERSIÓN estilo Substack (narrativo, ameno, profesional) para ${input.companyName} (${input.symbol}).

PRECIO ACTUAL: $${input.currentPrice.toFixed(2)}

DATOS DISPONIBLES:
${JSON.stringify(input.financialData, null, 2)}
${newsText}
${eventsText}
${analystText}
${technicalText}
${indexText}
${insiderText}
${peersText}
${ragContext}

INSTRUCCIONES:
- Escribe en PROSA FLUIDA, como artículo de Substack profesional
- Estructura: Partes I-IX del sistema, pero TODO narrativo (párrafos bien desarrollados)
- MÁXIMO 2-3 tablas pequeñas en TODO el análisis (competidores, escenarios)
- NO muestres fórmulas (VT = FCFF × ...) - calcula internamente y presenta resultados en texto
- NO hagas tablas año por año de proyecciones - explica en narrativa
- Integra números ($, %, múltiplos) en texto natural, no aislados
- Analiza noticias, eventos 🔴, análisis técnico, insider trading, consenso de analistas
- Compara con competidores del sector de forma narrativa
- Español (excepto acrónimos: DCF, WACC, ROIC, EBIT, PER)
- 2000 palabras - profundo pero ameno y legible
- 100% objetivo, basado en datos reales, sin forzar conclusiones`;

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
    // Forzar uso de gemini-3-flash-preview (eliminar variables de entorno obsoletas)
    const model = 'gemini-3-flash-preview';
    const endpoint = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;
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
    if (!auth) throw new Error('Error de autenticación: no se pudo inicializar el sistema de autenticación');
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

  // 🧠 RAG: Obtener contexto de la base de conocimiento del usuario
  const ragContext = await getRAGContext(input.symbol, input.companyName);

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
${ragContext}

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
    // Forzar uso de gemini-3-flash-preview (eliminar variables de entorno obsoletas)
    const model = 'gemini-3-flash-preview';
    const endpoint = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;
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
  if (!auth) throw new Error('Error de autenticación: no se pudo inicializar el sistema de autenticación');
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session?.user) throw new Error('Usuario no autenticado');

  const apiKey = process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY;
  if (!apiKey) {
    return 'IA desactivada: falta la clave de Gemini en el entorno.';
  }

  const system = `Eres un analista financiero profesional e IMPARCIAL especializado en due diligence exhaustivo de nivel institucional. Tu objetivo es analizar objetivamente los datos reales disponibles sin sesgos ni preconcepciones. Genera una TESIS DE INVERSIÓN completa, profunda, exhaustiva y narrativa en español, siguiendo EXACTAMENTE esta estructura y estilo:

IMPORTANTE - IMPARCIALIDAD TOTAL:
- Analiza los datos de forma 100% objetiva e imparcial
- NO asumas conclusiones - deja que los datos reales hablen por sí mismos
- Usa TODOS los datos financieros reales disponibles
- Considera TODA la información de analistas proporcionada
- Presenta tanto argumentos alcistas como bajistas de forma equilibrada y basados en datos reales
- Si los datos muestran sobrevaloración, dilo claramente
- Si los datos muestran infravaloración, dilo basándote en los datos
- NO fuerces conclusiones - las conclusiones deben derivarse naturalmente de los datos

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

#### 7.4. Valoración DCF y Análisis de Múltiplos
**IMPORTANTE - FORMATO DE VALORACIÓN:**
- **NO muestres fórmulas paso a paso** como "VT = FCFF × (1 + g) / (WACC - g)" seguido de cálculos intermedios
- **NO muestres tablas extensas** con cada paso del cálculo de DCF
- **SÍ calcula internamente** todos los valores (FCFF, WACC, tasa de crecimiento perpetuo, valor terminal, etc.)
- **SÍ presenta los resultados finales** de forma narrativa en lenguaje natural
- **Ejemplo CORRECTO**: "Utilizando un modelo DCF con un WACC del 11,35% y una tasa de crecimiento perpetuo del 4%, el valor terminal proyectado para 2034 se estima en aproximadamente $3.162.785 millones. Descontando este valor al presente, obtenemos un valor terminal descontado de $1.073.439 millones, que representa aproximadamente el [X%] del valor total estimado de la empresa."
- **Ejemplo INCORRECTO**: NO hagas esto - NO muestres fórmulas paso a paso como "VT = FCFF_año_final × (1 + g) / (WACC - g)" seguido de FCFF_2034 = $223.523,73 M USD, g = 4,00%, WACC = 11,35%, y luego cálculos intermedios VT = $223.523,73 × (1 + 0,04) / (0,1135 - 0,04) = $3.162.784,88 M USD. Esto es lo que DEBES EVITAR.

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
- **NO muestres fórmulas paso a paso ni cálculos intermedios** - calcula internamente y presenta solo los resultados finales en lenguaje natural
- **NO uses tablas para mostrar cálculos de DCF paso a paso** - usa tablas solo para comparaciones (métricas entre empresas, previsiones, etc.)
- **SÍ presenta los valores calculados** (FCFF, WACC, valor terminal, precio objetivo) pero de forma narrativa, explicando qué significan
- Sé específico sobre estrategia y ejecución
- Compara con períodos anteriores ("hace dos años vs ahora")
- Menciona decisiones del management/CEO cuando sea relevante
- **Estructura con encabezados claros (##, ###) y usa "Parte I", "Parte II", etc.**
- Usa listas numeradas (1️⃣, 2️⃣, 3️⃣) para puntos clave
- **CREA TABLAS en Markdown** cuando sea apropiado (Tabla 1, Tabla 2, etc.) - pero solo para comparaciones y resúmenes, NO para cálculos paso a paso
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

  // 🧠 RAG: Obtener contexto de la base de conocimiento del usuario
  const ragContext = await getRAGContext(input.symbol, input.companyName);

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
${ragContext}

IMPORTANTE - IMPARCIALIDAD Y USO DE DATOS REALES:
- **100% IMPARCIAL**: Analiza objetivamente sin sesgos ni preconcepciones - deja que los datos hablen por sí mismos
- **USA TODOS LOS DATOS REALES DISPONIBLES**: Prioriza siempre datos reales sobre estimaciones
- **USA TODA LA INFORMACIÓN DE ANALISTAS**: Considera TODAS las recomendaciones y targets de analistas proporcionados
  - Compara tu análisis con el consenso de analistas de Wall Street (strong buy, buy, hold, sell, strong sell)
  - Presenta el consenso de analistas de forma clara y objetiva
  - Si tu recomendación difiere del consenso, explica por qué basándote en datos reales
  - Si los analistas tienen targets de precio diferentes, menciona la dispersión y qué significa
  - Presenta tanto las opiniones alcistas como bajistas de los analistas si están disponibles
- Analiza en profundidad las noticias recientes para entender el contexto actual de la empresa
- PRESTA ESPECIAL ATENCIÓN a los eventos próximos (earnings próximos, anuncios, etc.) y menciona cómo pueden afectar el precio
- Los eventos marcados con 🔴 (high importance) pueden causar movimientos significativos del precio - evalúa su impacto potencial objetivamente
- **ANÁLISIS TÉCNICO**: Incluye análisis de soporte/resistencia, tendencia de precio y cómo afecta la evaluación
- **COMPARACIÓN CON ÍNDICES**: Menciona si la acción está superando o bajoperformeando al S&P 500 y qué significa
- **INSIDER TRADING**: Analiza en profundidad las transacciones de directivos objetivamente - compras pueden ser positiva, ventas pueden ser señal de alerta, pero evalúa según contexto
- **ANÁLISIS DE VOLUMEN**: Considera la liquidez y tendencia de volumen objetivamente
- **COMPETENCIA**: Si hay datos de competidores, compara métricas clave (PER, ROE, márgenes, crecimiento) con pares del sector. Menciona fortalezas y debilidades relativas basadas en datos
- **ESG**: Si hay datos ESG, evalúa cómo puede afectar la valoración a largo plazo y el riesgo reputacional
- Menciona eventos específicos recientes y próximos (earnings, cambios de management, acuerdos estratégicos, lanzamientos de productos, etc.)
- Usa las noticias y eventos para evaluar objetivamente la ejecución del CEO y la estrategia de la empresa
- Considera el sentimiento del mercado basado en las noticias recientes y eventos próximos
- Si hay un earnings próximo, menciona las expectativas y cómo podrían afectar la recomendación
- Incorpora información de resultados trimestrales recientes si están disponibles en las noticias
- Sé específico sobre el precio objetivo estimado considerando el contexto actual de las noticias y eventos próximos, pero compáralo con los targets de analistas
- Incluye análisis de PER y otras métricas de valoración comparándolas con competidores
- Si faltan datos históricos completos, estima valores conservadores basándote en las métricas disponibles y las noticias, pero sé transparente sobre las limitaciones
- Sé transparente sobre limitaciones de datos
- Genera una recomendación clara y fundamentada basada SOLO en datos reales e información de analistas
- NO fuerces conclusiones - las recomendaciones deben derivarse naturalmente de los datos
- Menciona específicamente si conviene esperar a eventos próximos antes de invertir o si es mejor actuar ahora, basándote en los datos
- **FORMATO DE VALORACIÓN DCF CRÍTICO**: Si realizas valoración DCF, NO muestres fórmulas paso a paso (ej: "VT = FCFF × (1 + g) / (WACC - g)" seguido de cálculos intermedios). Calcula internamente todos los valores necesarios y presenta SOLO los resultados finales en lenguaje natural. Ejemplo: "Utilizando un modelo DCF con un WACC del 11,35% y una tasa de crecimiento perpetuo del 4%, el valor terminal proyectado se estima en aproximadamente $3.162.785 millones, resultando en un valor descontado de $1.073.439 millones."`;

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
    // Forzar uso de gemini-3-flash-preview (eliminar variables de entorno obsoletas)
    const model = 'gemini-3-flash-preview';
    const endpoint = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;
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

/**
 * Estima Health Score usando IA cuando faltan datos reales
 * Usa Gemini para analizar todos los datos disponibles y estimar cualquier categoría faltante
 */
export async function estimateHealthScoreWithAI(
  symbol: string,
  companyName: string,
  financialData: any,
  missingCategories: string[] // ej: ['growth', 'stability', 'profitability', 'efficiency', 'valuation']
): Promise<{
  profitability?: number;
  growth?: number;
  stability?: number;
  efficiency?: number;
  valuation?: number;
}> {
  const apiKey = process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY;
  if (!apiKey) {
    console.warn('No Gemini API key, returning empty estimates');
    return {};
  }

  try {
    // Extraer todos los datos disponibles
    const metrics = financialData.metrics?.metric || financialData.metrics || {};
    const profile = financialData.profile || {};
    const quote = financialData.quote || {};
    const news = financialData.news || [];

    // Preparar datos para la IA
    const availableData = {
      symbol,
      companyName,
      quote: {
        currentPrice: quote.c,
        previousClose: quote.pc,
        change: quote.d,
        changePercent: quote.dp,
      },
      profile: {
        sector: profile.finnhubIndustry || profile.sector,
        country: profile.country,
        exchange: profile.exchange,
        marketCap: profile.marketCapitalization,
      },
      metrics: {
        // Rentabilidad (si está disponible)
        netMargin: metrics.netProfitMarginTTM || metrics.netProfitMargin,
        roe: metrics.roeTTM || metrics.roe,
        roa: metrics.roaTTM || metrics.roa,
        // Eficiencia (si está disponible)
        operatingMargin: metrics.operatingMarginTTM || metrics.operatingMargin,
        assetTurnover: metrics.assetTurnoverTTM || metrics.assetTurnover,
        // Valuación (si está disponible)
        pe: metrics.peTTM || metrics.pe,
        pb: metrics.pbTTM || metrics.pb,
        ps: metrics.psTTM || metrics.ps,
        // Datos parciales de Growth y Stability si existen
        revenue: metrics.revenueTTM || metrics.revenue,
        revenueGrowth: metrics.revenueGrowthTTM || metrics.revenueGrowth,
        debtToEquity: metrics.debtToEquityTTM || metrics.debtToEquity,
        currentRatio: metrics.currentRatioTTM || metrics.currentRatio,
        quickRatio: metrics.quickRatioTTM || metrics.quickRatio,
      },
      recentNews: news.slice(0, 5).map((n: any) => ({
        headline: n.headline,
        summary: n.summary,
        datetime: n.datetime,
      })),
    };

    const systemPrompt = `Eres un analista financiero experto e IMPARCIAL. Analiza TODOS los datos financieros REALES disponibles de forma objetiva y estima las categorías faltantes del Health Score basándote SOLO en datos reales, sin sesgos ni preconcepciones.

CATEGORÍAS A ESTIMAR:
${missingCategories.map(c => `- ${c.charAt(0).toUpperCase() + c.slice(1)}`).join('\n')}

DEFINICIONES DE CATEGORÍAS:
- Profitability (Rentabilidad): Mide la capacidad de generar beneficios. Usa ROE, ROA, márgenes netos si están disponibles indirectamente.
- Growth (Crecimiento): Mide el crecimiento de ingresos y beneficios. Usa tendencias de precio, noticias, múltiplos de crecimiento.
- Stability (Estabilidad): Mide estabilidad financiera y solidez. Usa ratios de deuda, liquidez, volatilidad si están disponibles.
- Efficiency (Eficiencia): Mide eficiencia operativa y uso de activos. Usa márgenes operativos, rotación de activos si están disponibles.
- Valuation (Valuación): Mide si la acción está infravalorada o sobrevalorada. Usa PER, P/B, P/S, comparación con sector.

METODOLOGÍA IMPARCIAL:
1. **PRIORIZA SIEMPRE datos reales disponibles** - si hay datos parciales, úsalos como base objetiva
2. Analiza TODOS los datos reales disponibles (métricas financieras, perfil, noticias recientes, cotización) de forma objetiva
3. Usa datos indirectos y correlaciones de forma conservadora y objetiva:
   - Cambios de precio pueden indicar expectativas de mercado (evalúa objetivamente si son positivos o negativos)
   - Noticias recientes pueden indicar tendencias y eventos (analiza tanto noticias positivas como negativas)
   - Múltiplos pueden reflejar expectativas (evalúa si son razonables o excesivos)
   - Correlaciones entre métricas (ej: alta rentabilidad puede indicar estabilidad, pero NO asumas - evalúa según datos)
4. Estima valores conservadores basados SOLO en datos reales disponibles, sin forzar conclusiones
5. Si NO hay suficientes datos para estimar de forma confiable, usa valores neutrales (50/100) y sé transparente sobre la incertidumbre
6. **NO fuerces valores altos o bajos** - las estimaciones deben reflejar objetivamente los datos disponibles

RESPONDE EN FORMATO JSON EXACTO:
{
  ${missingCategories.map(c => `"${c}": número entre 0-100`).join(',\n  ')}
}

IMPORTANTE:
- Si una categoría NO está en missingCategories, NO la incluyas en la respuesta
- Los valores deben ser realistas basados en los datos disponibles
- Usa valores conservadores si hay incertidumbre
- Compara con promedios del sector si es posible
- PRIORIZA siempre datos reales cuando estén disponibles sobre estimaciones`;

    const dataText = `DATOS DISPONIBLES PARA ${symbol} (${companyName}):

PERFIL:
- Sector: ${availableData.profile.sector || 'N/A'}
- País: ${availableData.profile.country || 'N/A'}
- Exchange: ${availableData.profile.exchange || 'N/A'}
- Market Cap: ${availableData.profile.marketCap || 'N/A'}

COTIZACIÓN ACTUAL:
- Precio: $${availableData.quote.currentPrice || 'N/A'}
- Cambio: ${availableData.quote.changePercent?.toFixed(2) || 'N/A'}%
- Precio Anterior: $${availableData.quote.previousClose || 'N/A'}

MÉTRICAS FINANCIERAS DISPONIBLES:
- Margen Neto: ${availableData.metrics.netMargin || 'N/A'}
- ROE: ${availableData.metrics.roe || 'N/A'}
- ROA: ${availableData.metrics.roa || 'N/A'}
- Margen Operativo: ${availableData.metrics.operatingMargin || 'N/A'}
- Rotación de Activos: ${availableData.metrics.assetTurnover || 'N/A'}
- PER: ${availableData.metrics.pe || 'N/A'}
- P/B: ${availableData.metrics.pb || 'N/A'}
- P/S: ${availableData.metrics.ps || 'N/A'}
- Ingresos: ${availableData.metrics.revenue || 'N/A'}
- Crecimiento Ingresos: ${availableData.metrics.revenueGrowth || 'N/A'}
- Deuda/Capital: ${availableData.metrics.debtToEquity || 'N/A'}
- Ratio Corriente: ${availableData.metrics.currentRatio || 'N/A'}
- Quick Ratio: ${availableData.metrics.quickRatio || 'N/A'}

NOTICIAS RECIENTES (${availableData.recentNews.length}):
${availableData.recentNews.map((n: any, idx: number) =>
      `${idx + 1}. [${new Date(n.datetime * 1000).toLocaleDateString('es-ES')}] ${n.headline}\n   ${n.summary?.substring(0, 100) || ''}...`
    ).join('\n\n')}

CATEGORÍAS FALTANTES A ESTIMAR: ${missingCategories.join(', ')}`;

    // 🧠 RAG: Obtener contexto para la estimación (notas del usuario sobre la calidad del negocio)
    const ragContext = await getRAGContext(symbol, companyName);

    const prompt = `${systemPrompt}\n\n${dataText}\n\n${ragContext}\n\nEstima las categorías faltantes basándote en TODOS estos datos reales disponibles.`;

    const payload = {
      contents: [{
        role: 'user',
        parts: [{ text: prompt }],
      }],
    };

    const model = 'gemini-3-flash-preview';
    const endpoint = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      cache: 'no-store',
    });

    const json = await res.json().catch(() => ({} as any));

    if (!res.ok) {
      console.warn('Gemini Health Score estimation failed:', res.status);
      return {};
    }

    const text: string | undefined = json?.candidates?.[0]?.content?.parts?.[0]?.text;
    if (!text) {
      return {};
    }

    // Extraer JSON de la respuesta
    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) {
      console.warn('No JSON found in Gemini response');
      return {};
    }

    try {
      const estimates = JSON.parse(jsonMatch[0]);

      // Validar y ajustar valores para TODAS las categorías solicitadas
      const result: {
        profitability?: number;
        growth?: number;
        stability?: number;
        efficiency?: number;
        valuation?: number;
      } = {};

      if (missingCategories.includes('profitability') && typeof estimates.profitability === 'number') {
        result.profitability = Math.max(0, Math.min(100, Math.round(estimates.profitability)));
      }

      if (missingCategories.includes('growth') && typeof estimates.growth === 'number') {
        result.growth = Math.max(0, Math.min(100, Math.round(estimates.growth)));
      }

      if (missingCategories.includes('stability') && typeof estimates.stability === 'number') {
        result.stability = Math.max(0, Math.min(100, Math.round(estimates.stability)));
      }

      if (missingCategories.includes('efficiency') && typeof estimates.efficiency === 'number') {
        result.efficiency = Math.max(0, Math.min(100, Math.round(estimates.efficiency)));
      }

      if (missingCategories.includes('valuation') && typeof estimates.valuation === 'number') {
        result.valuation = Math.max(0, Math.min(100, Math.round(estimates.valuation)));
      }

      return result;
    } catch (e) {
      console.error('Error parsing Gemini Health Score response:', e);
      return {};
    }
  } catch (error) {
    console.error('Error estimating Health Score with AI:', error);
    return {};
  }
}

// Función para generar respuestas del checklist automáticamente con IA
export async function generateChecklistWithAI(input: {
  symbol: string;
  companyName: string;
  financialData?: any;
  currentPrice: number;
}): Promise<{
  answers: { questionId: string; answer: 'yes' | 'no' | 'maybe'; explanation: string }[];
  overallScore: number;
  recommendation: string;
  summary: string;
}> {
  // Verificar autenticación (permitir en desarrollo sin MongoDB)
  try {
    const auth = await getAuth();
    if (auth) {
      const session = await auth.api.getSession({ headers: await headers() });
      if (!session?.user && process.env.NODE_ENV !== 'development') {
        throw new Error('Usuario no autenticado');
      }
    }
  } catch (authError: any) {
    if (process.env.NODE_ENV === 'development') {
      console.warn('⚠️ Generando checklist sin autenticación (modo desarrollo)');
    } else {
      throw new Error('Usuario no autenticado');
    }
  }

  // Obtener datos financieros si no se proporcionan
  let financialData = input.financialData;
  if (!financialData) {
    try {
      const { getStockFinancialData } = await import('./finnhub.actions');
      financialData = await getStockFinancialData(input.symbol);
    } catch (error) {
      console.error('Error fetching financial data server-side:', error);
      // Continuar con lo que tengamos o fallar controladamente
    }
  }

  const apiKey = process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY;
  if (!apiKey) {
    return {
      answers: [],
      overallScore: 0,
      recommendation: 'No disponible - falta API key',
      summary: 'IA desactivada: falta la clave de Gemini.'
    };
  }

  const CHECKLIST_QUESTIONS = [
    { id: 'understand_business', question: '¿Entiendo cómo gana dinero esta empresa?', weight: 1 },
    { id: 'competitive_moat', question: '¿Tiene una ventaja competitiva duradera (moat)?', weight: 2 },
    { id: 'pricing_power', question: '¿Puede subir precios sin perder clientes?', weight: 1.5 },
    { id: 'recurring_revenue', question: '¿Tiene ingresos recurrentes o predecibles?', weight: 1.5 },
    { id: 'management_quality', question: '¿El equipo directivo es honesto y competente?', weight: 1.5 },
    { id: 'skin_in_game', question: '¿Los directivos tienen participación significativa?', weight: 1 },
    { id: 'debt_level', question: '¿El nivel de deuda es manejable (Debt/EBITDA < 3)?', weight: 1.5 },
    { id: 'free_cash_flow', question: '¿Genera Free Cash Flow positivo y consistente?', weight: 2 },
    { id: 'return_on_capital', question: '¿El ROIC/ROE es superior al 15% sostenido?', weight: 1.5 },
    { id: 'margin_of_safety', question: '¿El precio actual ofrece margen de seguridad (>25%)?', weight: 2 },
    { id: 'growth_potential', question: '¿Tiene potencial de crecimiento para los próximos 5 años?', weight: 1 },
    { id: 'industry_tailwinds', question: '¿El sector tiene vientos de cola favorables?', weight: 1 },
    { id: 'no_major_risks', question: '¿Están identificados y son manejables los principales riesgos?', weight: 1.5 },
    { id: 'capital_allocation', question: '¿La empresa asigna bien el capital (dividendos, recompras, M&A)?', weight: 1 },
    { id: 'would_hold_10_years', question: '¿Mantendría esta acción durante 10 años sin mirar el precio?', weight: 2 }
  ];

  const questionsText = CHECKLIST_QUESTIONS.map((q, i) => `${i + 1}. [${q.id}] ${q.question}`).join('\n');

  const system = `Eres un analista de inversión value investing experto. Analiza los datos financieros proporcionados y responde a las 15 preguntas del checklist de inversión de forma objetiva y basada en datos.

Para cada pregunta, responde con:
- "yes" si los datos apoyan claramente una respuesta positiva
- "no" si los datos indican claramente una respuesta negativa  
- "maybe" si hay evidencia mixta o insuficiente

IMPORTANTE: Sé objetivo y basado en datos reales. No fuerces respuestas positivas.

Responde SOLO con un JSON válido en este formato exacto:
{
  "answers": [
    {"questionId": "understand_business", "answer": "yes|no|maybe", "explanation": "Explicación breve de 1-2 líneas"},
    ...para cada una de las 15 preguntas
  ],
  "overallScore": número del 0-100,
  "recommendation": "COMPRA FUERTE|COMPRAR|MANTENER|EVITAR|EVITAR FUERTE",
  "summary": "Resumen ejecutivo de 2-3 frases sobre la calidad de la inversión"
}`;

  // 🧠 RAG: Obtener criterios personales del usuario
  const ragContext = await getRAGContext(input.symbol, input.companyName);

  const prompt = `Analiza ${input.companyName} (${input.symbol}) a $${input.currentPrice.toFixed(2)} y responde estas 15 preguntas:

${questionsText}

DATOS FINANCIEROS:
${JSON.stringify(financialData, null, 2)}
${ragContext}

Responde con JSON válido únicamente.`;

  const payload = {
    contents: [{ role: 'user', parts: [{ text: `${system}\n\n${prompt}` }] }],
  };

  try {
    const model = 'gemini-3-flash-preview';
    const endpoint = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      cache: 'no-store',
    });

    const json = await res.json().catch(() => ({} as any));

    if (!res.ok) {
      console.error('Gemini API error', res.status);
      return { answers: [], overallScore: 0, recommendation: 'Error', summary: 'Error al generar análisis' };
    }

    const text: string | undefined = json?.candidates?.[0]?.content?.parts?.[0]?.text;
    if (!text) {
      return { answers: [], overallScore: 0, recommendation: 'Error', summary: 'Sin respuesta' };
    }

    // Extraer JSON
    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) {
      return { answers: [], overallScore: 0, recommendation: 'Error', summary: 'Formato inválido' };
    }

    const result = JSON.parse(jsonMatch[0]);
    return {
      answers: result.answers || [],
      overallScore: result.overallScore || 0,
      recommendation: result.recommendation || 'N/A',
      summary: result.summary || ''
    };
  } catch (e) {
    console.error('Gemini checklist error', e);
    return { answers: [], overallScore: 0, recommendation: 'Error', summary: 'Error de conexión' };
  }
}

// Función para análisis de patrones técnicos con IA
export async function generatePatternAnalysis(input: {
  symbol: string;
  companyName: string;
  financialData?: any;
  currentPrice: number;
}): Promise<{
  patterns: {
    name: string;
    type: 'bullish' | 'bearish' | 'neutral';
    confidence: number;
    description: string;
    priceTarget?: number;
  }[];
  elliottWave: {
    currentWave: string;
    position: string;
    nextMove: string;
    confidence: number;
  };
  supportResistance: {
    supports: number[];
    resistances: number[];
    keyLevel: number;
    trend: 'bullish' | 'bearish' | 'sideways';
  };
  summary: string;
}> {
  // Verificar autenticación (permitir en desarrollo)
  try {
    const auth = await getAuth();
    if (auth) {
      const session = await auth.api.getSession({ headers: await headers() });
      if (!session?.user && process.env.NODE_ENV !== 'development') {
        throw new Error('Usuario no autenticado');
      }
    }
  } catch (authError: any) {
    if (process.env.NODE_ENV !== 'development') {
      throw new Error('Usuario no autenticado');
    }
  }

  const apiKey = process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY;
  if (!apiKey) {
    return {
      patterns: [],
      elliottWave: { currentWave: 'N/A', position: 'N/A', nextMove: 'N/A', confidence: 0 },
      supportResistance: { supports: [], resistances: [], keyLevel: 0, trend: 'sideways' },
      summary: 'IA desactivada: falta API key'
    };
  }

  const system = `Eres un analista técnico experto especializado en:
- Patrones chartistas (cabeza-hombros, triángulos, banderas, cuñas, doble techo/suelo, etc.)
- Ondas de Elliott
- Niveles de soporte y resistencia
- Fibonacci

Analiza los datos proporcionados y detecta patrones técnicos.

Responde SOLO con JSON válido en este formato:
{
  "patterns": [
    {
      "name": "Nombre del patrón (ej: Bandera Alcista, Cabeza y Hombros Invertido)",
      "type": "bullish|bearish|neutral",
      "confidence": número 0-100,
      "description": "Explicación breve del patrón y su implicación",
      "priceTarget": número objetivo de precio si aplica
    }
  ],
  "elliottWave": {
    "currentWave": "1|2|3|4|5|A|B|C o N/A si no hay patrón claro",
    "position": "Inicio|Mitad|Final de la onda",
    "nextMove": "Descripción del próximo movimiento esperado",
    "confidence": número 0-100
  },
  "supportResistance": {
    "supports": [array de niveles de soporte en orden descendente],
    "resistances": [array de niveles de resistencia en orden ascendente],
    "keyLevel": nivel más importante actual,
    "trend": "bullish|bearish|sideways"
  },
  "summary": "Resumen ejecutivo de 2-3 líneas del análisis técnico"
}`;

  const technicalData = input.financialData?.technicalAnalysis;
  const quote = input.financialData?.quote;

  // 🧠 RAG: Obtener contexto técnico preferido del usuario
  const ragContext = await getRAGContext(input.symbol, input.companyName);

  const prompt = `Analiza técnicamente ${input.companyName} (${input.symbol}) a $${input.currentPrice.toFixed(2)}

DATOS TÉCNICOS DISPONIBLES:
- Precio actual: $${input.currentPrice}
- Precio apertura: $${quote?.o || 'N/A'}
- Precio cierre anterior: $${quote?.pc || 'N/A'}
- Máximo 52 semanas: $${quote?.h52 || technicalData?.resistance || 'N/A'}
- Mínimo 52 semanas: $${quote?.l52 || technicalData?.support || 'N/A'}
- Soporte estimado: $${technicalData?.support || 'N/A'}
- Resistencia estimada: $${technicalData?.resistance || 'N/A'}
- Tendencia: ${technicalData?.trend || 'N/A'}
- Volumen promedio: ${technicalData?.avgVolume || 'N/A'}

MÉTRICAS FINANCIERAS:
${JSON.stringify(input.financialData?.metrics || {}, null, 2)}
${ragContext} 

Identifica:
1. Patrones chartistas visibles
2. Posible conteo de ondas de Elliott
3. Niveles clave de soporte y resistencia
4. Tendencia general

Responde con JSON válido únicamente.`;

  const payload = {
    contents: [{ role: 'user', parts: [{ text: `${system}\n\n${prompt}` }] }],
  };

  try {
    const model = 'gemini-3-flash-preview';
    const endpoint = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      cache: 'no-store',
    });

    const json = await res.json().catch(() => ({} as any));

    if (!res.ok) {
      console.error('Gemini Pattern API error', res.status);
      return {
        patterns: [],
        elliottWave: { currentWave: 'Error', position: '', nextMove: '', confidence: 0 },
        supportResistance: { supports: [], resistances: [], keyLevel: input.currentPrice, trend: 'sideways' },
        summary: 'Error al generar análisis de patrones'
      };
    }

    const text: string | undefined = json?.candidates?.[0]?.content?.parts?.[0]?.text;
    if (!text) {
      return {
        patterns: [],
        elliottWave: { currentWave: 'N/A', position: '', nextMove: '', confidence: 0 },
        supportResistance: { supports: [], resistances: [], keyLevel: input.currentPrice, trend: 'sideways' },
        summary: 'Sin respuesta del análisis'
      };
    }

    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) {
      return {
        patterns: [],
        elliottWave: { currentWave: 'N/A', position: '', nextMove: '', confidence: 0 },
        supportResistance: { supports: [], resistances: [], keyLevel: input.currentPrice, trend: 'sideways' },
        summary: 'Formato de respuesta inválido'
      };
    }

    const result = JSON.parse(jsonMatch[0]);
    return {
      patterns: result.patterns || [],
      elliottWave: result.elliottWave || { currentWave: 'N/A', position: '', nextMove: '', confidence: 0 },
      supportResistance: result.supportResistance || { supports: [], resistances: [], keyLevel: input.currentPrice, trend: 'sideways' },
      summary: result.summary || ''
    };
  } catch (e) {
    console.error('Gemini pattern analysis error', e);
    return {
      patterns: [],
      elliottWave: { currentWave: 'Error', position: '', nextMove: '', confidence: 0 },
      supportResistance: { supports: [], resistances: [], keyLevel: input.currentPrice, trend: 'sideways' },
      summary: 'Error de conexión'
    };
  }
}

// ============================================
// Alternativas IA - Comparar con competidores del sector
// ============================================

// Mapa de competidores por sector/industria
const SECTOR_COMPETITORS: Record<string, string[]> = {
  // Pagos
  'V': ['MA', 'PYPL', 'AXP', 'SQ', 'AFRM'],
  'MA': ['V', 'PYPL', 'AXP', 'SQ', 'AFRM'],
  'PYPL': ['V', 'MA', 'SQ', 'AFRM', 'COIN'],
  'SQ': ['PYPL', 'V', 'MA', 'AFRM', 'COIN'],
  // Tech Giants
  'AAPL': ['MSFT', 'GOOGL', 'AMZN', 'META'],
  'MSFT': ['AAPL', 'GOOGL', 'AMZN', 'ORCL', 'CRM'],
  'GOOGL': ['AAPL', 'MSFT', 'META', 'AMZN'],
  'AMZN': ['MSFT', 'GOOGL', 'AAPL', 'WMT', 'TGT'],
  'META': ['GOOGL', 'SNAP', 'PINS', 'TWTR'],
  // Semiconductores
  'NVDA': ['AMD', 'INTC', 'AVGO', 'QCOM', 'TSM'],
  'AMD': ['NVDA', 'INTC', 'AVGO', 'QCOM'],
  'INTC': ['NVDA', 'AMD', 'AVGO', 'TXN'],
  // Cloud/SaaS
  'CRM': ['ORCL', 'NOW', 'WDAY', 'SAP'],
  'NOW': ['CRM', 'ORCL', 'WDAY', 'SNOW'],
  // Retail
  'WMT': ['TGT', 'COST', 'AMZN', 'HD', 'LOW'],
  'TGT': ['WMT', 'COST', 'AMZN', 'HD'],
  'COST': ['WMT', 'TGT', 'BJ', 'KR'],
  'HD': ['LOW', 'WMT', 'TGT', 'MCD'],
  'LOW': ['HD', 'WMT', 'TGT'],
  // Banca
  'JPM': ['BAC', 'WFC', 'GS', 'MS', 'C'],
  'BAC': ['JPM', 'WFC', 'C', 'USB'],
  'GS': ['MS', 'JPM', 'C'],
  'MS': ['GS', 'JPM', 'SCHW'],
  // Healthcare
  'JNJ': ['PFE', 'MRK', 'ABBV', 'UNH'],
  'PFE': ['JNJ', 'MRK', 'ABBV', 'BMY'],
  'UNH': ['CVS', 'CI', 'ELV', 'HUM'],
  // Consumer
  'KO': ['PEP', 'MNST', 'KDP'],
  'PEP': ['KO', 'MNST', 'KDP'],
  'NKE': ['LULU', 'ADDYY', 'UAA', 'DECK'],
  'MCD': ['SBUX', 'CMG', 'YUM', 'DPZ'],
  'SBUX': ['MCD', 'CMG', 'DNKN'],
  // Streaming
  'NFLX': ['DIS', 'WBD', 'PARA', 'CMCSA'],
  'DIS': ['NFLX', 'WBD', 'PARA', 'CMCSA'],
  // Auto EV
  'TSLA': ['F', 'GM', 'RIVN', 'NIO', 'LCID'],
  // Default fallback
  'default': []
};

// Obtener competidores de un símbolo
function getCompetitors(symbol: string): string[] {
  const upperSymbol = symbol.toUpperCase();
  return SECTOR_COMPETITORS[upperSymbol] || SECTOR_COMPETITORS['default'];
}

// Función principal: Obtener sugerencias de alternativas
export async function getAlternativeSuggestions(input: {
  symbol: string;
  companyName: string;
  sector?: string;
  financialData: any;
  currentPrice: number;
}): Promise<{
  currentStock: {
    symbol: string;
    name: string;
    score: number;
    strengths: string[];
    weaknesses: string[];
  };
  alternatives: {
    symbol: string;
    name: string;
    score: number;
    reason: string;
    isBetter: boolean;
  }[];
  recommendation: string;
  summary: string;
}> {
  // Permitir en desarrollo
  try {
    const auth = await getAuth();
    if (auth) {
      const session = await auth.api.getSession({ headers: await headers() });
      if (!session?.user && process.env.NODE_ENV !== 'development') {
        throw new Error('Usuario no autenticado');
      }
    }
  } catch (authError: any) {
    if (process.env.NODE_ENV !== 'development') {
      throw new Error('Usuario no autenticado');
    }
  }

  const apiKey = process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY;
  if (!apiKey) {
    return {
      currentStock: { symbol: input.symbol, name: input.companyName, score: 0, strengths: [], weaknesses: [] },
      alternatives: [],
      recommendation: 'IA desactivada',
      summary: 'Falta API key de Gemini'
    };
  }

  // Obtener competidores
  const competitors = getCompetitors(input.symbol);
  if (competitors.length === 0) {
    return {
      currentStock: { symbol: input.symbol, name: input.companyName, score: 75, strengths: ['Datos disponibles'], weaknesses: [] },
      alternatives: [],
      recommendation: `${input.symbol} es una buena opción`,
      summary: 'No hay competidores directos en nuestra base de datos para comparar.'
    };
  }

  const system = `Eres un analista financiero experto. Evalúa si la acción seleccionada es la mejor opción de su sector o si hay alternativas mejores.

RESPONDE SOLO CON JSON VÁLIDO en este formato:
{
  "currentStock": {
    "score": número 0-100,
    "strengths": ["fortaleza1", "fortaleza2", "fortaleza3"],
    "weaknesses": ["debilidad1", "debilidad2"]
  },
  "alternatives": [
    {
      "symbol": "SIMBOLO",
      "name": "Nombre empresa",
      "score": número 0-100,
      "reason": "Por qué podría ser mejor o peor",
      "isBetter": true/false
    }
  ],
  "recommendation": "MANTENER|CONSIDERAR_ALTERNATIVAS|MEJOR_OPCION",
  "summary": "Resumen ejecutivo de 2-3 líneas"
}`;

  const metrics = input.financialData?.metrics || {};

  // 🧠 RAG: Obtener preferencias de inversión del usuario para sugerencias alineadas
  const ragContext = await getRAGContext(input.symbol, input.companyName);

  const prompt = `Compara ${input.companyName} (${input.symbol}) con sus competidores: ${competitors.join(', ')}

DATOS DE ${input.symbol}:
- Precio actual: $${input.currentPrice}
- Sector: ${input.sector || 'N/A'}
${ragContext}
- P/E Ratio: ${metrics.peRatio || 'N/A'}
- P/B Ratio: ${metrics.pbRatio || 'N/A'}
- ROE: ${metrics.roe || 'N/A'}
- ROA: ${metrics.roa || 'N/A'}
- Margen operativo: ${metrics.operatingMargin || 'N/A'}
- Deuda/Equity: ${metrics.debtToEquity || 'N/A'}
- Crecimiento ingresos: ${metrics.revenueGrowth || 'N/A'}

Evalúa:
1. ¿Es ${input.symbol} la mejor opción de su sector?
2. ¿Tiene el mayor moat (ventaja competitiva)?
3. ¿Cuáles son sus fortalezas y debilidades?
4. ¿Algún competidor podría ser mejor inversión ahora?

Responde con JSON válido únicamente.`;

  const payload = {
    contents: [{ role: 'user', parts: [{ text: `${system}\n\n${prompt}` }] }],
  };

  try {
    const model = 'gemini-3-flash-preview';
    const endpoint = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      cache: 'no-store',
    });

    const json = await res.json().catch(() => ({} as any));

    if (!res.ok) {
      console.error('Gemini Alternatives API error', res.status);
      return {
        currentStock: { symbol: input.symbol, name: input.companyName, score: 70, strengths: [], weaknesses: [] },
        alternatives: [],
        recommendation: 'Error',
        summary: 'Error al generar análisis de alternativas'
      };
    }

    const text: string | undefined = json?.candidates?.[0]?.content?.parts?.[0]?.text;
    if (!text) {
      return {
        currentStock: { symbol: input.symbol, name: input.companyName, score: 70, strengths: [], weaknesses: [] },
        alternatives: [],
        recommendation: 'N/A',
        summary: 'Sin respuesta del análisis'
      };
    }

    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) {
      return {
        currentStock: { symbol: input.symbol, name: input.companyName, score: 70, strengths: [], weaknesses: [] },
        alternatives: [],
        recommendation: 'N/A',
        summary: 'Formato de respuesta inválido'
      };
    }

    const result = JSON.parse(jsonMatch[0]);
    return {
      currentStock: {
        symbol: input.symbol,
        name: input.companyName,
        score: result.currentStock?.score || 70,
        strengths: result.currentStock?.strengths || [],
        weaknesses: result.currentStock?.weaknesses || []
      },
      alternatives: result.alternatives || [],
      recommendation: result.recommendation || 'N/A',
      summary: result.summary || ''
    };
  } catch (e) {
    console.error('Gemini alternatives error', e);
    return {
      currentStock: { symbol: input.symbol, name: input.companyName, score: 70, strengths: [], weaknesses: [] },
      alternatives: [],
      recommendation: 'Error',
      summary: 'Error de conexión'
    };
  }
}

// ============================================
// Importar Cartera desde Captura de Pantalla (IA Vision)
// ============================================

// Tipo de cambio EUR/USD aproximado (actualizar periódicamente)
const EUR_TO_USD_RATE = 1.05;

export interface ExtractedPosition {
  symbol: string;
  name: string;
  currentPrice: number;
  currentPriceUSD: number; // Precio convertido a USD
  change: number;
  changePercent: number;
  currency: 'EUR' | 'USD'; // Moneda detectada
  // Calculado: si tenemos rentabilidad, calculamos precio de compra
  estimatedBuyPrice?: number;
  shares?: number;
  marketValue?: number;
}

export async function extractPortfolioFromImage(imageBase64: string): Promise<{
  success: boolean;
  positions: ExtractedPosition[];
  summary: string;
  detectedCurrency: 'EUR' | 'USD';
  error?: string;
}> {
  // Permitir en desarrollo
  try {
    const auth = await getAuth();
    if (auth) {
      const session = await auth.api.getSession({ headers: await headers() });
      if (!session?.user && process.env.NODE_ENV !== 'development') {
        return { success: false, positions: [], summary: '', detectedCurrency: 'USD', error: 'Usuario no autenticado' };
      }
    }
  } catch (authError: any) {
    if (process.env.NODE_ENV !== 'development') {
      return { success: false, positions: [], summary: '', detectedCurrency: 'USD', error: 'Usuario no autenticado' };
    }
  }

  const apiKey = process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY;
  if (!apiKey) {
    return { success: false, positions: [], summary: '', detectedCurrency: 'USD', error: 'Falta API key de Gemini' };
  }

  const system = `Eres un experto en análisis de imágenes de carteras de inversión. Analiza esta captura de pantalla de un broker/app de inversión y extrae TODAS las posiciones que veas.

IMPORTANTE: Detecta la moneda de los precios:
- Si ves símbolo € o "EUR" → currency = "EUR"
- Si ves símbolo $ o "USD" → currency = "USD"
- Los brokers europeos (Trade Republic, DEGIRO, etc.) suelen mostrar precios en EUR

IMPORTANTE SOBRE VALORES:
- En los resúmenes de cartera, el número grande suele ser el VALOR TOTAL DE LA POSICIÓN (Market Value), NO el precio por acción.
- El precio por acción y la cantidad (shares) suelen estar en letra más pequeña.
- Intenta deducir la cantidad (shares) si es posible.

IMPORTANTE SOBRE SIGNOS (+/-):
- Fíjate en el COLOR del porcentaje de cambio:
- ROJO = NEGATIVO (Añade un signo "-" si no lo tiene)
- VERDE = POSITIVO
- Si ves una flecha hacia abajo (↓), es NEGATIVO.
- Si ves una flecha hacia arriba (↑), es POSITIVO.

Para cada posición, extrae:
- Símbolo (ticker) - Convierte símbolos europeos a US (ej: 2PP = PYPL, AMZ = AMZN, ADB = ADBE, UNH = UNH, UT8 = UBER, NOVC = NVO, RACE = RACE)
- Nombre de la empresa
- marketValue: Valor total de la posición (el número principal) en la moneda detectada
- sharePrice: Precio de una acción individual (si es visible o deducible) en la moneda detectada
- shares: Cantidad de acciones (si es visible)
- changePercent: Cambio porcentual (%)
- currency: Moneda detectada (EUR o USD)

RESPONDE SOLO CON JSON VÁLIDO en este formato:
{
  "currency": "EUR",
  "positions": [
    {
      "symbol": "PYPL",
      "name": "PayPal Holdings Inc",
      "marketValue": 474.66,
      "sharePrice": null, 
      "shares": null,
      "changePercent": -14.77
    }
  ],
  "summary": "Cartera con X posiciones en EUR."
}`;

  // Preparar payload con imagen
  const payload = {
    contents: [{
      role: 'user',
      parts: [
        { text: system },
        {
          inline_data: {
            mime_type: 'image/jpeg',
            data: imageBase64.replace(/^data:image\/(png|jpeg|jpg);base64,/, '')
          }
        }
      ]
    }]
  };

  try {
    // Usar modelo con vision
    const model = 'gemini-2.0-flash';
    const endpoint = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;

    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      cache: 'no-store',
    });

    const json = await res.json().catch(() => ({} as any));

    if (!res.ok) {
      console.error('Gemini Vision API error', res.status, json);
      return {
        success: false,
        positions: [],
        summary: '',
        detectedCurrency: 'USD',
        error: `Error de API: ${res.status}`
      };
    }

    const text: string | undefined = json?.candidates?.[0]?.content?.parts?.[0]?.text;
    if (!text) {
      return { success: false, positions: [], summary: '', detectedCurrency: 'USD', error: 'Sin respuesta de la IA' };
    }

    // Extraer JSON de la respuesta
    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) {
      return { success: false, positions: [], summary: '', detectedCurrency: 'USD', error: 'Formato de respuesta inválido' };
    }

    const result = JSON.parse(jsonMatch[0]);

    // Detectar moneda de la respuesta
    const detectedCurrency: 'EUR' | 'USD' = result.currency === 'EUR' ? 'EUR' : 'USD';

    // Mapear símbolos europeos a US
    const symbolMap: Record<string, string> = {
      '2PP': 'PYPL', 'PYPL': 'PYPL',
      'AMZ': 'AMZN', 'AMZN': 'AMZN',
      'ADB': 'ADBE', 'ADBE': 'ADBE',
      'UNH': 'UNH',
      'UT8': 'UBER', 'UBER': 'UBER',
      'NOVC': 'NVO', 'NVO': 'NVO',
      'RACE': 'RACE',
      'AAPL': 'AAPL',
      'MSFT': 'MSFT',
      'GOOGL': 'GOOGL', 'GOOG': 'GOOGL',
      'META': 'META',
      'NVDA': 'NVDA',
      'TSLA': 'TSLA',
      'V': 'V', 'VISA': 'V',
      'MA': 'MA',
      'JPM': 'JPM',
    };

    const positions: ExtractedPosition[] = (result.positions || []).map((p: any) => {
      const rawSymbol = (p.symbol || '').toUpperCase().replace(/\s/g, '');
      const mappedSymbol = symbolMap[rawSymbol] || rawSymbol;

      const marketValue = parseFloat(p.marketValue) || parseFloat(p.currentPrice) || 0;
      const sharePrice = parseFloat(p.sharePrice) || 0;
      const shares = parseFloat(p.shares) || 0;

      // Usar sharePrice si existe, si no, usar marketValue temporalmente pero marcando que es marketValue
      const effectivePrice = sharePrice > 0 ? sharePrice : marketValue;

      // Convertir a USD si está en EUR
      const priceInUSD = detectedCurrency === 'EUR'
        ? effectivePrice * EUR_TO_USD_RATE
        : effectivePrice;

      const marketValueInUSD = detectedCurrency === 'EUR'
        ? marketValue * EUR_TO_USD_RATE
        : marketValue;

      return {
        symbol: mappedSymbol,
        name: p.name || mappedSymbol,
        currentPrice: effectivePrice,
        currentPriceUSD: priceInUSD,
        change: parseFloat(p.change) || 0,
        changePercent: parseFloat(p.changePercent) || 0,
        currency: detectedCurrency,
        estimatedBuyPrice: undefined,
        shares: shares > 0 ? shares : (sharePrice > 0 ? marketValue / sharePrice : undefined),
        marketValue: marketValue,
      };
    });

    return {
      success: true,
      positions,
      summary: result.summary || `${positions.length} posiciones encontradas${detectedCurrency === 'EUR' ? ' (convertidas a USD)' : ''}`,
      detectedCurrency
    };
  } catch (e) {
    console.error('Gemini Vision error', e);
    return { success: false, positions: [], summary: '', detectedCurrency: 'USD', error: 'Error de conexión' };
  }
}
