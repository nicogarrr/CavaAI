/**
 * Inputs inferidos: valores formateados, nunca decimales largos ni claves crudas.
 * Ejecución: node --experimental-strip-types --test scripts/provenance-format-guard.test.ts
 */
import { describe, it } from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { capitalizeLabel, formatProvenanceValue } from "../lib/research/provenance-format.ts"

describe("formatProvenanceValue", () => {
    it("porcentajes con coma y un decimal", () => {
        assert.match(formatProvenanceValue("penetration", 0.1442999), /^14,4\s?%$/)
        assert.match(formatProvenanceValue("fcf_margin", 25), /^25,0\s?%$/)
    })
    it("dinero en dólares estilo inglés", () => {
        assert.equal(formatProvenanceValue("total_debt", 4869930000), "$4.87B")
        assert.equal(formatProvenanceValue("monthly_arpu", 14.4), "$14.40")
    })
    it("cantidades sin decimales largos", () => {
        const out = formatProvenanceValue("satellites", 45.123456789)
        assert.ok(!/\d{3,}$/.test(out.split(",")[1] ?? ""), out)
    })
    it("sin dato es N/D", () => {
        assert.equal(formatProvenanceValue("penetration", null), "N/D")
    })
    it("capitalizeLabel", () => {
        assert.equal(capitalizeLabel("suscriptores direccionables"), "Suscriptores direccionables")
    })
})

describe("ThesisMemo", () => {
    const src = readFileSync("components/research/ThesisMemo.tsx", "utf8")
    it("pinta la etiqueta en español, no item.key crudo", () => {
        assert.match(src, /metricLabel\(item\.key\)/)
        assert.doesNotMatch(src, />\{item\.key\}</)
    })
    it("usa formatProvenanceValue", () => {
        assert.match(src, /formatProvenanceValue\(/)
    })
})
