'use server';

import { getPortfolioSummary } from './portfolio.actions';
import { getStockQuote } from './finnhub.actions';

// Scenarios definition with sector sensitivities (simplified for MVP)
// Values represent expected % change in that sector
const SCENARIOS: any = {
    'inflation_high': {
        name: 'Alta Inflación Persistente (5%)',
        description: 'La inflación se mantiene alta, forzando tipos altos. Sufren Growth y Consumo.',
        factors: {
            'Technology': -15,
            'Consumer Cyclical': -10,
            'Real Estate': -12,
            'Financial Services': 5, // Banks often benefit from higher rates
            'Energy': 10,
            'Healthcare': -2,
            'Utilities': -5,
            'Communication Services': -10,
            'Industrials': -5,
            'Basic Materials': 5,
            'default': -8
        },
        marketImpact: -10
    },
    'recession_2025': {
        name: 'Recesión Global 2025',
        description: 'Desaceleración económica severa. Caída de demanda y beneficios.',
        factors: {
            'Technology': -20,
            'Consumer Cyclical': -25, // Luxury/Discretionary hit hard
            'Real Estate': -15,
            'Financial Services': -15,
            'Energy': -20, // Low demand
            'Healthcare': 5, // Defensive
            'Utilities': 2, // Defensive
            'Communication Services': -15,
            'Industrials': -20,
            'Basic Materials': -15,
            'default': -15
        },
        marketImpact: -20
    },
    'tech_crash': {
        name: 'Estallido Burbuja IA / Tech',
        description: 'Corrección masiva en valoraciones tecnológicas excesivas.',
        factors: {
            'Technology': -35,
            'Consumer Cyclical': -10,
            'Communication Services': -20, // Google/Meta usually here
            'Real Estate': -5,
            'Financial Services': -5,
            'Energy': -2,
            'Healthcare': 0,
            'Utilities': 0,
            'Industrials': -5,
            'Basic Materials': -2,
            'default': -5
        },
        marketImpact: -12
    },
    'soft_landing': {
        name: 'Aterrizaje Suave (Soft Landing)',
        description: 'Economía se enfría sin recesión. Bajada de tipos gradual.',
        factors: {
            'Technology': 10,
            'Consumer Cyclical': 8,
            'Real Estate': 15, // Rates down = RE up
            'Financial Services': 5,
            'Energy': -5,
            'Healthcare': 5,
            'Utilities': 8,
            'Communication Services': 8,
            'Industrials': 5,
            'Basic Materials': 5,
            'default': 5
        },
        marketImpact: 8
    }
};

export async function generateRiskAnalysis(portfolioSummary: any, scenarioKey: string) {
    try {
        const scenario = SCENARIOS[scenarioKey];
        if (!scenario) throw new Error('Scenario not found');

        const analysis: any = {
            scenario: scenario.name,
            description: scenario.description,
            currentValue: portfolioSummary.totalValue,
            projectedValue: 0,
            projectedChange: 0,
            projectedChangePercent: 0,
            worstHit: null,
            bestPerformer: null,
            holdingsImpact: []
        };

        let projectedTotal = 0;

        // Simulate impact per holding
        for (const holding of portfolioSummary.holdings) {
            // In a real app, we would fetch the actual sector from FMP or DB if missing
            // For now we assume sector might be inferred or we use a fallback
            // We can try to guess sector or use 'default' if not available.
            // Since we don't have sector in 'holding' explicitly in the summary usually,
            // we might rely on the AI/Strategy analysis or just simple mapping if we had it.
            // For MVP, let's assume we can map some common ones or fallback to 'default' + Beta proxy?
            // Let's use a randomness factor to simulate Beta variance if we don't have sector.

            // BETTER: Use "Beta" logic if we don't have sector. 
            // If holding has high gain, it might be high beta. 
            // This is a simulation approximation.

            // Let's rely on a mock sector assignment for common tickers if needed, 
            // or just apply the 'marketImpact' * beta_estimate.

            // Fallback: Check if we have sector in holding (we added generic sector support earlier?)
            // If not, let's default to a "Market Sensitive" approach.

            const sector = holding.sector || 'default'; // Ensure portfolio.actions returns sector
            const impactFactor = scenario.factors[sector] || scenario.factors['default'];

            // Add some noise/variance based on stock specific volatility (mocked here)
            const volatilityNoise = (Math.random() * 4) - 2; // +/- 2% variance
            const finalImpactPercent = impactFactor + volatilityNoise;

            const projectedHoldingValue = holding.value * (1 + (finalImpactPercent / 100));
            projectedTotal += projectedHoldingValue;

            analysis.holdingsImpact.push({
                symbol: holding.symbol,
                current: holding.value,
                projected: projectedHoldingValue,
                changePercent: finalImpactPercent,
                change: projectedHoldingValue - holding.value
            });
        }

        analysis.projectedValue = projectedTotal;
        analysis.projectedChange = projectedTotal - analysis.currentValue;
        analysis.projectedChangePercent = (analysis.projectedChange / analysis.currentValue) * 100;

        // Find extremes
        analysis.holdingsImpact.sort((a: any, b: any) => a.changePercent - b.changePercent);
        analysis.worstHit = analysis.holdingsImpact[0];
        analysis.bestPerformer = analysis.holdingsImpact[analysis.holdingsImpact.length - 1];

        return analysis;

    } catch (error) {
        console.error("Error generating risk analysis:", error);
        return null;
    }
}
