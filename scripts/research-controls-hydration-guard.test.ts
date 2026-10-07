import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
for (const [path, disabled] of [
 ['components/ui/panel.tsx', /disabled=\{!hydrated\}/],
 ['components/research/QuickAlertButton.tsx', /disabled=\{busy \|\| !hydrated\}/],
] as const) test(`${path}: server control cannot accept a click before hydration`, () => {
 const src = readFileSync(path, 'utf8');
 assert.match(src, /useSyncExternalStore/);
 assert.match(src, disabled);
});
