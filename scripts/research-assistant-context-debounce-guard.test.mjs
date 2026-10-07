import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
const ui = readFileSync('components/research/ResearchAssistant.tsx', 'utf8');
test('contexto de guía espera al ticker completo y cancela consultas obsoletas', () => {
    const effect = ui.slice(ui.indexOf('  useEffect('), ui.indexOf('  async function submit'));
    assert.match(effect, /if \(mode !== 'guide' \|\| !value\) return;/);
    assert.match(effect, /const timer = setTimeout\(\(\) => \{\s*getGuideContextAction\(value\)/);
    assert.match(effect, /\}, 350\)/);
    assert.match(effect, /live = false; clearTimeout\(timer\)/);
    assert.match(effect, /if \(live\) setContext\(data\)/);
    assert.match(effect, /if \(live\) setContextError\(true\)/);
    assert.match(effect, /\[mode, ticker\]/);
});
