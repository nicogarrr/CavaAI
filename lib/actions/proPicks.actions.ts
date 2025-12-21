'use server';

import { getStockFinancialDataLight, getCandles, getProfile } from './finnhub.actions';
import { calculateAdvancedStockScore } from '@/lib/utils/advancedStockScoring';
import {
    PROPICKS_STRATEGIES,
    calculateStrategyScore,
    passesStrategyFilters,
    type ProPickStrategy
} from '@/lib/utils/proPicksStrategies';
import { getAuth } from '@/lib/better-auth/auth';
import { headers } from 'next/headers';
import { getRAGContext } from './ai.actions';

export interface ProPick {
    symbol: string;
    company: string;
    score: number;
    grade: string;
    strategyScore?: number; // Score según estrategia específica
    strategy?: string; // ID de la estrategia aplicada
    categoryScores: {
        value: number;
        growth: number;
        profitability: number;
        cashFlow: number;
        momentum: number;
        debtLiquidity: number;
    };
    reasons: string[];
    currentPrice: number;
    sector?: string;
    exchange?: string;
    vsSector?: {
        value: number;
        growth: number;
        profitability: number;
        cashFlow: number;
        momentum: number;
        debtLiquidity: number;
    };
    upsidePotential?: number; // % de subida potencial según analistas (12 meses)
    isStrongBuy?: boolean; // Flag para "Gritar Compra" (Score > 80 + Upside > 15%)
    targetPrice?: number;
}

/**
 * Usa Gemini IA para seleccionar las mejores acciones basándose en datos reales completos
 */
async function selectBestPicksWithAI(
    evaluatedPicks: ProPick[],
    limit: number
): Promise<ProPick[]> {
    try {
        const apiKey = process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY;
        if (!apiKey) {
            console.warn('No Gemini API key, usando selección por score');
            return evaluatedPicks
                .sort((a, b) => (b.strategyScore ?? b.score) - (a.strategyScore ?? a.score))
                .slice(0, limit);
        }

        if (evaluatedPicks.length === 0) {
            return [];
        }

        // Preparar datos completos para la IA
        const picksData = evaluatedPicks.map(pick => {
            const vsSector = pick.vsSector || {
                value: 0,
                growth: 0,
                profitability: 0,
                cashFlow: 0,
                momentum: 0,
                debtLiquidity: 0,
            };
            return {
                symbol: pick.symbol,
                company: pick.company,
                score: pick.score,
                grade: pick.grade,
                strategyScore: pick.strategyScore || pick.score,
                sector: pick.sector || 'Unknown',
                price: pick.currentPrice,
                categoryScores: pick.categoryScores,
                vsSector: {
                    value: vsSector.value || 0,
                    profitability: vsSector.profitability || 0,
                    growth: vsSector.growth || 0,
                    cashFlow: vsSector.cashFlow || 0,
                    momentum: vsSector.momentum || 0,
                },
                reasons: pick.reasons,
            };
        });

        // Prompt para Gemini - 100% IMPARCIAL

        // 🧠 RAG: Obtener criterios de inversión generales del usuario
        // Usamos un símbolo genérico para recuperar documentos de estrategia/criterios
        const ragContext = await getRAGContext('ESTRATEGIA', 'Criterios de Inversión Personal');

        const systemPrompt = `Eres un analista financiero experto e IMPARCIAL. Analiza los datos REALES COMPLETOS de ${evaluatedPicks.length} acciones ya evaluadas y selecciona las ${limit} MEJORES opciones de inversión en este momento basándote ÚNICAMENTE en datos reales y objetivos, sin sesgos ni preconcepciones:

DATOS REALES DISPONIBLES:
- Score general (0-100)
- Grade (A+ a F)
- Scores por categoría: Valor, Crecimiento, Rentabilidad, Flujo de Caja, Momentum, Deuda/Liquidez
- Comparación con sector (si está mejor o peor que el promedio)
- Razones específicas de cada acción
- Sector de cada empresa
${ragContext ? '\n' + ragContext + '\n\nIMPORTANTE: Usa los criterios de inversión de la BASE DE CONOCIMIENTO (arriba) para filtrar y priorizar las acciones que mejor se ajusten a la filosofía del usuario.' : ''}

CRITERIOS DE SELECCIÓN OBJETIVOS (basados SOLO en datos reales):
1. **Score general alto basado en datos reales** (priorizar scores >70, pero evalúa objetivamente todos los scores)
2. **Comparación objetiva con sector** (evalúa si están mejor o peor que su sector promedio según datos reales)
3. **Balance entre categorías** (evalúa objetivamente si hay balance o desequilibrio según datos reales)
4. **Diversificación sectorial** (máximo 2-3 por sector si es posible, pero no fuerces diversificación si los datos muestran concentración)
5. **Razones sólidas basadas en datos reales** (fortalezas y oportunidades reales identificadas en los datos, no asumidas)
6. **JOYAS OCULTAS**: Prioriza fuertemente las acciones marcadas como [💎 JOYA OCULTA] si sus fundamentos lo respaldan
7. **IMPARCIALIDAD**: NO favorezcas acciones por sector o nombre - selecciona basándote SOLO en los datos reales proporcionados

RESPONDE SOLO CON UNA LISTA DE SÍMBOLOS SEPARADOS POR COMAS, en el formato exacto:
SYMBOL1,SYMBOL2,SYMBOL3,...

Selecciona las ${limit} mejores opciones basándote en los datos reales actuales. NO incluyas explicaciones, solo los símbolos.`;

        const dataText = picksData.map(p => {
            const sectorStatus = p.vsSector.value > 0 && p.vsSector.profitability > 0 ? 'Mejor que sector' : 'Promedio sector';
            const upsideInfo = p.upsidePotential ? `, Upside: +${p.upsidePotential.toFixed(1)}%` : '';
            const strongBuyBadge = p.isStrongBuy ? ' [💎 JOYA OCULTA]' : '';
            return `${p.symbol} (${p.company})${strongBuyBadge}: Score ${p.score} (${p.grade}), StrategyScore ${p.strategyScore}${upsideInfo}, Sector: ${p.sector}
  Categorías: Valor ${p.categoryScores.value}, Crecimiento ${p.categoryScores.growth}, Rentabilidad ${p.categoryScores.profitability}, CashFlow ${p.categoryScores.cashFlow}, Momentum ${p.categoryScores.momentum}
  ${sectorStatus}: Valor ${p.vsSector.value > 0 ? '+' : ''}${p.vsSector.value.toFixed(1)}, Profitability ${p.vsSector.profitability > 0 ? '+' : ''}${p.vsSector.profitability.toFixed(1)}, Growth ${p.vsSector.growth > 0 ? '+' : ''}${p.vsSector.growth.toFixed(1)}
  Razones: ${p.reasons.slice(0, 3).join('; ')}
  Precio: $${p.price?.toFixed(2) || 'N/A'}`;
        }).join('\n\n');

        const prompt = `${systemPrompt}\n\nDatos completos de acciones evaluadas:\n\n${dataText}\n\nSelecciona las ${limit} mejores opciones de inversión basándote en TODOS estos datos reales y responde SOLO con los símbolos separados por comas:`;

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
            console.warn('Gemini selection failed, using score-based fallback:', res.status);
            return evaluatedPicks
                .sort((a, b) => (b.strategyScore ?? b.score) - (a.strategyScore ?? a.score))
                .slice(0, limit);
        }

        const text: string | undefined = json?.candidates?.[0]?.content?.parts?.[0]?.text;
        if (!text) {
            return evaluatedPicks
                .sort((a, b) => (b.strategyScore ?? b.score) - (a.strategyScore ?? a.score))
                .slice(0, limit);
        }

        // Extraer símbolos de la respuesta
        const selectedSymbols = text
            .split(/[,，\n]/)
            .map(s => s.trim().toUpperCase().replace(/[^A-Z0-9]/g, ''))
            .filter(s => s.length >= 2 && s.length <= 5)
            .slice(0, limit);

        // Mapear símbolos seleccionados a ProPick completos
        const selectedPicks = selectedSymbols
            .map(symbol => evaluatedPicks.find(p => p.symbol === symbol))
            .filter((p): p is ProPick => p !== undefined);

        console.log(`IA seleccionó ${selectedPicks.length} picks de ${evaluatedPicks.length} evaluados`);

        // Si la IA no seleccionó suficientes, completar con los mejores restantes
        if (selectedPicks.length < limit) {
            const remaining = evaluatedPicks
                .filter(p => !selectedSymbols.includes(p.symbol))
                .sort((a, b) => (b.strategyScore ?? b.score) - (a.strategyScore ?? a.score))
                .slice(0, limit - selectedPicks.length);

            return [...selectedPicks, ...remaining].slice(0, limit);
        }

        return selectedPicks.slice(0, limit);
    } catch (error) {
        console.error('Error en selección IA, usando fallback:', error);
        return evaluatedPicks
            .sort((a, b) => (b.strategyScore ?? b.score) - (a.strategyScore ?? a.score))
            .slice(0, limit);
    }
}

/**
 * ProPicks IA Adaptativo - La IA selecciona las mejores acciones según datos reales actuales
 * 
 * Características:
 * - Universo masivo expandido (~300+ símbolos)
 * - Evaluación completa de datos financieros reales
 * - Selección final con IA (Gemini) basándose en TODOS los datos reales
 * - Sin estrategias predefinidas - la IA decide las mejores opciones en cada momento
 * - Comparación con sector (crucial)
 * - Diversificación sectorial inteligente
 */
export async function generateProPicks(
    limit: number = 5,
    strategyId?: string
): Promise<ProPick[]> {
    try {
        // Usar única estrategia adaptativa
        const strategy = PROPICKS_STRATEGIES[0]; // Siempre la estrategia adaptativa

        // Universo expandido masivo - ~300+ símbolos
        const universeSymbols = [
            // Technology (50+)
            'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'NVDA', 'META', 'TSLA', 'AMD', 'INTC', 'CRM',
            'AVGO', 'QCOM', 'TXN', 'ADBE', 'ORCL', 'NOW', 'SNOW', 'PANW', 'CRWD', 'ZS', 'NET',
            'DDOG', 'FROG', 'ESTC', 'MNDY', 'DOCN', 'ASAN', 'DOCU', 'COUP', 'OKTA', 'ZM', 'TEAM',
            'WDAY', 'VEEV', 'SPLK', 'MDB', 'AKAM', 'FFIV', 'FTNT', 'CHKP', 'QLYS', 'RPD',
            'TYL', 'EPAM', 'GTLB', 'PD', 'U', 'RBLX', 'GME', 'HOOD',
            // Financials (40+)
            'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'V', 'MA', 'PYPL', 'AXP', 'COF', 'SCHW',
            'BLK', 'BX', 'KKR', 'APO', 'TROW', 'BEN', 'IVZ', 'SOFI', 'NU', 'UPST', 'LC',
            'AFRM', 'SQ', 'FISV', 'FIS', 'JKHY', 'FLYW', 'PAYO', 'BILL', 'COIN', 'MARA',
            'RIOT', 'GBTC', 'ETHE', 'HIVE', 'BITF', 'HUT',
            // Healthcare (60+)
            'JNJ', 'PFE', 'UNH', 'ABBV', 'MRK', 'LLY', 'TMO', 'ABT', 'DHR', 'ISRG', 'CI',
            'CVS', 'ELV', 'HCA', 'ZTS', 'NVO', 'NVS', 'SNY', 'RHHBY', 'TAK', 'GSK', 'AZN',
            'BMY', 'BIIB', 'GILD', 'REGN', 'VRTX', 'BMRN', 'ALNY', 'ARWR', 'FOLD', 'IONS',
            'PTCT', 'RNA', 'SGMO', 'BLUE', 'RGNX', 'AGIO', 'AGEN', 'ALKS', 'ALLO', 'AMGN',
            'BHVN', 'BPMC', 'CDMO', 'CERE', 'CLVS', 'CRSP', 'CRVS', 'CTLT', 'DCPH', 'EDIT',
            'FGEN', 'GOSS', 'IMGN', 'IOVA', 'KYMR', 'LGND', 'LYEL', 'MRUS', 'NTLA',
            // Consumer Discretionary (50+)
            'WMT', 'HD', 'NKE', 'MCD', 'SBUX', 'DIS', 'NFLX', 'TJX', 'LOW', 'TGT', 'BKNG',
            'EXPE', 'ABNB', 'TRIP', 'MAR', 'HLT', 'HYATT', 'WH', 'CHH', 'MGM', 'LVS',
            'WYNN', 'CZR', 'PENN', 'DKNG', 'FAND', 'EA', 'ATVI', 'TTWO', 'BBY', 'GPS',
            'ANF', 'AEO', 'DKS', 'HIBB', 'ASO', 'WSM', 'RH', 'PTON', 'LULU', 'ONON',
            'HOKA', 'DECK', 'VFC', 'COLM',
            // Consumer Staples (25+)
            'PG', 'KO', 'PEP', 'COST', 'PM', 'MO', 'CL', 'EL', 'CLX', 'CHD', 'NWL', 'ENR',
            'KMB', 'SJM', 'CPB', 'GIS', 'HSY', 'HRL', 'TAP', 'SAM', 'BUD', 'STZ', 'TPB',
            'DEO', 'BF.B', 'HEINY',
            // Industrial (40+)
            'BA', 'CAT', 'GE', 'HON', 'UNP', 'RTX', 'ETN', 'EMR', 'CMI', 'ITW', 'DE', 'PH',
            'AME', 'ROK', 'DOV', 'GGG', 'NOC', 'LMT', 'GD', 'HWM', 'TXT', 'FTV', 'IR',
            'XRAY', 'BDX', 'BSX', 'EW', 'ZBH', 'BAX', 'ALGN', 'INVH', 'ALG', 'APOG',
            'AXON', 'BECN', 'BLDR', 'CSWI', 'DY', 'FAST', 'FIX', 'GFF', 'HDS', 'HEES',
            // Energy (30+)
            'XOM', 'CVX', 'COP', 'SLB', 'MPC', 'VLO', 'PSX', 'EOG', 'DVN', 'FANG', 'MRO',
            'OVV', 'SWN', 'CTRA', 'NOV', 'OXY', 'APA', 'HAL', 'BKR', 'LBRT', 'WTTR',
            'CLB', 'NBR', 'PTEN', 'SPN', 'WTI', 'CRK', 'TALO', 'SM', 'PDC', 'MTDR',
            // Communication (20+)
            'VZ', 'T', 'CMCSA', 'SPOT', 'WMG', 'LYV', 'LIVE', 'EGHT', 'BAND', 'TWLO',
            'VZIO', 'FYBR', 'ASTS', 'GSAT', 'ATEX', 'CALL', 'COMM', 'INFN', 'NTNX',
            'OTEX', 'RPD', 'VIAV',
            // Utilities (20+)
            'NEE', 'DUK', 'SO', 'D', 'AEP', 'EXC', 'SRE', 'XEL', 'PEG', 'ED', 'ES',
            'ETR', 'FE', 'AES', 'NRG', 'VST', 'CEG', 'CNP', 'NI', 'OGE', 'PNW',
            // Materials (25+)
            'LIN', 'APD', 'ECL', 'SHW', 'PPG', 'FCX', 'NEM', 'GOLD', 'AU', 'AG', 'SLV',
            'AA', 'CLF', 'STLD', 'X', 'NUE', 'CMC', 'RS', 'RYI', 'TX', 'ZEUS', 'AMR',
            'MT', 'PKX', 'PBR', 'VALE',
            // Real Estate (25+)
            'AMT', 'PLD', 'EQIX', 'PSA', 'WELL', 'PEAK', 'VTR', 'VICI', 'EXPI', 'RDFN',
            'Z', 'OPEN', 'RKT', 'COMP', 'REAX', 'ACRE', 'ACHR', 'ADC', 'AKR', 'ALEX',
            'BRT', 'BRX', 'BTI', 'BXP', 'CDP', 'CIO', 'CLI', 'CMCT',
            // International (30+)
            'TSM', 'ASML', 'BABA', 'JD', 'PDD', 'TME', 'BILI', 'NIO', 'XPEV', 'LI', 'SE',
            'GRAB', 'DIDI', 'BIDU', 'WB', 'NTES', 'TAL', 'EDU', 'YMM', 'TUYA', 'ACH',
            'VIPS', 'YQ', 'TIGR', 'FUTU', 'GSX', 'LAIX', 'LX', 'MOMO', 'QTT',
            // Others / Emerging (20+)
            'HOOD', 'SOFI', 'UPST', 'AFRM', 'LC', 'NU', 'PAGS', 'STNE', 'MELI', 'ARCE',
            'DESP', 'PAM', 'IRDM', 'ORBC', 'SATS', 'VSAT',
        ];

        // Evaluar múltiples símbolos del universo (máximo 80 para tener buenas opciones)
        const symbolsToEvaluate = universeSymbols.slice(0, Math.min(80, universeSymbols.length));
        console.log(`Evaluando ${symbolsToEvaluate.length} símbolos con datos completos...`);

        const allEvaluatedPicks: ProPick[] = [];

        // Optimización: Procesamiento en paralelo con control de concurrencia
        const BATCH_SIZE = 5; // Procesar de 5 en 5 para no saturar la API
        const DELAY_BETWEEN_BATCHES = 1000; // 1 segundo entre lotes

        for (let i = 0; i < symbolsToEvaluate.length; i += BATCH_SIZE) {
            const batch = symbolsToEvaluate.slice(i, i + BATCH_SIZE);
            console.log(`Procesando lote ${i / BATCH_SIZE + 1} de ${Math.ceil(symbolsToEvaluate.length / BATCH_SIZE)}: ${batch.join(', ')}`);

            const batchPromises = batch.map(async (symbol) => {
                try {
                    // Use lightweight version - no news, events, peers (much faster)
                    const financialData = await getStockFinancialDataLight(symbol);

                    if (!financialData || !financialData.profile) return null;

                    const sector = (financialData.profile as any)?.finnhubIndustry || (financialData.profile as any)?.industry || 'Unknown';
                    const currentPrice = financialData.quote?.c || financialData.quote?.price || 0;

                    // Obtener datos históricos para momentum
                    let historicalData;
                    try {
                        const to = Math.floor(Date.now() / 1000);
                        const from = to - (365 * 24 * 60 * 60);
                        const candles = await getCandles(symbol, from, to, 'D', 3600);
                        if (candles.s === 'ok' && candles.c.length > 0) {
                            historicalData = {
                                prices: candles.c,
                                dates: candles.t,
                            };
                        }
                    } catch (e) {
                        // Continuar sin datos históricos
                    }

                    // Calcular score avanzado
                    const advancedScore = await calculateAdvancedStockScore(
                        financialData,
                        historicalData || undefined
                    );

                    // Calcular score según estrategia
                    const strategyScore = calculateStrategyScore(advancedScore, strategy);

                    // Combinar razones
                    const allReasons = [
                        ...advancedScore.reasons.strengths,
                        ...advancedScore.reasons.opportunities,
                    ].slice(0, 5);

                    return {
                        symbol,
                        company: financialData.profile.name || symbol,
                        score: advancedScore.overallScore,
                        grade: advancedScore.grade,
                        strategyScore,
                        strategy: strategy.id,
                        categoryScores: advancedScore.categoryScores,
                        reasons: allReasons.length > 0 ? allReasons : [
                            'Fundamentos sólidos',
                            'Buena salud financiera',
                            'Potencial de crecimiento',
                        ],
                        currentPrice,
                        sector,
                        exchange: financialData.profile.exchange || undefined,
                        vsSector: advancedScore.sectorComparison?.vsSector,
                        upsidePotential: 0,
                        isStrongBuy: false,
                        targetPrice: 0,
                    } as ProPick;

                    // Calculate Upside Potential & Strong Buy Logic
                    if (financialData.priceTarget && financialData.priceTarget.targetMean && currentPrice > 0) {
                        const targetMean = financialData.priceTarget.targetMean;
                        const upside = ((targetMean - currentPrice) / currentPrice) * 100;

                        pick.targetPrice = targetMean;
                        pick.upsidePotential = upside;

                        // "Screaming Buy" Criteria: 
                        // 1. Excellent Fundamentals (Score >= 80)
                        // 2. High Upside Potential (> 15%)
                        if (pick.score >= 80 && upside > 15) {
                            pick.isStrongBuy = true;
                            pick.reasons.unshift('💎 JOYA OCULTA: Fuerte subida proyectada a 12 meses');
                        }
                    }

                    return pick;

                } catch (error: any) {
                    console.error(`Error evaluating ${symbol}:`, error);
                    return null;
                }
            });

            // Esperar a que termine el lote actual
            const batchResults = await Promise.all(batchPromises);

            // Filtrar nulos y agregar a resultados
            batchResults.forEach(res => {
                if (res) allEvaluatedPicks.push(res);
            });

            // Delay entre lotes para respetar rate limits
            if (i + BATCH_SIZE < symbolsToEvaluate.length) {
                await new Promise(resolve => setTimeout(resolve, DELAY_BETWEEN_BATCHES));
            }
        }

        // Filtrar picks con score mínimo razonable
        const qualifiedPicks = allEvaluatedPicks.filter(p => p.score >= 60);

        if (qualifiedPicks.length === 0) {
            console.warn('No hay picks con score suficiente');
            return allEvaluatedPicks
                .sort((a, b) => (b.strategyScore ?? b.score) - (a.strategyScore ?? a.score))
                .slice(0, limit);
        }

        // Paso 2: Usar IA para seleccionar las mejores basándose en TODOS los datos reales
        console.log(`Usando IA para seleccionar las ${limit} mejores opciones de ${qualifiedPicks.length} evaluadas...`);
        const finalPicks = await selectBestPicksWithAI(qualifiedPicks, limit);

        return finalPicks;
    } catch (error) {
        console.error('Error generating ProPicks:', error);
        return [];
    }
}

/**
 * Genera ProPicks para una estrategia específica
 */
export async function generateProPicksForStrategy(
    strategyId: string,
    limit: number = 10
): Promise<ProPick[]> {
    return generateProPicks(limit, strategyId);
}

/**
 * Obtiene todas las estrategias disponibles
 */
export async function getAvailableStrategies() {
    return PROPICKS_STRATEGIES.map(s => ({
        id: s.id,
        name: s.name,
        description: s.description,
    }));
}

export interface EnhancedProPicksFilters {
    timePeriod?: 'week' | 'month' | 'quarter' | 'year';
    limit?: number;
    minScore?: number;
    sector?: string;
    sortBy?: 'score' | 'momentum' | 'value' | 'growth' | 'profitability';
}

// Buffer multiplier for initial picks generation to ensure enough options after filtering
const FILTER_BUFFER_MULTIPLIER = 3;

/**
 * Genera ProPicks con filtros avanzados (similar a Investing Pro)
 * Soporta filtrado por período, sector, score mínimo y ordenamiento personalizado
 */
export async function generateEnhancedProPicks(
    filters: EnhancedProPicksFilters = {}
): Promise<ProPick[]> {
    const {
        timePeriod = 'month',
        limit = 20,
        minScore = 70,
        sector = 'all',
        sortBy = 'score'
    } = filters;

    try {
        // Generar picks base con limite más alto para tener opciones para filtrar
        // Usamos un multiplicador buffer para asegurar suficientes resultados post-filtrado
        const basePicks = await generateProPicks(Math.min(limit * FILTER_BUFFER_MULTIPLIER, 100));

        // Filtrar por score mínimo
        let filteredPicks = basePicks.filter(pick => pick.score >= minScore);

        // Filtrar por sector si se especifica
        if (sector !== 'all') {
            // Crear mapa de alias de sectores para manejar diferentes nombres
            const sectorAliases: Record<string, string[]> = {
                'Technology': ['Technology', 'Information Technology', 'Software', 'Semiconductors', 'Internet'],
                'Healthcare': ['Healthcare', 'Biotechnology', 'Pharmaceuticals', 'Medical Devices', 'Health Care'],
                'Financial Services': ['Financial Services', 'Financials', 'Banks', 'Insurance', 'Asset Management'],
                'Consumer Discretionary': ['Consumer Discretionary', 'Retail', 'Apparel', 'Hotels', 'Restaurants'],
                'Industrials': ['Industrials', 'Aerospace', 'Defense', 'Machinery', 'Industrial'],
                'Consumer Staples': ['Consumer Staples', 'Food', 'Beverages', 'Tobacco', 'Household Products'],
                'Energy': ['Energy', 'Oil', 'Gas', 'Petroleum'],
                'Utilities': ['Utilities', 'Electric Utilities', 'Power'],
                'Real Estate': ['Real Estate', 'REITs', 'Property'],
                'Materials': ['Materials', 'Chemicals', 'Mining', 'Metals', 'Basic Materials'],
                'Communication Services': ['Communication Services', 'Media', 'Entertainment', 'Telecom', 'Telecommunications']
            };

            const sectorKeywords = sectorAliases[sector] || [sector];
            filteredPicks = filteredPicks.filter(pick => {
                if (!pick.sector) return false;
                const pickSectorLower = pick.sector.toLowerCase();
                return sectorKeywords.some(keyword =>
                    pickSectorLower.includes(keyword.toLowerCase())
                );
            });
        }

        // Ordenar según el criterio seleccionado
        filteredPicks.sort((a, b) => {
            switch (sortBy) {
                case 'momentum':
                    return b.categoryScores.momentum - a.categoryScores.momentum;
                case 'value':
                    return b.categoryScores.value - a.categoryScores.value;
                case 'growth':
                    return b.categoryScores.growth - a.categoryScores.growth;
                case 'profitability':
                    return b.categoryScores.profitability - a.categoryScores.profitability;
                case 'score':
                default:
                    return (b.strategyScore ?? b.score) - (a.strategyScore ?? a.score);
            }
        });

        // Aplicar límite final
        return filteredPicks.slice(0, limit);
    } catch (error) {
        console.error('Error generating enhanced ProPicks:', error);
        return [];
    }
}
