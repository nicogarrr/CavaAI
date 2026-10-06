/** Canales de inversion: cada canal con URL https de YouTube, fuente y fecha; sin avatares copiados. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

// @ts-expect-error TS5097: explicit extension for node strip-types.
import { INVESTOR_CHANNELS } from '../app/(root)/inversores/canales/channels.ts';

const page = readFileSync('app/(root)/inversores/canales/page.tsx', 'utf8');
const list = readFileSync('app/(root)/inversores/page.tsx', 'utf8');

test('cada canal lleva URL de YouTube, fuente y fecha', () => {
    assert.ok(INVESTOR_CHANNELS.length >= 25);
    for (const channel of INVESTOR_CHANNELS) {
        assert.match(channel.url, /^https:\/\/www\.youtube\.com\/@[A-Za-z0-9._-]+$/, channel.name);
        assert.equal(channel.url, `https://www.youtube.com/${channel.handle}`);
        assert.ok(channel.source.length > 0 && channel.checked_at === '2026-10-06', channel.name);
    }
});

test('sin duplicados y las trampas de handle quedan fuera', () => {
    const urls = INVESTOR_CHANNELS.map((c: { url: string }) => c.url);
    assert.equal(new Set(urls).size, urls.length);
    for (const bad of ['@business', '@BloombergTelevision', '@AswathDamodaran']) {
        assert.ok(!urls.some((u: string) => u.endsWith(bad)), bad);
    }
});

test('las empresas van aparte y la pagina no copia avatares', () => {
    assert.ok(INVESTOR_CHANNELS.filter((c: { category: string }) => c.category === 'empresa').length === 5);
    assert.ok(!/<img|Image\b/.test(page));
});

test('el listado enlaza a los canales', () => {
    assert.match(list, /href="\/inversores\/canales"/);
});

test('los canales generalistas van en negocio, no en inversion', () => {
    const byName = new Map(INVESTOR_CHANNELS.map((c: { name: string; category: string }) => [c.name, c.category]));
    assert.equal(byName.get('The Diary Of A CEO'), 'negocio');
    assert.equal(byName.get("Sourcery with Molly O'Shea"), 'negocio');
    assert.match(page, /category: 'negocio'/);
});
