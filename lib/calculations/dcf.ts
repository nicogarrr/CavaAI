/**
 * DCF & WACC Calculation Utilities
 * For Visual Investment Thesis
 */

export interface WACCInputs {
    riskFreeRate: number;      // 10Y Treasury rate (e.g., 0.045 = 4.5%)
    beta: number;              // Stock beta
    equityRiskPremium: number; // Market premium (typically 5-6%)
    costOfDebt: number;        // Interest rate on debt
    taxRate: number;           // Corporate tax rate (e.g., 0.21 = 21%)
    debtToEquity: number;      // D/E ratio
}

export interface DCFScenario {
    name: 'bear' | 'base' | 'bull';
    wacc: number;
    terminalGrowth: number;
    targetPrice: number;
    marginOfSafety: number;
}

export interface ThesisValuation {
    currentPrice: number;
    intrinsicValue: number;
    marginOfSafety: number;
    verdict: 'UNDERVALUED' | 'FAIRLY_VALUED' | 'OVERVALUED';
    wacc: number;
    costOfEquity: number;
    costOfDebt: number;
    terminalValue: number;
    scenarios: DCFScenario[];
}

/**
 * Calculate Cost of Equity using CAPM
 * Ke = Rf + β × (Rm - Rf)
 */
export function calculateCostOfEquity(
    riskFreeRate: number,
    beta: number,
    equityRiskPremium: number = 0.055 // Default 5.5%
): number {
    return riskFreeRate + (beta * equityRiskPremium);
}

/**
 * Calculate Weighted Average Cost of Capital (WACC)
 * WACC = (E/V × Ke) + (D/V × Kd × (1-T))
 */
export function calculateWACC(inputs: WACCInputs): number {
    const { riskFreeRate, beta, equityRiskPremium, costOfDebt, taxRate, debtToEquity } = inputs;

    // E/V and D/V from D/E ratio
    // D/E = D/E, so D = D/E × E
    // V = E + D = E + D/E × E = E × (1 + D/E)
    // E/V = E / (E × (1 + D/E)) = 1 / (1 + D/E)
    // D/V = D/E / (1 + D/E)

    const equityWeight = 1 / (1 + debtToEquity);
    const debtWeight = debtToEquity / (1 + debtToEquity);

    const costOfEquity = calculateCostOfEquity(riskFreeRate, beta, equityRiskPremium);
    const afterTaxCostOfDebt = costOfDebt * (1 - taxRate);

    return (equityWeight * costOfEquity) + (debtWeight * afterTaxCostOfDebt);
}

/**
 * Calculate Terminal Value using Gordon Growth Model
 * TV = FCF × (1 + g) / (WACC - g)
 */
export function calculateTerminalValue(
    lastFCF: number,
    wacc: number,
    perpetualGrowthRate: number = 0.025 // Default 2.5%
): number {
    if (wacc <= perpetualGrowthRate) {
        // Avoid negative or infinite terminal value
        return lastFCF * 15; // Fallback multiplier
    }
    return (lastFCF * (1 + perpetualGrowthRate)) / (wacc - perpetualGrowthRate);
}

/**
 * Calculate Intrinsic Value per Share using DCF
 */
export function calculateIntrinsicValue(
    projectedFCFs: number[], // Array of projected FCFs
    wacc: number,
    terminalValue: number,
    sharesOutstanding: number
): number {
    if (!projectedFCFs.length || sharesOutstanding <= 0) return 0;

    // Present value of projected FCFs
    let pvFCF = 0;
    projectedFCFs.forEach((fcf, i) => {
        pvFCF += fcf / Math.pow(1 + wacc, i + 1);
    });

    // Present value of terminal value (discounted from last projection year)
    const pvTerminal = terminalValue / Math.pow(1 + wacc, projectedFCFs.length);

    // Enterprise Value = PV of FCFs + PV of Terminal Value
    const enterpriseValue = pvFCF + pvTerminal;

    // Equity Value per share (simplified - should subtract debt, add cash)
    return enterpriseValue / sharesOutstanding;
}

/**
 * Calculate Margin of Safety
 */
export function calculateMarginOfSafety(
    currentPrice: number,
    intrinsicValue: number
): number {
    if (intrinsicValue <= 0) return 0;
    return ((intrinsicValue - currentPrice) / intrinsicValue) * 100;
}

/**
 * Get Valuation Verdict based on Margin of Safety
 */
export function getValuationVerdict(
    marginOfSafety: number
): 'UNDERVALUED' | 'FAIRLY_VALUED' | 'OVERVALUED' {
    if (marginOfSafety >= 15) return 'UNDERVALUED';
    if (marginOfSafety >= -10) return 'FAIRLY_VALUED';
    return 'OVERVALUED';
}

/**
 * Generate Bear/Base/Bull scenarios based on FMP's intrinsic value
 * Uses the professional DCF as base and applies sensitivity adjustments
 */
export function generateScenarios(
    fmpIntrinsicValue: number, // The DCF value from FMP API
    currentPrice: number,
    baseWACC: number,
    _projectedFCFs?: number[] // Kept for backwards compatibility
): DCFScenario[] {
    const scenarios: DCFScenario[] = [];

    // Use FMP's value as base, apply percentage adjustments for bear/bull
    const configs = [
        { name: 'bear' as const, priceAdj: 0.65, waccAdj: 0.015, growthRate: 0.015 },  // 35% haircut
        { name: 'base' as const, priceAdj: 1.0, waccAdj: 0, growthRate: 0.025 },       // FMP value as-is
        { name: 'bull' as const, priceAdj: 1.25, waccAdj: -0.01, growthRate: 0.035 }, // 25% premium
    ];

    configs.forEach(config => {
        const scenarioWACC = Math.max(0.05, baseWACC + config.waccAdj);
        const targetPrice = fmpIntrinsicValue * config.priceAdj;
        const mos = calculateMarginOfSafety(currentPrice, targetPrice);

        scenarios.push({
            name: config.name,
            wacc: scenarioWACC * 100,
            terminalGrowth: config.growthRate * 100,
            targetPrice,
            marginOfSafety: mos
        });
    });

    return scenarios;
}

/**
 * Estimate Beta from sector (fallback when not available)
 */
export function estimateBeta(sector: string): number {
    const sectorBetas: Record<string, number> = {
        'Technology': 1.2,
        'Healthcare': 0.85,
        'Financials': 1.15,
        'Consumer Cyclical': 1.2,
        'Consumer Defensive': 0.7,
        'Industrials': 1.1,
        'Energy': 1.3,
        'Utilities': 0.5,
        'Real Estate': 0.9,
        'Materials': 1.1,
        'Communication Services': 1.0,
    };

    return sectorBetas[sector] || 1.0; // Default to market beta
}

/**
 * Estimate Tax Rate by country/region
 */
export function estimateTaxRate(country: string = 'US'): number {
    const taxRates: Record<string, number> = {
        'US': 0.21,
        'UK': 0.25,
        'DE': 0.30,
        'JP': 0.30,
        'CN': 0.25,
    };

    return taxRates[country] || 0.25;
}
