"""Macro news lane: GDELT theme queries without ticker, labeled macro at creation.

Each query is specific (phrases, not bare generic terms) to keep noise out.
Themes approved by Nico 2026-09-27 (oro/bancos centrales, tipos, materias
primas, camiones/freight, IA, Ormuz/petróleo, energía, semiconductores,
dólar/divisas, inflación, liquidez M2, China/supply chains, política
comercial EEUU). Events land with company_id NULL (no ticker detection),
news_lane="macro" and macro_theme in metadata — they feed the macro feed
and the second-order analysis, never tracked-news alerts (fail-closed:
no company link, no alert).
"""

MACRO_NEWS_LANE = "macro"

# (theme_key, query GDELT DOC 2.0). Sintaxis: frases entre comillas,
# OR/AND en mayúsculas, espacio = AND implícito.
MACRO_GDELT_QUERIES: tuple[tuple[str, str], ...] = (
    (
        "gold_central_banks",
        '(gold OR oro) ("central bank" OR "banco central" OR "Federal Reserve" OR ECB OR BCE)',
    ),
    (
        "interest_rates",
        '("interest rates" OR "tipos de interes" OR "rate hike" OR "rate cut" OR "subida de tipos" OR "bajada de tipos") ("Federal Reserve" OR "ECB" OR "BCE" OR "banco central")',
    ),
    (
        "commodities",
        '("copper price" OR "precio del cobre" OR "lithium price" OR "precio del litio" OR "commodity prices" OR "precio de las materias primas")',
    ),
    (
        "trucking_freight",
        '(trucking OR "Cass Freight" OR "freight index" OR "transporte de mercancias" OR camiones) (economy OR economia OR recession OR recesion OR demand OR demanda)',
    ),
    (
        "ai_investment",
        '("artificial intelligence" OR "inteligencia artificial") ("AI capex" OR "data centers" OR "centros de datos" OR "AI spending" OR "inversion en IA")',
    ),
    (
        "hormuz_oil",
        '("Strait of Hormuz" OR "Estrecho de Ormuz" OR "oil price" OR "precio del petroleo" OR "crude oil" OR OPEC)',
    ),
    (
        "energy",
        '("natural gas" OR "gas natural" OR "electricity prices" OR "precio de la electricidad" OR "energy crisis" OR "crisis energetica")',
    ),
    (
        "semiconductors",
        '(semiconductors OR semiconductores OR "chip shortage" OR "escasez de chips" OR "chip export controls" OR "controles de exportacion de chips")',
    ),
    (
        "dollar_fx",
        '("dollar index" OR DXY OR "US dollar" OR "dolar estadounidense") ("currency markets" OR "mercado de divisas" OR euro OR yen OR yuan)',
    ),
    (
        "inflation",
        '(inflation OR inflacion OR CPI OR IPC OR "consumer prices" OR "precios al consumo") ("Federal Reserve" OR "ECB" OR "BCE" OR "banco central" OR eurozone OR "zona euro" OR "United States")',
    ),
    (
        "liquidity_m2",
        '("M2 money supply" OR "masa monetaria" OR "money supply" OR "oferta monetaria" OR "central bank liquidity" OR "liquidez bancaria" OR "quantitative easing" OR "quantitative tightening")',
    ),
    (
        "china_supply_chains",
        '(China OR "supply chain" OR "cadena de suministro") ("supply chains" OR "cadenas de suministro" OR exportaciones OR manufacturing OR manufactura OR tariffs OR aranceles)',
    ),
    (
        "us_trade_policy",
        '(Trump OR Bessent OR "TACO trade") (tariffs OR aranceles OR "trade deal" OR "acuerdo comercial" OR "trade war" OR "guerra comercial" OR "trade negotiations" OR "negociaciones comerciales")',
    ),
)


def iter_macro_queries() -> tuple[tuple[str, str], ...]:
    return MACRO_GDELT_QUERIES
