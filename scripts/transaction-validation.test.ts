/**
 * Validación del formulario "Nueva Inversión": ningún submit falla en silencio.
 * Se ejecuta con: node --experimental-strip-types --test scripts/transaction-validation.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

// @ts-expect-error entorno de test con node --experimental-strip-types (import con extensión solo en runtime)
import { hasTransactionErrors, validateTransactionForm } from '../components/portfolio/transactionValidation.ts';

const NOW = new Date('2026-09-23T12:00:00');

const VALID = {
  symbol: 'AAPL',
  type: 'buy' as const,
  quantity: '10',
  price: '150',
  date: '2026-09-23',
};

describe('validateTransactionForm (F1: sin submits silenciosos)', () => {
  it('acepta un formulario completo válido', () => {
    assert.deepEqual(validateTransactionForm(VALID, NOW), {});
  });

  it('exige símbolo seleccionado', () => {
    const errors = validateTransactionForm({ ...VALID, symbol: '  ' }, NOW);
    assert.ok(errors.symbol, 'debe pedir seleccionar acción');
    assert.ok(hasTransactionErrors(errors));
  });

  it('rechaza cantidad vacía, cero o negativa', () => {
    for (const quantity of ['', '0', '-5', 'abc']) {
      const errors = validateTransactionForm({ ...VALID, quantity }, NOW);
      assert.ok(errors.quantity, `cantidad ${JSON.stringify(quantity)} debe fallar`);
    }
  });

  it('rechaza precio vacío o negativo', () => {
    for (const price of ['', '-1']) {
      const errors = validateTransactionForm({ ...VALID, price }, NOW);
      assert.ok(errors.price, `precio ${JSON.stringify(price)} debe fallar`);
    }
  });

  it('rechaza fecha inválida o futura', () => {
    assert.ok(validateTransactionForm({ ...VALID, date: '' }, NOW).date);
    assert.ok(validateTransactionForm({ ...VALID, date: '23/09/2026' }, NOW).date);
    assert.ok(validateTransactionForm({ ...VALID, date: '2026-09-24' }, NOW).date);
  });
});
