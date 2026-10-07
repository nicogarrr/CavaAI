import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
const page=readFileSync("app/(root)/research/page.tsx","utf8");
const nav=readFileSync("components/layout/SectionNav.tsx","utf8");
test("research tools have one contextual navigation, not an obsolete sidebar footer",()=>{
 assert.doesNotMatch(page,/dentro del grupo Research|title="Herramientas de research"|const TOOLS =|title="Contexto de cartera"/);
 assert.match(nav,/\[.\/research\/workflows.,.Workflows.\]/);
});
