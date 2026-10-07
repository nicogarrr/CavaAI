/**
 * Fixture E2E determinista de la cabecera de cotización. SOLO se activa con
 * la combinación exacta APP_ENV=test + E2E_AUTH_BYPASS=1 + entorno no
 * producción + el ticker del escenario visual; cualquier otra combinación
 * sigue la ruta real de proveedores. La guarda cubre la tabla de verdad.
 */
import type { CompanyMarketSnapshot } from '@/lib/actions/market-workspace.actions';

export const E2E_MARKET_FIXTURE_TICKER = 'MSFT';

type FixtureEnv = { APP_ENV?: string; E2E_AUTH_BYPASS?: string; NODE_ENV?: string };

export function isE2EMarketFixtureEnabled(env: FixtureEnv, ticker: string): boolean {
    return (
        env.APP_ENV === 'test' &&
        env.E2E_AUTH_BYPASS === '1' &&
        env.NODE_ENV !== 'production' &&
        ticker === E2E_MARKET_FIXTURE_TICKER
    );
}

export function e2eMarketFixture(ticker: string): CompanyMarketSnapshot {
    const history = Array.from({ length: 40 }, (_, index) => ({
        date: new Date(Date.UTC(2026, 7, 1 + index)).toISOString().slice(0, 10),
        close: 300 + index * 0.9 + (index % 7),
        volume: null,
    }));
    return {
        ticker,
        name: ticker,
        exchange: null,
        currency: 'USD',
        quote: {
            price: 336.56,
            change: 2.34,
            changePercent: 0.7,
            open: 334.2,
            high: 337.1,
            low: 333.8,
            previousClose: null,
            metricsSource: 'Fixture local',
            metricsSession: '2026-09-09',
            priceAsOf: null, // cotización "en vivo" del fixture: sin rótulo de cierre
            priceKind: 'live' as const,
        },
        history,
        status: 'available',
    };
}
