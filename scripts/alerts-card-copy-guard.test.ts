import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
// @ts-expect-error TS5097: explicit extension for node strip-types.
import { alertCardCopy } from '../lib/alerts/card-copy.ts';

const base = {
  id: 1, title: 'Review required: news material update',
  message: 'Material news requires thesis review. No structural thesis node matched with sufficient confidence.',
  severity: 'high', status: 'open', alert_type: 'news_material_update', channels: [], deliveries: {},
  ticker: 'V', companyName: 'Visa', triggeredAt: null, sourceUrl: 'https://www.sec.gov/x',
  createdAt: '2026-09-28T10:00:00Z', eventDate: '2025-10-28T12:00:00Z',
  eventDateSource: 'source', eventForm: '8-K',
};

test('filing card uses only source-backed fields; keeps original machine trace behind detail', () => {
  const card = alertCardCopy(base);
  assert.match(card.heading, /Visa · 8-K · 28 oct 2025/);
  assert.match(card.summary, /Documento 8-K asociado a Visa/);
  assert.doesNotMatch(card.summary, /No structural thesis|21846000000/);
  assert.match(card.technical, /No structural thesis node/);
});

test('unknown form/date are not guessed from machine prose or alert created_at', () => {
  const card = alertCardCopy({ ...base, eventDate: null, eventForm: null });
  assert.equal(card.heading, 'Visa · Noticia material');
  assert.doesNotMatch(card.summary, /8-K|2025/);
});

test('source and detail controls exist on both surfaces', () => {
  for (const path of ['components/PersonalizedOverview.tsx', 'components/alerts/AlertsManager.tsx']) {
    const view = readFileSync(path, 'utf8');
    assert.match(view, /alertCardCopy\(item\)/);
    assert.match(view, /Detalle técnico/);
    assert.match(view, /item.sourceUrl/);
  }
});
