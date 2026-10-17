import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
const source=readFileSync('components/brain/GlobalBrain.tsx','utf8');
test('mobile brain clears BottomNav and uses full flat icon without shell',()=>{
 assert.ok(source.includes('bottom-[calc(4.75rem+env(safe-area-inset-bottom))]'));
 assert.ok(source.includes('shadow-none bg-transparent hover:bg-transparent'));
 assert.ok(!source.split('if (!isOpen)')[1].split('// Panel:')[0].includes('bg-indigo-600'));
 assert.ok(source.includes('h-14 w-14 p-0'));
 assert.ok(source.includes('h-14 w-14 shrink-0 object-contain'));
 assert.ok(!source.split('if (!isOpen)')[1].split('// Panel:')[0].includes('bg-white'));
});
