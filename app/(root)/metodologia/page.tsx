import Link from 'next/link';
import {
  BookOpen,
  Calculator,
  Database,
  FlaskConical,
  LineChart,
  Scale,
  Search,
  ShieldAlert,
  Sparkles,
  Target,
  TriangleAlert,
  Users,
  Wallet,
} from 'lucide-react';

import { GlossaryTerm } from '@/components/GlossaryTerm';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

export const dynamic = 'force-dynamic';
export const revalidate = 3600;

const sources = [
  {
    icon: Database,
    title: 'Finnhub',
    text: 'Precios (quotes), perfiles de compañía (profile2) y búsqueda de símbolos, incluidos tickers poco comunes. Capa gratuita con API key: es la fuente principal de nombres y cotizaciones.',
    href: '/research',
    cta: 'Ver research',
  },
  {
    icon: LineChart,
    title: 'Yahoo Finance · chart API',
    text: 'Índices y futuros reales: S&P 500 (^GSPC), Nasdaq (^IXIC), Bitcoin (BTC-USD), oro (GC=F) y plata (SI=F). Sin API key y con caché de 60 s. Nunca un ETF etiquetado como índice.',
    href: '/',
    cta: 'Ver índices en la home',
  },
  {
    icon: Users,
    title: 'SEC EDGAR',
    text: 'Filings 10-K/10-Q y Form 4 (operaciones de insiders) directamente del regulador de EE. UU. Acceso público y gratuito: la fuente primaria de documentos.',
    href: '/insider',
    cta: 'Ver señales insider',
  },
];

const engines = [
  {
    title: 'Standard DCF (por defecto)',
    text: (
      <>
        DCF FCFF a 5 años sobre ingresos y margen FCF del último snapshot coherente: si falta el margen se deriva
        como FCF/ingresos (acotado a 1%-50%) y el crecimiento sale de los hechos o de un valor por defecto (acotado
        a -15%/+45%). El <GlossaryTerm k="wacc" icon={false}>WACC</GlossaryTerm> y el crecimiento terminal usan un
        valor por defecto etiquetado como tal; la deuda neta del snapshot resta al equity (la caja neta suma).
        Escenarios bear/base/bull, sensibilidad 3x3 crecimiento x WACC y{' '}
        <GlossaryTerm k="reverse_dcf" icon={false}>reverse DCF</GlossaryTerm> incluidos.
      </>
    ),
  },
  {
    title: 'Pre-revenue / especulativo (pre-FCF)',
    text: 'DCF a 5 años para empresas sin caja libre: ingresos mínimos de 1,0 (para que ~0 no rompa la matemática), margen 1%-40%, crecimiento por defecto del 20% (acotado a -15%/+60%) y WACC del 13% por defecto. Escenarios causales (retraso de ejecución o estrés de financiación, base, monetización acelerada) con dilución extra en el bear (>=15%, tope del 80% del valor) y funding gap estimado a 2 años con buffer del 50%.',
  },
  {
    title: 'Commodities (minería, energía, uranio)',
    text: 'Flujo = max(precio - coste unitario, 0) x volumen x (1 - tasa), y equity = flujo x múltiplo - deuda neta, todo desde hechos financieros (precio realizado o spot, coste, volumen, múltiplo). Los escenarios son el grid de precios x0,75 / x1,0 / x1,25 sobre el precio de referencia, y esa misma tabla es la sensibilidad.',
  },
  {
    title: 'SOTP (multi-segmento)',
    text: 'NAV = suma de (métrica operativa del segmento x múltiplo del segmento) - deuda neta, con contrato explícito de hechos por segmento y descuento holding entre 0 y 1. Escenarios: descuento +15pp (techo 45%) / base / -8pp con NAV x1,12 en el bull; sensibilidad del descuento -5pp / base / +5pp. Nunca cae a un DCF de firma única.',
  },
  {
    title: 'Holding company (tipo BN/BABA)',
    text: 'Para holdings: hereda el SOTP con descuento holding explícito que recoge el conglomerate discount persistente del grupo. Mismos escenarios y misma sensibilidad del descuento que el SOTP.',
  },
];

const steps = [
  {
    title: 'Más de 100 métricas por acción',
    text: 'Valor, crecimiento, rentabilidad, flujo de caja, momentum y salud de balance, normalizadas por sector.',
  },
  {
    title: 'Comparación contra el sector',
    text: 'Cada pick se mide contra sus pares antes de puntuar: lo que es barato en un sector puede ser caro en otro.',
  },
  {
    title: 'Score + confianza verificable',
    text: 'Score 0-100 con nivel de confianza y motivos auditables: cada motivo muestra su métrica y su valor.',
  },
  {
    title: 'Backtest por estrategia',
    text: 'El desempeño simulado se calcula con datos históricos y se compara contra el S&P 500 (alpha explícito).',
  },
];

const limits = [
  {
    icon: TriangleAlert,
    title: 'Datos con retraso',
    text: 'Los datos de mercado llegan con ligero retraso en la mayoría de mercados. Suficiente para análisis, no para trading intradía.',
  },
  {
    icon: ShieldAlert,
    title: 'Cobertura parcial',
    text: 'No todos los tickers tienen la misma cobertura: si faltan filings o métricas, la ficha lo indica en lugar de inventar.',
  },
  {
    icon: Scale,
    title: 'Point-in-time',
    text: (
      <>
        Los motores de valoración solo usan información disponible en cada fecha simulada: sin mirar al futuro.
        Evitar el <GlossaryTerm k="look_ahead" icon={false}>look-ahead</GlossaryTerm> es lo que hace que un backtest
        sea creíble.
      </>
    ),
  },
  {
    icon: Target,
    title: 'No es asesoramiento',
    text: 'CavaAI es una herramienta educativa y de análisis. Las decisiones de inversión son siempre tuyas.',
  },
];

const costs = [
  {
    icon: Wallet,
    title: 'Datos: 0 EUR/mes',
    text: 'Finnhub (capa gratuita con key), Yahoo Finance (chart API sin key) y SEC EDGAR (acceso público). Las tres fuentes de datos activas son sin cuota.',
  },
  {
    icon: FlaskConical,
    title: 'Modelos LLM: por uso',
    text: 'OpenCode Go como único proveedor, con el precio por modelo publicado en model_aliases.py (coste real o "desconocido" explícito, nunca 0 silencioso). Las micro-decisiones van por el cliente Jev (~0,042 USD/MTok de entrada, salida gratuita) con presupuesto objetivo por debajo de 0,50 USD/mes.',
  },
  {
    icon: BookOpen,
    title: 'Infraestructura: autoalojada',
    text: 'Frontend en Vercel (plan hobby); backend autoalojado con Postgres, Qdrant, MinIO y Redis en la máquina propia. Sin cuota cloud: solo energía y hardware del host.',
  },
];

export default function MetodologiaPage() {
  return (
    <main className="mx-auto flex w-full min-w-0 max-w-7xl flex-col gap-6 overflow-x-clip">
      <header className="flex flex-col gap-4 border-b border-gray-800 pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <p className="text-sm font-semibold uppercase text-teal-300">Transparencia</p>
          <h1 className="mt-1 break-words text-2xl font-bold text-gray-100 sm:text-3xl">Metodología</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-400">
            Fuentes, motores de valoración, límites y costes de CavaAI: de dónde sale cada dato, cómo se
            calcula cada número y qué no debes esperar de la plataforma.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-2 sm:flex sm:flex-wrap">
          <Button asChild className="h-11 w-full sm:w-auto" variant="outline">
            <Link href="/knowledge">
              <BookOpen className="h-4 w-4" />
              Knowledge
            </Link>
          </Button>
          <Button asChild className="h-11 w-full sm:w-auto" variant="outline">
            <Link href="/search">
              <Search className="h-4 w-4" />
              Buscar evidencia
            </Link>
          </Button>
          <Button asChild className="h-11 w-full sm:w-auto">
            <Link href="/propicks">
              <Sparkles className="h-4 w-4" />
              Ver ProPicks
            </Link>
          </Button>
        </div>
      </header>

      <section className="min-w-0">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <Database className="h-5 w-5 text-teal-300" />
          <h2 className="text-lg font-semibold text-gray-100">Fuentes de datos</h2>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:gap-4 md:grid-cols-2">
          {sources.map((source) => (
            <article
              className="flex min-w-0 flex-col rounded-xl border border-gray-800 bg-[#101010] p-4 break-words sm:p-5"
              key={source.title}
            >
              <div className="flex items-center gap-2">
                <source.icon className="h-5 w-5 shrink-0 text-teal-300" />
                <h3 className="font-semibold text-gray-100">{source.title}</h3>
              </div>
              <p className="mt-2 flex-1 text-sm leading-6 text-gray-400">{source.text}</p>
              <Button asChild className="mt-4 h-11 w-full sm:w-fit" size="sm" variant="outline">
                <Link href={source.href}>{source.cta}</Link>
              </Button>
            </article>
          ))}
        </div>
        <p className="mt-4 rounded-xl border border-amber-900/60 bg-amber-950/20 p-4 text-sm leading-6 text-amber-200">
          <strong>FMP retirado:</strong> Financial Modeling Prep se eliminó de la app porque su plan gratuito dejó de
          servir los endpoints que usábamos (ahora responden &laquo;Legacy Endpoint&raquo;). Ningún cálculo actual
          depende de FMP; los consumidores que quedaban se migran a Finnhub y Yahoo Finance.
        </p>
      </section>

      <section className="min-w-0 rounded-xl border border-gray-800 bg-[#101010] p-4 sm:p-5">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <Calculator className="h-5 w-5 text-teal-300" />
          <h2 className="text-lg font-semibold text-gray-100">Motores de valoración</h2>
          <Badge className="sm:ml-auto" variant="outline">
            5 motores
          </Badge>
        </div>
        <p className="mb-4 text-sm leading-6 text-gray-400">
          Cada compañía se valora con el motor que le corresponde por su tipo y factor tags; los supuestos de abajo
          son los reales del código (data-engine/app/valuation/engines/), no una descripción de marketing. Cuando
          falta un dato obligatorio el motor devuelve insufficient_data en lugar de inventar un número.
        </p>
        <ol className="grid grid-cols-1 gap-3 sm:gap-4 md:grid-cols-2">
          {engines.map((engine, index) => (
            <li
              className="flex min-w-0 gap-3 rounded-lg border border-gray-800 bg-black/30 p-4 break-words"
              key={engine.title}
            >
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-teal-950 text-sm font-semibold text-teal-300">
                {index + 1}
              </span>
              <div className="min-w-0">
                <h3 className="font-semibold text-gray-100">{engine.title}</h3>
                <p className="mt-1 text-sm leading-6 text-gray-400">{engine.text}</p>
              </div>
            </li>
          ))}
        </ol>
        <p className="mt-4 text-xs leading-5 text-gray-500">
          Además existen motores sectoriales dedicados para bancos (P/B justificado = (ROE - g)/(CoE - g)),
          aseguradoras (el mismo P/B multiplicado por un factor del combined ratio) e inmobiliarias cotizadas (REIT).
          Los escenarios bear/base/bull de cada motor se muestran con sus supuestos en la ficha de la compañía,
          dentro de &laquo;Supuestos del escenario&raquo;.
        </p>
      </section>

      <section className="min-w-0 rounded-xl border border-gray-800 bg-[#101010] p-4 sm:p-5">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <Sparkles className="h-5 w-5 text-teal-300" />
          <h2 className="text-lg font-semibold text-gray-100">Cómo se generan los ProPicks</h2>
          <Badge className="sm:ml-auto" variant="outline">
            4 pasos
          </Badge>
        </div>
        <ol className="grid grid-cols-1 gap-3 sm:gap-4 md:grid-cols-2">
          {steps.map((step, index) => (
            <li
              className="flex min-w-0 gap-3 rounded-lg border border-gray-800 bg-black/30 p-4 break-words"
              key={step.title}
            >
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-teal-950 text-sm font-semibold text-teal-300">
                {index + 1}
              </span>
              <div className="min-w-0">
                <h3 className="font-semibold text-gray-100">{step.title}</h3>
                <p className="mt-1 text-sm leading-6 text-gray-400">{step.text}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="min-w-0">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <ShieldAlert className="h-5 w-5 text-amber-300" />
          <h2 className="text-lg font-semibold text-gray-100">Límites que debes conocer</h2>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:gap-4 md:grid-cols-2">
          {limits.map((limit) => (
            <article
              className="min-w-0 rounded-xl border border-gray-800 bg-[#101010] p-4 break-words sm:p-5"
              key={limit.title}
            >
              <div className="flex items-center gap-2">
                <limit.icon className="h-5 w-5 shrink-0 text-amber-300" />
                <h3 className="font-semibold text-gray-100">{limit.title}</h3>
              </div>
              <p className="mt-2 text-sm leading-6 text-gray-400">{limit.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="min-w-0">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <Wallet className="h-5 w-5 text-teal-300" />
          <h2 className="text-lg font-semibold text-gray-100">Costes explícitos</h2>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:gap-4 md:grid-cols-3">
          {costs.map((cost) => (
            <article
              className="min-w-0 rounded-xl border border-gray-800 bg-[#101010] p-4 break-words sm:p-5"
              key={cost.title}
            >
              <div className="flex items-center gap-2">
                <cost.icon className="h-5 w-5 shrink-0 text-teal-300" />
                <h3 className="font-semibold text-gray-100">{cost.title}</h3>
              </div>
              <p className="mt-2 text-sm leading-6 text-gray-400">{cost.text}</p>
            </article>
          ))}
        </div>
        <p className="mt-4 rounded-xl border border-gray-800 bg-black/30 p-4 text-sm leading-6 text-gray-400">
          Fuentes, límites y costes se documentan aquí mismo, sin letra pequeña: lo que ves es lo que hay. Si un
          coste no se puede cuantificar, se dice &laquo;desconocido&raquo; en lugar de poner un 0 que rompería el
          presupuesto.
        </p>
      </section>
    </main>
  );
}
