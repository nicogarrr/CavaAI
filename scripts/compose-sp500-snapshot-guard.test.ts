import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const compose = readFileSync('docker-compose.prod.yml', 'utf8');
const backend = compose.slice(compose.indexOf('\n  backend:'), compose.indexOf('\n  worker:'));

test('el backend de prod monta el snapshot del factsheet S&P 500 en solo lectura (#726)', () => {
  assert.match(backend, /SP500_FACTSHEET_SNAPSHOT_DIR=\$\{SP500_FACTSHEET_SNAPSHOT_DIR:-\/data\/sp500-factsheet-snapshots\}/);
  assert.match(backend, /\.\/data-sp500-factsheet-snapshots:\/data\/sp500-factsheet-snapshots:ro/);
});
