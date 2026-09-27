/** Cache compartida del buscador: una rafaga, reintento tras fallo/cierre. */
import assert from "node:assert/strict";
import test from "node:test";

// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
const { _resetPopularStocksForTests, loadPopularStocks } = await import("../lib/popular-stocks-loader.ts");

test("aperturas concurrentes comparten UNA llamada al fetcher", async () => {
    _resetPopularStocksForTests();
    let calls = 0;
    const fetcher = async () => {
        calls += 1;
        await new Promise((resolve) => setTimeout(resolve, 20));
        return { status: "ok" as const, stocks: [{ symbol: "AAPL" } as never] };
    };
    const [a, b, c] = await Promise.all([
        loadPopularStocks(fetcher),
        loadPopularStocks(fetcher),
        loadPopularStocks(fetcher),
    ]);
    assert.equal(calls, 1);
    assert.equal(a.length, 1);
    assert.equal(b, a); // misma referencia cacheada
    assert.equal(c, a);
});

test("exito cacheado: las aperturas siguientes no refetchean", async () => {
    _resetPopularStocksForTests();
    let calls = 0;
    const fetcher = async () => {
        calls += 1;
        return { status: "ok" as const, stocks: [] };
    };
    await loadPopularStocks(fetcher);
    await loadPopularStocks(fetcher); // reabrir: cache, sin fetch
    await loadPopularStocks(fetcher);
    assert.equal(calls, 1);
});

test("abrir-cerrar-reabrir tras FALLO reintenta (no queda muerto)", async () => {
    _resetPopularStocksForTests();
    let calls = 0;
    const fetcher = async () => {
        calls += 1;
        if (calls === 1) throw new Error("red caida");
        return { status: "ok" as const, stocks: [] };
    };
    await assert.rejects(loadPopularStocks(fetcher), /red caida/);
    // Reabrir: la promesa fallida se descarto -> reintento real.
    const results = await loadPopularStocks(fetcher);
    assert.equal(calls, 2);
    assert.deepEqual(results, []);
});

test("un fallo no envenena a los listeners concurrentes mas alla del rechazo", async () => {
    _resetPopularStocksForTests();
    let calls = 0;
    const fetcher = async () => {
        calls += 1;
        throw new Error("boom");
    };
    await assert.rejects(loadPopularStocks(fetcher));
    await assert.rejects(loadPopularStocks(fetcher));
    assert.equal(calls, 2); // cada apertura reintenta; nada cacheado
});

test("fallo de proveedor (status error) NO se cachea y reintenta", async () => {
    _resetPopularStocksForTests();
    let calls = 0;
    const fetcher = async () => {
        calls += 1;
        // Proveedor caido con clave configurada: la action devuelve error.
        if (calls === 1) return { status: "error" as const };
        return { status: "ok" as const, stocks: [{ symbol: "MSFT" } as never] };
    };
    await assert.rejects(loadPopularStocks(fetcher), /popular_stocks_fetch_failed/);
    const results = await loadPopularStocks(fetcher);
    assert.equal(calls, 2);
    assert.equal(results[0].symbol, "MSFT");
});
