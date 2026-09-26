/**
 * Guarda de la API analytics legacy (F72): el backend retiró /analytics/*
 * intencionadamente (data-engine/tests/test_analytics_endpoints.py garantiza
 * el 404), así que el frontend no puede llamar a esa superficie ni montar
 * UI para funciones que solo existían ahí (pestaña Simulación Monte Carlo).
 * Ejecución: node --experimental-strip-types --test scripts/analytics-legacy-guard.test.ts
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, extname } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');

const walk = (dir: string): string[] =>
    readdirSync(dir).flatMap((name) => {
        const path = join(dir, name);
        if (statSync(path).isDirectory()) {
            return walk(path);
        }
        return ['.ts', '.tsx'].includes(extname(name)) ? [path] : [];
    });

const frontendFiles = ['app', 'components', 'lib'].flatMap((dir) => walk(join(root, dir)));

void test('ningún archivo del frontend llama a la superficie legacy /analytics/*', () => {
    const offenders = frontendFiles.filter((path) => readFileSync(path, 'utf8').includes('/analytics/'));
    assert.deepEqual(offenders.map((path) => path.slice(root.length + 1)), []);
});

void test('la pestaña Simulación (Monte Carlo retirado) no vuelve sin un endpoint real', () => {
    const offenders = frontendFiles.filter((path) => /montecarlo|PortfolioRiskSimulator|generateRiskAnalysis/i.test(readFileSync(path, 'utf8')));
    assert.deepEqual(offenders.map((path) => path.slice(root.length + 1)), []);
});
