import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Metodología - CavaAI',
  description:
    'De dónde vienen los datos de CavaAI, qué cobertura tienen, cómo se genera una tesis y cuánto cuesta el servicio.',
};

export const dynamic = 'force-dynamic';

function Section({
  id,
  emoji,
  title,
  children,
}: {
  id: string;
  emoji: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="mb-8 scroll-mt-24">
      <h2 className="text-2xl font-semibold text-gray-100 mb-4">
        {emoji} {title}
      </h2>
      {children}
    </section>
  );
}

export default function MetodologiaPage() {
  return (
    <div className="container mx-auto px-4 py-12 max-w-4xl">
      <div className="mb-8">
        <p className="text-sm font-semibold uppercase text-teal-300">Transparencia</p>
        <h1 className="text-4xl font-bold text-gray-100 mb-4">Metodología</h1>
        <p className="text-gray-300 mb-4">
          Cómo funciona CavaAI por dentro: de dónde salen los datos, qué cubren (y qué no),
          cómo se construye una tesis de inversión y cuánto cuesta cada cosa.
        </p>
        <nav className="flex flex-wrap gap-2 text-sm">
          {[
            ['#fuentes', 'Fuentes de datos'],
            ['#cobertura', 'Cobertura y límites'],
            ['#tesis', 'Cómo se genera una tesis'],
            ['#riesgos', 'Riesgos y disclaimer'],
            ['#costes', 'Costes del servicio'],
          ].map(([href, label]) => (
            <Link
              key={href}
              href={`/metodologia${href}`}
              className="rounded-md border border-gray-700 bg-gray-800 px-3 py-1.5 text-gray-200 hover:border-teal-700 hover:text-teal-300"
            >
              {label}
            </Link>
          ))}
        </nav>
      </div>

      <div className="prose prose-lg max-w-none">
        <Section id="fuentes" emoji="📊" title="Fuentes de datos">
          <p className="text-gray-200 mb-4">
            CavaAI combina datos de mercado, documentos regulatorios e indicadores macro.
            Ninguna fuente es en tiempo real: todas llegan con retraso y pasan por una caché
            para no agotar los planes gratuitos.
          </p>
          <div className="overflow-x-auto rounded-lg border border-gray-700">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead>
                <tr className="bg-gray-800 text-xs uppercase text-gray-400">
                  <th className="px-4 py-3">Fuente</th>
                  <th className="px-4 py-3">Qué aporta</th>
                  <th className="px-4 py-3">Retraso / frescura</th>
                </tr>
              </thead>
              <tbody className="text-gray-200">
                <tr className="border-t border-gray-700">
                  <td className="px-4 py-3 font-semibold text-gray-100">Yahoo Finance</td>
                  <td className="px-4 py-3">
                    Índices y macro del screener (S&amp;P 500, Nasdaq, Bitcoin, oro, plata);
                    recurso de reserva para cotizaciones cuando Finnhub falla. Gratis, sin API key.
                  </td>
                  <td className="px-4 py-3">
                    Datos de sesión con retraso (minutos); no es tiempo real.
                  </td>
                </tr>
                <tr className="border-t border-gray-700">
                  <td className="px-4 py-3 font-semibold text-gray-100">Finnhub</td>
                  <td className="px-4 py-3">
                    Cotizaciones, market caps, perfiles de empresa y noticias del screener
                    y las fichas de acción. Plan gratuito con límite de peticiones.
                  </td>
                  <td className="px-4 py-3">
                    Precios y noticias con caché de ~60 segundos; perfiles hasta 24&nbsp;h.
                    El plan gratuito impone rate limits: ante picos puedes ver datos de hace un minuto
                    o un aviso de reintento.
                  </td>
                </tr>
                <tr className="border-t border-gray-700">
                  <td className="px-4 py-3 font-semibold text-gray-100">SEC EDGAR</td>
                  <td className="px-4 py-3">
                    Filings oficiales (10-K, 10-Q, 8-K): la base documental de las tesis.
                    Acceso público y gratuito.
                  </td>
                  <td className="px-4 py-3">
                    Se publican cuando la empresa los presenta (trimestral/anual);
                    siempre van por detrás del mercado.
                  </td>
                </tr>
                <tr className="border-t border-gray-700">
                  <td className="px-4 py-3 font-semibold text-gray-100">FRED</td>
                  <td className="px-4 py-3">
                    Indicadores macro (Reserva Federal, BCE): contexto para valoraciones y riesgo.
                    API gratuita.
                  </td>
                  <td className="px-4 py-3">
                    Frecuencia diaria o inferior según el indicador; es contexto estructural,
                    no señal intradía.
                  </td>
                </tr>
                <tr className="border-t border-gray-700">
                  <td className="px-4 py-3 font-semibold text-gray-100">LLM (OpenCode Go + Jev)</td>
                  <td className="px-4 py-3">
                    Solo genera texto de análisis: tesis, debate bull/bear y micro-decisiones.
                    Nunca inventa precios: los números vienen de las fuentes anteriores.
                  </td>
                  <td className="px-4 py-3">
                    Bajo demanda; tarda segundos o pocos minutos según el workflow.
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </Section>

        <Section id="cobertura" emoji="🔭" title="Cobertura y límites">
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
            <ul className="text-gray-200 space-y-3">
              <li>
                🌍 <strong>Universo del screener, limitado:</strong> el{' '}
                <Link href="/screener" className="text-teal-300 hover:text-teal-200">
                  screener
                </Link>{' '}
                muestra large caps líquidos por sector (p. ej. Technology, Energy), unas 25
                empresas por vista. No cubre small caps, ni todos los mercados, ni todas las bolsas.
              </li>
              <li>
                ⏱️ <strong>Sin tiempo real:</strong> los precios llevan caché de ~60 segundos y las
                fuentes gratuitas tienen retraso propio. No uses CavaAI para trading intradía
                ni para operar en apertura/cierre.
              </li>
              <li>
                📉 <strong>Disponibilidad:</strong> si el backend está arrancando o una API gratuita
                limita el ritmo, verás un aviso de reintento en lugar de datos. Reintenta en 30 segundos.
              </li>
              <li>
                🧾 <strong>Documentos:</strong> la cobertura de filings y transcripts depende de lo que
                cada empresa publique y de lo que hayas importado en{' '}
                <Link href="/research/sources" className="text-teal-300 hover:text-teal-200">
                  fuentes de research
                </Link>
                . Sin documentos, la tesis solo usa precios y macro.
              </li>
            </ul>
          </div>
        </Section>

        <Section id="tesis" emoji="🧠" title="Cómo se genera una tesis">
          <p className="text-gray-200 mb-4">
            Cada tesis sigue el mismo pipeline auditable en el{' '}
            <Link href="/research" className="text-teal-300 hover:text-teal-200">
              Research Desk
            </Link>
            :
          </p>
          <ol className="text-gray-200 space-y-3 list-decimal list-inside mb-4">
            <li>
              <strong>Recopilar evidencia:</strong> precios (Finnhub/Yahoo), filings (SEC EDGAR),
              macro (FRED) y documentos importados en{' '}
              <Link href="/research/sources" className="text-teal-300 hover:text-teal-200">
                Sources
              </Link>
              . Cada documento queda registrado con auditoría.
            </li>
            <li>
              <strong>Ejecutar el workflow:</strong> el backend Python corre el workflow de tesis
              (GenerateThesisWorkflow, visible en{' '}
              <Link href="/research/workflows" className="text-teal-300 hover:text-teal-200">
                Workflows
              </Link>
              ), que calcula una valoración determinista (escenarios bear/base/bull) a partir
              de los datos, sin inventar cifras.
            </li>
            <li>
              <strong>Debate bull/bear:</strong> el LLM argumenta a favor y en contra de la tesis
              con la evidencia anterior y emite un <strong>veredicto</strong> que queda guardado
              en la propia tesis.
            </li>
            <li>
              <strong>Versionado:</strong> cada cambio genera una nueva versión con su auditoría,
              así que puedes ver qué cambió, cuándo y con qué datos.
            </li>
          </ol>
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
            <p className="text-gray-200 text-sm">
              💡 Regla de oro: el LLM solo interpreta; los números siempre vienen de las fuentes
              de la sección anterior. Si una cifra no tiene fuente, la tesis la marca como
              pendiente, no la inventa.
            </p>
          </div>
        </Section>

        <Section id="riesgos" emoji="⚠️" title="Riesgos y disclaimer">
          <div className="bg-yellow-900 border border-yellow-700 rounded-lg p-6">
            <p className="text-yellow-200 font-medium mb-2">
              Esto no es asesoramiento financiero.
            </p>
            <div className="text-gray-200 space-y-3 text-sm">
              <p>
                CavaAI es una herramienta educativa y de análisis. Las tesis, valoraciones y
                veredictos son opiniones generadas a partir de datos públicos con retraso y
                modelos de lenguaje que pueden equivocarse o usar información incompleta.
              </p>
              <p>
                Invertir conlleva riesgo de pérdida, incluida la pérdida total. Haz tu propia
                diligencia, contrasta con fuentes primarias (filings en SEC EDGAR) y consulta
                a un asesor financiero autorizado antes de tomar decisiones.
              </p>
              <p>
                Al usar CavaAI aceptas los{' '}
                <Link href="/terms" className="text-blue-300 hover:text-blue-200">
                  Términos de Servicio
                </Link>
                , que incluyen el descargo de responsabilidad de inversión completo.
              </p>
            </div>
          </div>
        </Section>

        <Section id="costes" emoji="💰" title="Costes del servicio">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="bg-green-900/40 border border-green-800 rounded-lg p-6">
              <h3 className="text-lg font-semibold text-green-200 mb-3">✅ Gratis</h3>
              <ul className="text-gray-200 text-sm space-y-2">
                <li>Screener, fichas de acción, índices y macro (datos gratuitos).</li>
                <li>Importar documentos y consultar fuentes y auditorías.</li>
                <li>Valoraciones deterministas y screeners guardados (cálculo local).</li>
                <li>Yahoo Finance, SEC EDGAR y FRED no tienen coste por uso.</li>
              </ul>
            </div>
            <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
              <h3 className="text-lg font-semibold text-gray-100 mb-3">🤖 Gasta LLM</h3>
              <ul className="text-gray-200 text-sm space-y-2">
                <li>Generar o regenerar una tesis (modelo barato vía OpenCode Go).</li>
                <li>Debate bull/bear y veredicto de cada tesis.</li>
                <li>Micro-decisiones de Jev (clasificar, resumir, extraer señales).</li>
                <li>Se usan modelos económicos a propósito: pagas céntimos por análisis,
                  no por cada precio que consultas.</li>
              </ul>
            </div>
          </div>
        </Section>

        <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 text-center">
          <h3 className="text-xl font-semibold text-gray-100 mb-3">¿Lo ves claro?</h3>
          <p className="text-gray-200 mb-4 text-sm">
            Prueba el screener o abre el Research Desk con esta metodología en mente.
          </p>
          <div className="flex flex-wrap justify-center gap-3">
            <Link
              href="/screener"
              className="rounded-md bg-teal-600 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-500"
            >
              Ir al screener
            </Link>
            <Link
              href="/research"
              className="rounded-md border border-gray-600 px-4 py-2 text-sm font-semibold text-gray-200 hover:border-teal-600 hover:text-teal-300"
            >
              Ir a research
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
