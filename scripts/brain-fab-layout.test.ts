import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
const source=readFileSync('components/brain/GlobalBrain.tsx','utf8');
test('mobile brain clears BottomNav and uses large flat icon in teal shell',()=>{
 assert.ok(source.includes('bottom-[calc(4.75rem+env(safe-area-inset-bottom))]'));
 assert.ok(source.includes('bg-teal-600 hover:bg-teal-500'));
 assert.ok(!source.split('if (!isOpen)')[1].split('// Panel:')[0].includes('bg-indigo-600'));
 assert.ok(source.includes('h-14 w-14 p-0'));
 assert.ok(source.includes('h-[50px] w-[50px]'));
 assert.ok(source.includes('h-[44px] w-[44px]'));
});
