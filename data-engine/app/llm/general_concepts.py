"""Reviewed local glossary. No model output, provider call or private context."""
from __future__ import annotations

import re
import unicodedata

# Public definitions, not current market data or personalized recommendations.
DEFINITIONS: dict[str, str] = {
    "PER": "El PER relaciona el precio de una acción con el beneficio por acción: PER = precio por acción / beneficio por acción. Indica cuánto precio corresponde a cada unidad de beneficio. Con beneficios negativos o muy pequeños pierde utilidad. No incorpora por sí solo deuda, crecimiento ni calidad del beneficio; un PER bajo no demuestra que una acción esté barata.",
    "EBITDA": "El EBITDA es el resultado antes de intereses, impuestos, depreciaciones y amortizaciones. Ayuda a comparar resultados operativos, pero no equivale al flujo de caja: no descuenta inversiones, cambios en el capital circulante ni pagos de deuda. Los ajustes del EBITDA ajustado pueden variar entre empresas y deben comprobarse en su definición.",
    "ETF": "Un ETF es un fondo cuyas participaciones cotizan en bolsa. Puede seguir un índice o una estrategia propia. Su exposición depende de lo que contiene, no de la etiqueta ETF. Tiene costes y riesgos; algunos usan derivados o apalancamiento. El precio de negociación puede diferir de su valor liquidativo.",
    "dividendo": "Un dividendo es una distribución a los accionistas, normalmente en efectivo, acordada por la empresa. No está garantizado y puede reducirse o suspenderse. La rentabilidad por dividendo relaciona el dividendo por acción con su precio, pero no mide por sí sola la rentabilidad total ni la sostenibilidad de los pagos.",
    "deuda": "La deuda es financiación que debe devolverse según unas condiciones, habitualmente con intereses. Para entenderla importan importe, vencimientos, tipo de interés, garantías y capacidad de generar caja. La deuda bruta no descuenta el efectivo; la deuda neta sí lo hace según la definición utilizada. No todo pasivo contable es deuda financiera.",
    "ingresos": "Los ingresos son los importes reconocidos por la actividad de una empresa durante un periodo según sus normas contables. No son beneficio: todavía deben descontarse costes y otros gastos. Tampoco equivalen necesariamente a cobros, porque el reconocimiento del ingreso y la entrada de efectivo pueden ocurrir en momentos distintos.",
    "beneficio": "El beneficio es el resultado de restar los gastos a los ingresos del periodo según el nivel considerado. Beneficio bruto, operativo y neto descuentan partidas diferentes. Un beneficio contable no equivale necesariamente a efectivo disponible y puede incluir partidas extraordinarias o sin movimiento de caja.",
    "margen": "Un margen expresa un resultado como proporción de los ingresos: margen = resultado / ingresos. El margen bruto, operativo y neto usan resultados distintos. Compararlo exige mantener la misma definición, periodo y actividad. Un margen alto por sí solo no demuestra crecimiento, rentabilidad sobre el capital ni generación de caja.",
    "inflación": "La inflación es el aumento del nivel general de precios durante un periodo, medido mediante un índice de una cesta de bienes y servicios. Reduce el poder adquisitivo del dinero cuando los ingresos no aumentan al mismo ritmo. El índice agregado puede diferir de la experiencia de una persona. Desinflación significa que los precios crecen más despacio, no necesariamente que bajen.",
    "interés compuesto": "El interés compuesto acumula rendimientos sobre el capital inicial y sobre rendimientos anteriores que permanecen invertidos. Con una tasa constante por periodo, el capital final es capital inicial multiplicado por (1 + tasa) elevado al número de periodos. Es un modelo simplificado: tasas variables, costes, impuestos y pérdidas cambian el resultado real.",
    "diversificación": "La diversificación reparte exposición entre activos, emisores o factores de riesgo distintos. Puede reducir el riesgo concentrado, pero no elimina las pérdidas ni todos los riesgos del mercado. Tener muchos activos no basta si responden de forma parecida. Sus correlaciones pueden cambiar, especialmente durante periodos de tensión.",
    "precio de mercado": "El precio de mercado es el precio al que un activo se negocia en un momento dado. Depende de las órdenes y condiciones del mercado. No es necesariamente su valor económico estimado ni el importe al que podría negociarse una posición grande. Liquidez, diferencial entre oferta y demanda y momento de ejecución influyen.",
    "capitalización bursátil": "La capitalización bursátil es el precio por acción multiplicado por las acciones en circulación. Mide el valor de mercado del capital de los accionistas, no el valor de toda la empresa incluyendo deuda. Puede cambiar por el precio y por emisiones o recompras de acciones. La cifra depende del momento y del recuento usado.",
    "BPA": "El beneficio por acción (BPA) divide el beneficio atribuible a los accionistas ordinarios entre el número medio ponderado de acciones del periodo. El BPA diluido incorpora instrumentos potencialmente dilutivos cuando procede. No equivale a efectivo por acción. Recompras, emisiones y partidas extraordinarias pueden afectar a su evolución.",
    "flujo de caja libre": "El flujo de caja libre suele calcularse como flujo de caja operativo menos inversiones de capital, aunque no tiene una única definición universal. Conviene distinguir el flujo disponible para toda la empresa del disponible para accionistas. Puede diferir mucho del beneficio contable por inversiones, capital circulante y partidas sin salida de efectivo.",
    "ROE": "El ROE relaciona el beneficio neto atribuible a los accionistas con sus fondos propios, a menudo medios del periodo. Mide rentabilidad contable sobre ese capital. La deuda, las recompras y unos fondos propios reducidos pueden elevarlo sin mejorar el negocio. Con patrimonio negativo su interpretación es especialmente problemática.",
    "ROIC": "El ROIC relaciona el resultado operativo después de impuestos con el capital invertido en la actividad. Busca medir la rentabilidad del capital empleado. Su cálculo varía según los ajustes del resultado y la definición de capital invertido, por lo que las comparaciones exigen criterios consistentes.",
    "valor de empresa": "El valor de empresa suele partir de la capitalización bursátil, añadir deuda financiera y otras reclamaciones sobre el negocio y restar efectivo. Los ajustes por arrendamientos, minoritarios y otros activos pueden variar. No es lo mismo que el valor de mercado de las acciones ni una valoración intrínseca demostrada.",
    "balance": "El balance muestra activos, pasivos y patrimonio neto en una fecha. Su identidad básica es activo = pasivo + patrimonio neto. Es una fotografía contable, no una medida directa del valor de mercado ni un registro de todos los cobros y pagos. Las notas explican criterios y partidas que el resumen puede ocultar.",
    "flujo de caja": "El flujo de caja describe entradas y salidas de efectivo durante un periodo. El estado de flujos las agrupa en actividades operativas, de inversión y de financiación. Una entrada de efectivo puede proceder de nueva deuda y no de beneficios; por eso el cambio total de caja no mide por sí solo el desempeño del negocio.",
    "bono": "Un bono es un instrumento de deuda con condiciones de intereses y devolución. Su precio puede variar por tipos de interés, riesgo de crédito y liquidez. Cupón y rentabilidad no son lo mismo: la rentabilidad depende también del precio y de los pagos que finalmente se reciban. Mantenerlo hasta vencimiento no elimina el riesgo de impago.",
    "acción": "Una acción representa una participación en el capital de una empresa, con derechos que dependen de su clase y de las normas aplicables. Su precio y sus dividendos pueden variar. En una liquidación los accionistas cobran después de los acreedores, por lo que pueden perder toda su aportación.",
    "índice bursátil": "Un índice bursátil resume la evolución de una cesta de valores mediante unas reglas de selección y ponderación. No todos ponderan por capitalización ni reinvierten dividendos. Un índice de precios y otro de rentabilidad total pueden mostrar resultados distintos. El índice es una medida; los productos que lo siguen tienen costes y posibles diferencias de seguimiento.",
    "tipo de interés": "El tipo de interés expresa el coste o rendimiento del dinero por periodo respecto al capital. Para compararlo importan periodicidad, capitalización y comisiones. El tipo nominal no siempre coincide con la tasa anual efectiva. El tipo real considera el efecto de la inflación, con resultados distintos según la medida utilizada.",
    "deuda neta": "La deuda neta suele ser deuda financiera menos efectivo y equivalentes disponibles. No existe una definición única: pueden variar el tratamiento de arrendamientos, inversiones líquidas y efectivo restringido. Una cifra negativa indica más caja que la deuda incluida en ese cálculo, pero no prueba por sí sola ausencia de otros compromisos.",
    "activo": "Un activo contable es un recurso económico controlado por una entidad como resultado de hechos pasados. Puede ser efectivo, una cuenta a cobrar, un inmueble o un derecho intangible, entre otros. Su importe contable no tiene por qué coincidir con su valor de mercado ni con el efectivo recuperable.",
    "pasivo": "Un pasivo es una obligación presente de transferir un recurso económico derivada de hechos pasados. Incluye, entre otras partidas, deudas, cuentas a pagar y determinadas provisiones. No todos los pasivos tienen intereses ni el mismo plazo. Importe, vencimientos y condiciones ayudan a interpretar la obligación.",
    "patrimonio neto": "El patrimonio neto es la diferencia contable entre activos y pasivos. Incluye aportaciones de los propietarios y resultados acumulados, entre otras partidas. No equivale a capitalización bursátil ni al importe que recibirían necesariamente los accionistas si se liquidara la empresa.",
    "amortización": "En contabilidad, la amortización distribuye el coste de ciertos activos a lo largo de su vida útil; según el contexto puede distinguirse de la depreciación de activos materiales. No representa necesariamente una salida de caja en ese periodo. En deuda, amortizar significa devolver principal, que es un uso distinto del término.",
    "rentabilidad": "La rentabilidad relaciona el resultado obtenido con el capital o precio inicial durante un periodo. En un activo, la rentabilidad total incluye cambios de precio y distribuciones recibidas, con ajustes cuando procede. Compararla exige el mismo plazo y criterio de costes e impuestos. Una rentabilidad pasada no garantiza resultados futuros.",
    "volatilidad": "La volatilidad mide la variación de una serie de rendimientos durante un periodo y suele expresarse con una desviación típica. Depende de la frecuencia y ventana elegidas. Describe fluctuaciones, no todas las formas de riesgo: no mide por sí sola impago, liquidez o pérdida permanente.",
    "liquidez": "La liquidez puede referirse a la capacidad de negociar un activo con rapidez y sin alterar mucho su precio, o a la capacidad de una entidad para afrontar pagos próximos. Son sentidos distintos. Un activo cotizado no siempre es líquido y una empresa rentable puede tener dificultades de caja.",
    "apalancamiento": "El apalancamiento amplía una exposición mediante deuda, derivados u otros compromisos. Puede aumentar tanto ganancias como pérdidas respecto al capital propio. Sus riesgos dependen de garantías, vencimientos y condiciones de financiación. No se limita a la deuda que aparece de forma evidente en el balance.",
    "dilución": "La dilución es la reducción de la participación relativa o de ciertas magnitudes por acción al aumentar las acciones o los derechos que pueden convertirse en ellas. Su efecto económico depende del precio y del uso de los recursos obtenidos. No toda emisión destruye valor, aunque sí puede cambiar el reparto de propiedad.",
    "valor contable": "El valor contable es el importe registrado de un activo, pasivo o patrimonio según las normas contables. Para acciones suele usarse el patrimonio atribuible por acción. No es una estimación automática del valor de mercado o de liquidación. Activos no reconocidos, deterioros y criterios contables pueden afectar a la comparación.",
}


def _normalize(text: str) -> str:
    value = "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", value).strip()


_ALIASES = {_normalize(k): k for k in DEFINITIONS}
_ALIASES.update({
    "dividendos": "dividendo", "revenue": "ingresos", "beneficios": "beneficio",
    "margenes": "margen", "eps": "BPA", "beneficio por accion": "BPA",
    "fcf": "flujo de caja libre", "cash flow": "flujo de caja", "cash flow libre": "flujo de caja libre",
    "enterprise value": "valor de empresa", "equity": "patrimonio neto", "acciones": "acción",
    "bonos": "bono", "etfs": "ETF", "depreciacion": "amortización",
})
_PREFIX = r"(?:que es|que son|que significa|como funciona|como se calcula|explica|explicame|define|what is|how does) "


def canonical_concept(question: str) -> str | None:
    # Only exact public-concept questions. Extra text stays on the original route.
    value = re.sub(r"^[¿¡\s]+|[?!.\s]+$", "", _normalize(question))
    match = re.fullmatch(_PREFIX + r"(?:(?:el|la|los|las|un|una|the|an|a) )?(.+?)(?: work)?", value)
    return _ALIASES.get(match.group(1)) if match else None


def local_definition(question: str) -> str | None:
    concept = canonical_concept(question)
    return DEFINITIONS.get(concept) if concept else None
