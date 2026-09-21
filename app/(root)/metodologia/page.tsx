import Link from 'next/link';
import {
  BookOpen,
  Database,
  FlaskConical,
  Library,
  Scale,
  Search,
  ShieldAlert,
  Sparkles,
  Target,
  TriangleAlert,
  Users,
  Wallet,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

export const dynamic = 'force-dynamic';
export const revalidate = 3600;

const sources = [
  {
    icon: Users,
    title: 'SEC EDGAR · Form 4',
    text: 'Compras insider en mercado abierto: clusters, operaciones de CEO/CFO y grandes compras. Cada señal enlaza a su ficha de research.',
    href: '/insider',
    cta: 'Ver señales insider',
  },
  {
    icon: FlaskConical,
    title: 'Evidencia de compañías',
    text: 'Hechos, métricas y secciones de tesis por ticker, con citas y estado canónico antes de cualquier conclusión.',
    href: '/research',
    cta: 'Abrir research',
  },
  {
    icon: Library,
    title: 'Biblioteca de conocimiento',
    text: 'Libros, cartas y casos separados de la evidencia de empresas, con principios trazables aprobados por humanos.',
    href: '/knowledge',
    cta: 'Abrir knowledge',
  },
  {
    icon: Database,
    title: 'RAG reconstruible',
    text: 'Postgres como canónico y Qdrant como índice semántico que se reconstruye desde Postgres. Nada vive solo en el vector.',
    href: '/search',
    cta: 'Buscar evidencia',
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
    text: 'Score 0–100 con nivel de confianza y motivos auditables: cada motivo muestra su métrica y su valor.',
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
    text: 'Los motores de valoración solo usan información disponible en cada fecha simulada: sin mirar al futuro.',
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
    title: 'Infraestructura',
    text: 'Frontend en Vercel; backend con Postgres, Qdrant, MinIO y Redis. Los puertos de base de datos están cerrados al exterior.',
  },
  {
    icon: FlaskConical,
    title: 'Modelos',
    text: 'OpenCode Go como único LLM y micro-decisiones locales: el coste por análisis se mantiene bajo y predecible.',
  },
  {
    icon: BookOpen,
    title: 'Transparencia total',
    text: 'Fuentes, límites y costes documentados aquí mismo. Sin letra pequeña: lo que ves es lo que hay.',
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
            Fuentes, límites y costes de CavaAI: de dónde sale cada dato, cómo se calculan los
            ProPicks y qué no debes esperar de la plataforma.
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
          <h2 className="text-lg font-semibold text-gray-100">Costes e infraestructura</h2>
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
      </section>
    </main>
  );
}
