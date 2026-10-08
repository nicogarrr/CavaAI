/** Síntesis editorial en español. No citas literales ni principios extraídos por IA. */
export type InvestorConcept = {
  slug: string;
  title: string;
  summary: string;
  body: string;
  application: string;
  risk: string;
  investors: string[];
  source: { title: string; url: string };
};

const BUFFETT_1996 = {
  title: "Berkshire Hathaway · Carta de 1996",
  url: "https://www.berkshirehathaway.com/letters/1996.html",
};
export const CONCEPTS: InvestorConcept[] = [
  {
    slug: "circulo-de-competencia",
    title: "Círculo de competencia",
    summary: "Entender un negocio importa más que seguir todos los negocios.",
    body: "Buffett distingue entre evaluar empresas seleccionadas y conocer todas las empresas. Lo importante es delimitar lo que entiendes, no ampliar el círculo a cualquier precio.",
    application:
      "Antes de valorar una empresa, identifica cómo gana dinero, qué sostiene su ventaja y qué podría cambiar ese negocio.",
    risk: "Conocer el producto no basta para entender sus costes, deuda o competencia.",
    investors: ["buffett"],
    source: BUFFETT_1996,
  },
  {
    slug: "ventaja-competitiva",
    title: "Ventaja competitiva duradera",
    summary:
      "Buscar una posición económica que pueda resistir el paso del tiempo.",
    body: "La carta de 1996 describe la preferencia de Berkshire por negocios cuya fortaleza competitiva pueda seguir existiendo muchos años después. El precio de compra sigue importando.",
    application:
      "Contrasta la ventaja con márgenes, retención de clientes, costes de cambio y capacidad de los rivales para replicarla.",
    risk: "Una empresa excelente puede ser una mala inversión si se paga demasiado. La ventaja también puede desaparecer.",
    investors: ["buffett"],
    source: BUFFETT_1996,
  },
  {
    slug: "paciencia",
    title: "Paciencia y seguimiento",
    summary:
      "Mantener un buen negocio no significa dejar de comprobar la tesis.",
    body: "Buffett compara mantener acciones con ser dueño de un negocio: comprar a un precio razonable y comprobar después si se conservan la calidad económica y la calidad de la dirección.",
    application:
      "Define las señales que invalidarían la tesis antes de comprar. Revisa el negocio, no solo las oscilaciones de su cotización.",
    risk: "La paciencia no justifica ignorar un deterioro permanente ni el riesgo de concentración.",
    investors: ["buffett"],
    source: BUFFETT_1996,
  },
  {
    slug: "opciones",
    title: "Opciones: calls y puts",
    summary: "Derechos para el comprador, obligaciones para el vendedor.",
    body: "Una call da al comprador el derecho a comprar el subyacente al precio de ejercicio; una put, el derecho a venderlo. El derecho tiene un vencimiento y cuesta una prima. El vendedor asume la obligación correspondiente cuando se ejerce.",
    application:
      "Compara el coste de la prima, el vencimiento, el precio de ejercicio y el tamaño real del contrato antes de abrir una posición.",
    risk: "El comprador puede perder toda la prima. Vender opciones puede exigir garantías y generar pérdidas superiores a la prima cobrada; una call vendida sin cobertura puede tener pérdidas ilimitadas.",
    investors: [],
    source: {
      title: "SEC · Introducción a las opciones",
      url: "https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-63",
    },
  },
];

export function conceptsForInvestor(slug: string) {
  return CONCEPTS.filter((concept) => concept.investors.includes(slug));
}
