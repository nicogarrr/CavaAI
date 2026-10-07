import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const content = readFileSync('components/proPicks/EnhancedProPicksContent.tsx', 'utf8');
const controls = readFileSync('components/proPicks/EnhancedProPicksFilters.tsx', 'utf8');

test('los resultados y el vacío describen solo los filtros aplicados', () => {
    assert.match(content, /setAppliedFilters\(requestedFilters\)/);
    assert.match(content, /generateEnhancedProPicksWithRun\(requestedFilters\)/);
    const presentation = content.slice(content.indexOf('    return ('));
    assert.doesNotMatch(presentation, /(?<!applied)filters\.(minScore|sortBy|sector)/);
    assert.match(presentation, /appliedFilters\.minScore/);
    assert.match(presentation, /appliedFilters\.sector/);
    const success = content.indexOf('setAppliedFilters(requestedFilters)');
    assert.ok(success > content.indexOf('await generateEnhancedProPicksWithRun(requestedFilters)'));
    assert.ok(success < content.indexOf('} catch {', content.indexOf('const loadPicks')));
});

test('cargas simultáneas y cambios durante una carga quedan bloqueados', () => {
    assert.match(content, /if \(requestInFlight\.current\) return;/);
    assert.match(content, /requestInFlight\.current = true;/);
    assert.match(content, /finally \{\s*requestInFlight\.current = false;/);
    assert.match(content, /disabled=\{loading\}/);
    assert.match(controls, /<fieldset disabled=\{disabled\}/);
    assert.equal((controls.match(/<Select disabled=\{disabled\}/g) ?? []).length, 2);
    assert.equal((controls.match(/disabled=\{disabled\}\s*value=\{\[filters\./g) ?? []).length, 2);
});
