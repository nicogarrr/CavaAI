/**
 * Guarda F146: el historial «Últimos disparos y entregas» de /alerts debe ser
 * trazable y accionable: hora del disparo visible y enlace a la investigación
 * cuando la alerta tiene ticker. Antes las tarjetas no mostraban hora ni
 * enlace pese a que la API ya entrega created_at y company_id.
 *
 * Ejecución: node --experimental-strip-types --test scripts/alerts-history-traceability-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');
const readSource = (rel: string) => readFileSync(join(root, rel), 'utf8');

describe('alerts history traceability guard (F146)', () => {
    it('la tarjeta de disparo muestra la hora del disparo', () => {
        const src = readSource('components/alerts/AlertsManager.tsx');
        assert.ok(
            src.includes('formatUserDateTime(item.triggeredAt)'),
            'el historial debe mostrar la hora del ultimo disparo (triggeredAt)',
        );
        assert.ok(
            !src.includes('formatUserDateTime(item.createdAt)'),
            'createdAt es la hora del PRIMER disparo (fila reutilizada por fingerprint): exhibirla como hora del disparo es falso',
        );
    });

    it('la tarjeta enlaza a la investigación cuando hay ticker', () => {
        const src = readSource('components/alerts/AlertsManager.tsx');
        assert.ok(
            src.includes('href={`/research/${item.ticker}`}'),
            'el historial debe enlazar a /research/[ticker] cuando la alerta tiene ticker',
        );
        assert.ok(src.includes('item.ticker &&'), 'el enlace solo se muestra con ticker presente (nunca inventado)');
    });

    it('la acción frontend propaga el ticker que entrega la API', () => {
        const src = readSource('lib/actions/alerts.actions.ts');
        assert.ok(src.includes('ticker: row.ticker ?? null'), 'alerts.actions.ts debe propagar ticker');
        assert.ok(
            src.includes('triggeredAt: row.last_triggered_at ?? row.created_at'),
            'triggeredAt debe salir de last_triggered_at (fallback created_at en filas antiguas)',
        );
    });

    it('la API incluye ticker en ResearchAlertOut', () => {
        const schema = readSource('data-engine/app/schemas/api.py');
        const route = readSource('data-engine/app/api/routes/alerts.py');
        assert.ok(schema.includes('ticker: str | None = None'), 'ResearchAlertOut debe exponer ticker');
        assert.ok(route.includes('out.ticker = tickers.get(alert.company_id)'), 'list_alerts debe resolver el ticker');
        assert.ok(schema.includes('last_triggered_at: datetime | None'), 'ResearchAlertOut debe exponer last_triggered_at');
        const model = readSource('data-engine/app/models/entities.py');
        assert.ok(model.includes('last_triggered_at'), 'ResearchAlert debe persistir last_triggered_at');
        const service = readSource('data-engine/app/services/review_alert_service.py');
        assert.ok(
            service.includes('existing.last_triggered_at = now'),
            'un re-disparo por fingerprint debe actualizar last_triggered_at',
        );
    });
});
