'use server';

import { getStockFinancialData, getCandles, getProfile } from './finnhub.actions';
import { calculateAdvancedStockScore } from '@/lib/utils/advancedStockScoring';
import { 
    PROPICKS_STRATEGIES, 
    calculateStrategyScore, 
    passesStrategyFilters,
    type ProPickStrategy 
} from '@/lib/utils/proPicksStrategies';
import { getAuth } from '@/lib/better-auth/auth';
import { headers } from 'next/headers';

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
}

/**
 * Usa Gemini IA para preseleccionar los mejores símbolos del universo
 */
async function selectBestCandidatesWithAI(
    universeSymbols: string[],
    strategy: ProPickStrategy,
    limit: number
): Promise<string[]> {
    try {
        const auth = await getAuth();
        if (!auth) {
            console.warn('No auth available, skipping AI preselection');
            return universeSymbols.slice(0, Math.min(60, universeSymbols.length));
        }
        
        const apiKey = process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY;
        if (!apiKey) {
            console.warn('No Gemini API key, skipping AI preselection');
            return universeSymbols.slice(0, Math.min(60, universeSymbols.length));
        }

        // Obtener datos básicos de todos los símbolos (solo quote y profile)
        console.log(`Obteniendo datos básicos de ${universeSymbols.length} símbolos para preselección IA...`);
        const basicData: Array<{symbol: string; name?: string; price?: number; sector?: string; marketCap?: number}> = [];
        
        // Procesar en lotes para no saturar la API
        const batchSize = 20;
        for (let i = 0; i < Math.min(150, universeSymbols.length); i += batchSize) {
            const batch = universeSymbols.slice(i, i + batchSize);
            const promises = batch.map(async (symbol) => {
                try {
                    const profile = await getProfile(symbol);
                    if (!profile) return null;
                    
                    // Obtener quote básico
                    const token = process.env.FINNHUB_API_KEY || process.env.NEXT_PUBLIC_FINNHUB_API_KEY;
                    if (!token) return null;
                    
                    const quoteUrl = `https://finnhub.io/api/v1/quote?symbol=${encodeURIComponent(symbol)}&token=${token}`;
                    const quoteRes = await fetch(quoteUrl, { cache: 'no-store' });
                    if (!quoteRes.ok) return null;
                    const quote = await quoteRes.json();
                    
                    if (!quote.c || quote.c === 0) return null;
                    
                    return {
                        symbol,
                        name: profile.name || symbol,
                        price: quote.c,
                        sector: (profile as any)?.finnhubIndustry || (profile as any)?.industry || 'Unknown',
                        marketCap: (profile as any)?.marketCapitalization || 0,
                    };
                } catch (e) {
                    return null;
                }
            });
            
            const results = await Promise.all(promises);
            basicData.push(...results.filter((r): r is NonNullable<typeof r> => r !== null));
            
            // Delay entre lotes
            if (i + batchSize < universeSymbols.length) {
                await new Promise(resolve => setTimeout(resolve, 1000));
            }
        }

        if (basicData.length === 0) {
            return universeSymbols.slice(0, Math.min(60, universeSymbols.length));
        }

        // Preparar prompt para Gemini
        const systemPrompt = `Eres un analista financiero experto. Analiza los datos básicos de acciones y selecciona las ${limit * 3} mejores candidatas según la estrategia de inversión especificada.

Estrategia: ${strategy.name}
Descripción: ${strategy.description}
Categorías priorizadas: ${Object.entries(strategy.categoryWeights)
    .filter(([_, weight]) => weight > 0.15)
    .map(([cat, weight]) => `${cat} (${(weight * 100).toFixed(0)}%)`)
    .join(', ')}

Criterios de selección:
1. Diversificación sectorial (máximo 2-3 por sector)
2. Calidad de la empresa (nombre conocido, liquidez)
3. Potencial según la estrategia
4. Valor relativo (precio razonable vs mercado)
5. Tamaño de mercado (preferir mid-cap a large-cap para mayor potencial)

RESPONDE SOLO CON UNA LISTA DE SÍMBOLOS SEPARADOS POR COMAS, en el formato exacto:
SYMBOL1,SYMBOL2,SYMBOL3,...

NO incluyas explicaciones, solo los símbolos.`;

        const dataText = basicData.map(d => 
            `${d.symbol} (${d.name}): Precio $${d.price?.toFixed(2) || 'N/A'}, Sector: ${d.sector || 'Unknown'}, MarketCap: ${d.marketCap ? (d.marketCap / 1e9).toFixed(1) + 'B' : 'N/A'}`
        ).join('\n');

        const prompt = `${systemPrompt}\n\nDatos de acciones disponibles (${basicData.length} total):\n${dataText}\n\nSelecciona las ${limit * 3} mejores candidatas y responde SOLO con los símbolos separados por comas:`;

        const payload = {
            contents: [{
                role: 'user',
                parts: [{ text: prompt }],
            }],
        };

        const model = 'gemini-2.5-flash';
        const endpoint = `https://generativelanguage.googleapis.com/v1/models/${model}:generateContent?key=${apiKey}`;
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            cache: 'no-store',
        });

        const json = await res.json().catch(() => ({} as any));
        
        if (!res.ok) {
            console.warn('Gemini preselection failed, using fallback:', res.status);
            return basicData
                .sort((a, b) => (b.marketCap || 0) - (a.marketCap || 0))
                .slice(0, Math.min(limit * 3, basicData.length))
                .map(d => d.symbol);
        }

        const text: string | undefined = json?.candidates?.[0]?.content?.parts?.[0]?.text;
        if (!text) {
            return basicData
                .sort((a, b) => (b.marketCap || 0) - (a.marketCap || 0))
                .slice(0, Math.min(limit * 3, basicData.length))
                .map(d => d.symbol);
        }

        // Extraer símbolos de la respuesta
        const selectedSymbols = text
            .split(/[,，\n]/)
            .map(s => s.trim().toUpperCase().replace(/[^A-Z0-9]/g, ''))
            .filter(s => s.length >= 2 && s.length <= 5 && universeSymbols.includes(s))
            .slice(0, limit * 3);

        console.log(`IA preseleccionó ${selectedSymbols.length} símbolos de ${basicData.length} evaluados`);
        return selectedSymbols.length > 0 ? selectedSymbols : basicData.slice(0, Math.min(limit * 3, basicData.length)).map(d => d.symbol);
    } catch (error) {
        console.error('Error en preselección IA, usando fallback:', error);
        return universeSymbols.slice(0, Math.min(60, universeSymbols.length));
    }
}

/**
 * ProPicks IA Mejorado - Similar a Investing Pro
 * 
 * Características:
 * - Universo masivo expandido (~300+ símbolos)
 * - Preselección con IA (Gemini) antes de evaluación completa
 * - Comparación con sector (crucial)
 * - Múltiples categorías de métricas
 * - Estrategias predefinidas
 * - Scoring avanzado
 * - Diversificación sectorial forzada
 */
export async function generateProPicks(
    limit: number = 10,
    strategyId?: string
): Promise<ProPick[]> {
    try {
        // Seleccionar estrategia o usar estrategia por defecto
        const strategy = strategyId 
            ? PROPICKS_STRATEGIES.find(s => s.id === strategyId)
            : PROPICKS_STRATEGIES[0]; // 'beat-sp500' por defecto

        if (!strategy) {
            throw new Error(`Estrategia no encontrada: ${strategyId}`);
        }

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

        // Paso 1: Usar IA para preseleccionar los mejores candidatos
        console.log(`Preseleccionando mejores candidatos de ${universeSymbols.length} símbolos usando IA...`);
        const preselectedSymbols = await selectBestCandidatesWithAI(universeSymbols, strategy, limit);
        
        console.log(`Evaluando ${preselectedSymbols.length} símbolos preseleccionados con scoring completo...`);

        const picks: ProPick[] = [];
        const allEvaluatedPicks: ProPick[] = [];
        
        // Paso 2: Evaluar solo los preseleccionados con scoring completo
        for (let i = 0; i < preselectedSymbols.length; i++) {
            const symbol = preselectedSymbols[i];
            
            try {
                // Obtener datos financieros completos
                const financialData = await getStockFinancialData(symbol);
                
                if (!financialData || !financialData.profile) {
                    await new Promise(resolve => setTimeout(resolve, 300));
                    continue;
                }

                const sector = (financialData.profile as any)?.finnhubIndustry || (financialData.profile as any)?.industry || 'Unknown';
                const currentPrice = financialData.quote?.c || financialData.quote?.price || 0;
                const marketCap = (financialData.profile as any)?.marketCapitalization || 0;

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

                const pick: ProPick = {
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
                };

                allEvaluatedPicks.push(pick);

                // Si pasa los filtros de la estrategia, agregarlo
                if (passesStrategyFilters(advancedScore, strategy, sector, currentPrice, marketCap)) {
                    picks.push(pick);
                }

                // Delay entre requests
                await new Promise(resolve => setTimeout(resolve, 300));
            } catch (error: any) {
                if (error?.message?.includes('429') || error?.message?.includes('limit')) {
                    console.warn(`Rate limit reached, stopping at ${picks.length} picks`);
                    break;
                }
                console.error(`Error evaluating ${symbol}:`, error);
                await new Promise(resolve => setTimeout(resolve, 300));
                continue;
            }

            if (picks.length >= limit * 1.5) {
                break;
            }
        }

        // Si tenemos picks que pasaron los filtros, aplicar diversificación sectorial
        if (picks.length > 0) {
            // Función para calcular score de diversificación
            const getDiversificationScore = (pick: ProPick, currentSectorCount: Map<string, number>): number => {
                const sector = pick.sector || 'Unknown';
                const currentCount = currentSectorCount.get(sector) || 0;
                const sectorPenalty = Math.min(currentCount * 5, 15);
                
                const vsSectorBonus = pick.vsSector 
                    ? (pick.vsSector.value + pick.vsSector.profitability + pick.vsSector.growth) / 30
                    : 0;
                
                return (pick.strategyScore ?? pick.score) - sectorPenalty + vsSectorBonus;
            };

            // Ordenar picks considerando diversificación sectorial
            const diversifiedPicks: ProPick[] = [];
            const usedSectors = new Map<string, number>();
            const remainingPicks = [...picks];

            // Agrupar por sector
            const sectorGroups = new Map<string, ProPick[]>();
            remainingPicks.forEach(pick => {
                const sector = pick.sector || 'Unknown';
                if (!sectorGroups.has(sector)) {
                    sectorGroups.set(sector, []);
                }
                sectorGroups.get(sector)!.push(pick);
            });

            // Seleccionar top picks de cada sector (hasta 2 por sector)
            sectorGroups.forEach((sectorPicks, sector) => {
                const sorted = sectorPicks.sort((a, b) => {
                    const scoreA = a.strategyScore ?? a.score;
                    const scoreB = b.strategyScore ?? b.score;
                    return scoreB - scoreA;
                });
                const topPicks = sorted.slice(0, 2);
                topPicks.forEach(pick => {
                    diversifiedPicks.push(pick);
                    usedSectors.set(sector, (usedSectors.get(sector) || 0) + 1);
                });
            });

            // Completar si faltan picks
            if (diversifiedPicks.length < limit) {
                const remaining = remainingPicks
                    .filter(p => !diversifiedPicks.includes(p))
                    .sort((a, b) => {
                        const divScoreA = getDiversificationScore(a, usedSectors);
                        const divScoreB = getDiversificationScore(b, usedSectors);
                        return divScoreB - divScoreA;
                    });

                const needed = limit - diversifiedPicks.length;
                for (let i = 0; i < needed && i < remaining.length; i++) {
                    const pick = remaining[i];
                    diversifiedPicks.push(pick);
                    const sector = pick.sector || 'Unknown';
                    usedSectors.set(sector, (usedSectors.get(sector) || 0) + 1);
                }
            }

            // Ordenar final por strategyScore
            const sortedPicks = diversifiedPicks.sort((a, b) => {
                const scoreA = a.strategyScore ?? a.score;
                const scoreB = b.strategyScore ?? b.score;
                return scoreB - scoreA;
            });

            return sortedPicks.slice(0, limit);
        }

        // Fallback: usar los mejores evaluados
        if (allEvaluatedPicks.length > 0) {
            console.warn(`No se encontraron picks que pasen todos los filtros, usando los mejores evaluados`);
            
            const sortedAllPicks = allEvaluatedPicks.sort((a, b) => {
                const scoreA = a.strategyScore ?? a.score;
                const scoreB = b.strategyScore ?? b.score;
                return scoreB - scoreA;
            });

            return sortedAllPicks.slice(0, limit);
        }

        return [];
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