import {
  E2E_ENABLED,
  E2E_SKIP_REASON,
  expect,
  jsonResponse,
  test,
  uniqueMarker,
} from "./fixtures/research-api";

type AlertRule = {
  id: number;
  company_id: number;
  name: string;
  rule_type: string;
  condition: { operator: string; value: number | string };
  active: boolean;
};

type EvaluateResponse = {
  status: string;
  evaluated: number;
};

test.skip(!E2E_ENABLED, E2E_SKIP_REASON);

test("alert rule create -> read -> evaluate -> deactivate", async ({
  request,
}) => {
  const marker = uniqueMarker("e2e-alert");
  // Valor distintivo por ejecucion: la creacion es idempotente por nombre,
  // asi cada run crea su propia regla y la limpieza no toca otras.
  const target = 5000 + (Date.now() % 100000) / 100;

  const created = await jsonResponse<AlertRule>(
    await request.post("/api/alerts", {
      data: {
        ticker: "MSFT",
        alert_type: "price_above",
        operator: ">",
        value: target,
      },
    }),
    201,
  );
  expect(created.active).toBe(true);
  expect(created.rule_type).toBe("price_above");
  expect(created.condition).toMatchObject({ operator: ">", value: target });

  try {
    const rules = await jsonResponse<AlertRule[]>(
      await request.get("/api/alerts/rules", {
        params: { ticker: "MSFT" },
      }),
    );
    expect(rules).toContainEqual(expect.objectContaining({ id: created.id }));

    const evaluated = await jsonResponse<EvaluateResponse>(
      await request.post("/api/alerts/rules/evaluate"),
    );
    expect(evaluated.status).toBe("ok");
    expect(evaluated.evaluated).toBeGreaterThanOrEqual(1);

    // Frontera honesta: actuar/despachar un id inexistente es 404, no 500.
    await jsonResponse(
      await request.post("/api/alerts/999999999/action", {
        data: { action: "acknowledge", actor: marker },
      }),
      404,
    );
    await jsonResponse(
      await request.post("/api/alerts/999999999/dispatch"),
      404,
    );
  } finally {
    // Limpieza: desactivar la regla creada por este run.
    const deactivated = await jsonResponse<AlertRule>(
      await request.delete(`/api/alerts/rules/${created.id}`),
    );
    expect(deactivated.active).toBe(false);
  }

  const stillActive = await jsonResponse<AlertRule[]>(
    await request.get("/api/alerts/rules", {
      params: { ticker: "MSFT", active: "true" },
    }),
  );
  expect(stillActive.find((rule) => rule.id === created.id)).toBeUndefined();
});
