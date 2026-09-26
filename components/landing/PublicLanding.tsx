import Link from 'next/link';
import type { Metadata } from 'next';
import {
    ArrowRight,
    BookOpen,
    CircleHelp,
    FileSearch,
    GitCompareArrows,
    Scale,
    TriangleAlert,
} from 'lucide-react';

import { CavaAIWordmark } from '@/components/CavaAIWordmark';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { SUPPORT_EMAIL } from '@/lib/config/brand';
import { isPublicSignUpOpen, productChain, productModules } from '@/lib/config/product';
import { NA, formatDate, formatMoney, formatNumber, formatPercent } from '@/lib/format';

/**
 * Metadatos de la landing.
 *
 * Viven aquí y la página los reexporta: `app/(public)/page.tsx` es
 * `export { default, metadata } from '@/components/landing/PublicLanding'`.
 * El título no incluye la marca porque la plantilla de `app/layout.tsx` ya
 * añade «| CavaAI».
 */
export const metadata: Metadata = {
    title: 'Research OS de inversión fundamental con fuentes trazables',
    description:
        'CavaAI convierte el research de una empresa en tesis trazables y versionadas: cada afirmación conserva su fuente y cada resultado revisa tu previsión.',
    alternates: { canonical: '/' },
    openGraph: {
        type: 'website',
        locale: 'es_ES',
        siteName: 'CavaAI',
        title: 'CavaAI: research de empresas con fuentes trazables y tesis versionadas',
        description:
            'Cada afirmación conserva su fuente, cada tesis tiene versión y cada resultado contrasta tu previsión. Metodología y términos públicos.',
    },
};

/**
 * Landing pública de CavaAI.
 *
 * Server component sin interaccion: el unico elemento con estado es el
 * accordion de preguntas frecuentes, que usa `<details>` nativo. No se importa
 * ningun componente de cliente, asi que la pagina no descarga JS.
 *
 * La ficha de empresa del apartado de demo es INVENTADA a proposito (ticker
 * inexistente, cifras redondas) y va rotulada como dato de ejemplo: el producto
 * promete no inventar cifras, asi que su propia web no puede empezar
 * inventando una cotizacion real.
 */

/* ------------------------------------------------------------------ *
 * 1. Problema
 * ------------------------------------------------------------------ */

const problems = [
    {
        title: 'Cuarenta pestañas y ni una fuente',
        text: 'La evidencia vive repartida entre informes anuales, notas de resultados y hojas de cálculo. Cuando toca defender una tesis nadie sabe de dónde salió cada dato.',
    },
    {
        title: 'Tres modelos, tres verdades',
        text: 'El mismo discounted cash flow rehecho cada trimestre da tres cifras distintas, y ninguna lleva sus supuestos a la vista. Comparar dos modelos tuyos deja de tener sentido.',
    },
    {
        title: 'Las tesis caducan en silencio',
        text: 'El plan se escribe una vez y nunca se vuelve a contrastar con lo que la empresa publicó después. Lo que no se revisa no es una tesis: es una opinión.',
    },
];

/* ------------------------------------------------------------------ *
 * 3. Tres pasos
 * ------------------------------------------------------------------ */

const steps = [
    {
        title: 'Reúne la evidencia con su fuente',
        text: 'Cada hecho entra con el documento del que sale, su fecha y su nivel de confianza. Si un dato no se puede traer, queda declarado como ausente: nunca se rellena con una estimación silenciosa.',
    },
    {
        title: 'Modela con supuestos visibles',
        text: 'El motor de valoración se elige por tipo de empresa y sus supuestos —crecimiento, margen, coste de capital— quedan escritos junto al número, con escenarios y sensibilidad.',
    },
    {
        title: 'Escribe la tesis y revísala',
        text: 'La tesis se versiona: hipótesis, escenarios con probabilidad, catalizadores con fecha y qué la invalidaría. Cada resultado publicado se compara con lo que habías previsto.',
    },
];

/* ------------------------------------------------------------------ *
 * 4. Demo del espacio de trabajo
 * ------------------------------------------------------------------ */

const demoThesis = {
    summary:
        'Ejemplo de resumen ejecutivo: la tesis se apoya en un margen de caja libre que se sostiene y en un segmento nuevo que todavía no aporta lo previsto.',
    hypothesis:
        'Ejemplo de hipótesis: si el margen de caja libre se mantiene por encima del 18% mientras el segmento nuevo crece, el negocio puede financiar su expansión sin diluir.',
    rating: 'Ejemplo de tesis v3, vigente',
    version: 3,
    date: '2026-08-14',
    scenarios: [
        { label: 'Precio', value: 42, probability: null },
        { label: 'Bajista', value: 24, probability: 0.25 },
        { label: 'Base', value: 51, probability: 0.5, highlight: true },
        { label: 'Alcista', value: 78, probability: 0.25 },
    ],
    marginOfSafety: 0.22,
    catalysts: [
        { label: 'Resultados del tercer trimestre', date: '30 oct 2026' },
        { label: 'Revisión del contrato principal', date: 'sin fecha confirmada' },
    ],
    invalidation: [
        'Margen de caja libre por debajo del 8% durante dos trimestres seguidos.',
        'Pérdida de dos de los tres clientes que más aportan.',
    ],
};

const demoClaims = [
    {
        claim: 'El margen de caja libre de los últimos cinco años no baja del 15%.',
        source: 'Informe anual de ejemplo, página 42',
        date: '2026-02-28',
        verdict: 'Confirmado',
    },
    {
        claim: 'El año que viene la mayor parte de la deuda refinancia a un tipo superior.',
        source: 'Nota de resultados de ejemplo, párrafo 18',
        date: '2026-05-06',
        verdict: 'Confirmado',
    },
    {
        claim: 'El segmento nuevo aporta un 30% de los ingresos este año.',
        source: 'Documento sin fuente verificable',
        date: '2026-08-14',
        verdict: 'Sin verificar',
    },
];

const demoMoat = [
    { check: 'Margen de caja libre 5 años', value: 0.18, threshold: '> 5%', passed: true },
    { check: 'Rentabilidad sobre recursos propios 5 años', value: 0.21, threshold: '> 15%', passed: true },
    { check: 'Rentabilidad del capital invertido', value: 0.11, threshold: '> coste de capital', passed: true },
    { check: 'Ganancias del propietario 5 años', value: 420, threshold: '> 0', passed: true },
    { check: 'Inversión sobre depreciación 5 años', value: 1.8, threshold: '≤ 1,5', passed: false },
];

const demoValuation = {
    engine: 'DCF de flujo de caja libre a 5 años',
    assumptions: [
        'Crecimiento de ingresos en el año 5: 6% (declarado como supuesto, no como hecho).',
        'Margen de caja libre normalizado: 18% (media de los cinco años disponibles).',
        'Coste de capital: 9,5% calculado sobre la estructura de capital del último informe.',
    ],
    wacc: [0.085, 0.095, 0.105],
    growth: [0.04, 0.06, 0.08],
    grid: [
        [58, 68, 79],
        [49, 57, 66],
        [41, 47, 54],
    ],
};

const demoChanges = [
    { date: '2026-08-14', what: 'Tesis v3: se sube el supuesto de crecimiento tras el resultado del 2T.' },
    { date: '2026-06-02', what: 'Evidencia: el informe anual confirma la mejora del margen de caja libre.' },
    { date: '2026-02-20', what: 'Tesis v2: se añade el criterio de invalidación sobre la concentración de clientes.' },
];

/* ------------------------------------------------------------------ *
 * 5. Metodologia
 * ------------------------------------------------------------------ */

const methodology = [
    { icon: FileSearch, text: 'Tres fuentes de datos con licencia y acceso público, declaradas una a una.' },
    { icon: Scale, text: 'Cinco motores de valoración, elegidos por tipo de empresa, con sus supuestos a la vista.' },
    { icon: GitCompareArrows, text: 'Los backtests solo ven la información disponible en cada fecha: nada de mirar al futuro.' },
    { icon: BookOpen, text: 'Límites y costes publicados en la propia web, sin letra pequeña.' },
];

/* ------------------------------------------------------------------ *
 * 6. Preguntas frecuentes
 * ------------------------------------------------------------------ */

const faqs = [
    {
        question: '¿CavaAI es asesoramiento de inversión?',
        answer:
            'No. Es una herramienta educativa y de análisis: te da datos, trazabilidad y un sitio donde escribir tu tesis. Las decisiones de inversión son tuyas y conviene consultar a un profesional.',
    },
    {
        question: '¿De dónde salen los datos?',
        answer:
            'De fuentes con licencia y de acceso público, identificadas una a una. Cada hecho conserva el documento y la fecha de origen, y cuando un dato no se puede traer la ficha lo declara en lugar de rellenarlo.',
    },
    {
        question: '¿Qué pasa si un dato no está disponible?',
        answer:
            'Se queda sin dato. CavaAI no estima ni interpola: un número sin fuente no entra en el modelo, y la valoración devuelve un estado explícito de evidencia insuficiente.',
    },
    {
        question: '¿Puedo leer los términos y la metodología sin crear una cuenta?',
        answer:
            'Sí. Ambas páginas son públicas y no piden sesión. El acceso a las fichas de empresa sí requiere una cuenta.',
    },
    {
        question: '¿Puedo exportar mi trabajo?',
        answer:
            'Sí. Tus tesis, tus notas y tu cartera se pueden exportar en cualquier momento: los datos te pertenecen.',
    },
];

/* ------------------------------------------------------------------ */

function SectionHeading({ eyebrow, title, children }: { eyebrow: string; title: string; children?: React.ReactNode }) {
    return (
        <div className="max-w-3xl">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-teal-300">{eyebrow}</p>
            <h2 className="mt-2 text-2xl font-bold text-gray-100 sm:text-3xl">{title}</h2>
            {children ? <p className="mt-3 text-base leading-7 text-gray-400">{children}</p> : null}
        </div>
    );
}

export default function PublicLanding() {
    const signUpOpen = isPublicSignUpOpen();
    const waitlistHref = `mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent('Lista de espera de CavaAI')}`;

    return (
        <main id="content" tabIndex={-1} className="w-full">
            {/* Hero ---------------------------------------------------- */}
            <section className="container py-14 sm:py-20">
                <div className="max-w-3xl">
                    <p className="inline-flex items-center gap-2 rounded-full border border-teal-300/30 bg-teal-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-teal-300">
                        Research OS de inversión fundamental
                    </p>
                    <h1 className="mt-5 text-3xl font-bold leading-tight tracking-tight text-gray-100 sm:text-5xl">
                        Convierte el research disperso de una empresa en tesis trazables que se revisan
                        contra la realidad
                    </h1>
                    <p className="mt-5 text-lg leading-8 text-gray-400">
                        Cada afirmación conserva su documento y su fecha, cada tesis tiene versión, y cada
                        resultado publicado contrasta tu previsión. Si un dato no está, CavaAI lo dice en
                        lugar de inventarlo.
                    </p>
                    <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
                        {signUpOpen ? (
                            <Button asChild size="lg">
                                <Link href="/sign-up">
                                    Empezar mi primera tesis
                                    <ArrowRight aria-hidden="true" />
                                </Link>
                            </Button>
                        ) : (
                            <Button asChild size="lg">
                                <a href={waitlistHref}>
                                    Pedir acceso en la lista de espera
                                    <ArrowRight aria-hidden="true" />
                                </a>
                            </Button>
                        )}
                        <Button asChild size="lg" variant="outline">
                            <Link href="#demo">Ver una demo pública del espacio de trabajo</Link>
                        </Button>
                    </div>
                    <p className="mt-4 text-sm text-gray-500">
                        <Link href="/terms" className="public-footer-link">
                            Términos de servicio
                        </Link>{' '}
                        ·{' '}
                        <Link href="/metodologia" className="public-footer-link">
                            Metodología y fuentes de datos
                        </Link>
                    </p>
                </div>
            </section>

            {/* El problema --------------------------------------------- */}
            <section className="container pb-14 sm:pb-20">
                <SectionHeading eyebrow="El problema" title="El research se pierde y las tesis caducan">
                    Ninguna de estas tres cosas es un problema de datos: es un problema de memoria.
                </SectionHeading>
                <ol className="mt-8 grid gap-4 md:grid-cols-3">
                    {problems.map((problem, index) => (
                        <li
                            className="flex min-w-0 flex-col rounded-xl border border-gray-700/50 bg-surface-1 p-5"
                            key={problem.title}
                        >
                            <span className="text-xs font-semibold text-teal-300">0{index + 1}</span>
                            <h3 className="mt-2 font-semibold text-gray-100">{problem.title}</h3>
                            <p className="mt-2 text-sm leading-6 text-gray-400">{problem.text}</p>
                        </li>
                    ))}
                </ol>
            </section>

            {/* Tres pasos ---------------------------------------------- */}
            <section className="border-y border-gray-700/50 bg-surface-1 py-14 sm:py-20">
                <div className="container">
                    <SectionHeading eyebrow="Cómo funciona" title={`${productChain}, en tres pasos`}>
                        El mismo recorrido que verás dentro: nada de lo que se cuenta aquí es una promesa
                        que la app no cumpla.
                    </SectionHeading>
                    <ol className="mt-8 grid gap-4 md:grid-cols-3">
                        {steps.map((step, index) => (
                            <li
                                className="flex min-w-0 flex-col rounded-xl border border-gray-700/50 bg-surface-overlay p-5"
                                key={step.title}
                            >
                                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-teal-950 text-sm font-semibold text-teal-300">
                                    {index + 1}
                                </span>
                                <h3 className="mt-3 font-semibold text-gray-100">{step.title}</h3>
                                <p className="mt-2 text-sm leading-6 text-gray-400">{step.text}</p>
                            </li>
                        ))}
                    </ol>
                    <ul className="mt-8 grid gap-3 md:grid-cols-3">
                        {productModules.map(({ icon: ModuleIcon, title, description }) => (
                            <li
                                className="flex min-w-0 items-start gap-3 rounded-xl border border-gray-700/50 bg-black/20 p-4"
                                key={title}
                            >
                                <ModuleIcon aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-teal-300" />
                                <div className="min-w-0">
                                    <p className="font-medium text-gray-100">{title}</p>
                                    <p className="mt-1 text-sm leading-6 text-gray-400">{description}</p>
                                </div>
                            </li>
                        ))}
                    </ul>
                </div>
            </section>

            {/* Demo publica -------------------------------------------- */}
            <section className="container py-14 sm:py-20" id="demo">
                <SectionHeading eyebrow="Demo pública" title="Así se ve una ficha dentro del espacio de trabajo">
                    Un ejemplo con la estructura real de la ficha: tesis versionada, evidencia con su
                    fuente, marco competitivo, valoración con supuestos y el registro de cambios.
                </SectionHeading>

                <p className="mt-6 flex items-start gap-3 rounded-xl border border-amber-900/60 bg-amber-950/20 p-4 text-sm leading-6 text-amber-200">
                    <TriangleAlert aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0" />
                    <span>
                        <strong>Datos de ejemplo, no son de una empresa real.</strong> El ticker{' '}
                        <code className="font-mono">DEMO</code> no existe en ningún mercado y todas las
                        cifras están inventadas para enseñar la estructura de la ficha. Un producto que
                        promete no inventar datos no puede empezar su web inventando una cotización.
                    </span>
                </p>

                <div className="mt-6 space-y-4">
                    {/* Cabecera de la ficha */}
                    <div className="rounded-xl border border-gray-700/50 bg-surface-1 p-5">
                        <div className="flex flex-wrap items-center gap-2">
                            <span className="font-mono text-sm text-gray-400">DEMO</span>
                            <h3 className="text-lg font-semibold text-gray-100">Empresa de ejemplo</h3>
                            <Badge variant="outline">{demoThesis.rating}</Badge>
                            <Badge variant="outline">v{demoThesis.version}</Badge>
                            <span className="text-xs text-gray-500">
                                Tesis del {formatDate(demoThesis.date)}
                            </span>
                        </div>
                        <p className="mt-3 text-sm leading-6 text-gray-300">{demoThesis.summary}</p>
                    </div>

                    <div className="grid gap-4 lg:grid-cols-2">
                        {/* Capa 1: evidencia */}
                        <section className="min-w-0 rounded-xl border border-gray-700/50 bg-surface-1 p-5">
                            <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-100">
                                <FileSearch aria-hidden="true" className="h-4 w-4 text-teal-300" />
                                1. Evidencia
                            </h3>
                            <ul className="mt-3 space-y-3">
                                {demoClaims.map((item) => (
                                    <li className="rounded-lg border border-gray-700/50 bg-black/20 p-3" key={item.source}>
                                        <p className="text-sm leading-6 text-gray-200">{item.claim}</p>
                                        <p className="mt-2 text-xs text-gray-500">
                                            {item.source} · {formatDate(item.date)}
                                        </p>
                                        <p
                                            className={`mt-1 text-xs font-medium ${
                                                item.verdict === 'Confirmado' ? 'text-teal-300' : 'text-amber-300'
                                            }`}
                                        >
                                            {item.verdict}
                                        </p>
                                    </li>
                                ))}
                            </ul>
                            <p className="mt-3 text-xs leading-5 text-gray-500">
                                El último punto no entra en el modelo: una afirmación sin fuente
                                verificable se conserva marcada y no se usa como hecho.
                            </p>
                        </section>

                        {/* Capa 2: marco competitivo */}
                        <section className="min-w-0 rounded-xl border border-gray-700/50 bg-surface-1 p-5">
                            <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-100">
                                <Scale aria-hidden="true" className="h-4 w-4 text-teal-300" />
                                2. Foso competitivo
                            </h3>
                            <ul className="mt-3 space-y-2">
                                {demoMoat.map((check) => (
                                    <li
                                        className="flex items-center justify-between gap-3 rounded-lg border border-gray-700/50 bg-black/20 px-3 py-2"
                                        key={check.check}
                                    >
                                        <span className="text-sm text-gray-300">{check.check}</span>
                                        <span className="shrink-0 text-xs">
                                            <span className="font-mono text-gray-200">
                                                {check.passed
                                                    ? formatPercent(check.value)
                                                    : formatNumber(check.value, { maximumFractionDigits: 1 })}
                                            </span>{' '}
                                            <span className="text-gray-500">frente a {check.threshold}</span>
                                            <span className={check.passed ? ' text-teal-300' : ' text-amber-300'}>
                                                {' '}
                                                {check.passed ? 'superado' : 'no superado'}
                                            </span>
                                        </span>
                                    </li>
                                ))}
                            </ul>
                        </section>
                    </div>

                    {/* Capa 3: valoracion */}
                    <section className="min-w-0 rounded-xl border border-gray-700/50 bg-surface-1 p-5">
                        <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-100">
                            <GitCompareArrows aria-hidden="true" className="h-4 w-4 text-teal-300" />
                            3. Valoración
                        </h3>
                        <p className="mt-2 text-xs text-gray-500">Motor aplicado: {demoValuation.engine}</p>
                        <ul className="mt-3 grid gap-2 md:grid-cols-3">
                            {demoValuation.assumptions.map((assumption) => (
                                <li className="rounded-lg border border-gray-700/50 bg-black/20 p-3 text-xs leading-5 text-gray-400" key={assumption}>
                                    {assumption}
                                </li>
                            ))}
                        </ul>
                        <div className="mt-4 overflow-x-auto">
                            <table className="w-full min-w-[22rem] text-left text-sm">
                                <caption className="pb-2 text-left text-xs text-gray-500">
                                    Sensibilidad del valor por acción: coste de capital (filas) frente a
                                    crecimiento en el año 5 (columnas).
                                </caption>
                                <thead>
                                    <tr>
                                        <th scope="col" className="px-3 py-2 text-xs font-medium text-gray-500">
                                            Coste de capital
                                        </th>
                                        {demoValuation.growth.map((growth) => (
                                            <th key={growth} scope="col" className="px-3 py-2 text-xs font-medium text-gray-500">
                                                {formatPercent(growth, { digits: 0 })}
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {demoValuation.grid.map((row, rowIndex) => (
                                        <tr key={demoValuation.wacc[rowIndex]}>
                                            <th scope="row" className="px-3 py-2 text-xs font-medium text-gray-500">
                                                {formatPercent(demoValuation.wacc[rowIndex], { digits: 1 })}
                                            </th>
                                            {row.map((value, columnIndex) => (
                                                <td
                                                    className={`px-3 py-2 font-mono ${
                                                        rowIndex === 1 && columnIndex === 1
                                                            ? 'text-teal-300'
                                                            : 'text-gray-300'
                                                    }`}
                                                    key={demoValuation.growth[columnIndex]}
                                                >
                                                    {formatMoney(value)}
                                                </td>
                                            ))}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                        <p className="mt-3 text-xs leading-5 text-gray-500">
                            Motor sin datos suficientes: el beneficio por acción aparece como{' '}
                            <span className="font-mono text-gray-400">{NA}</span> porque el último informe
                            de ejemplo no trae el desglose por acción. No se rellena con una estimación.
                        </p>
                    </section>

                    {/* Escenarios e invalidacion */}
                    <div className="grid gap-4 lg:grid-cols-2">
                        <section className="min-w-0 rounded-xl border border-gray-700/50 bg-surface-1 p-5">
                            <h3 className="text-sm font-semibold text-gray-100">Escenarios de la tesis</h3>
                            <p className="mt-2 text-sm leading-6 text-gray-300">{demoThesis.hypothesis}</p>
                            <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
                                {demoThesis.scenarios.map((scenario) => (
                                    <div
                                        className={`rounded-lg border p-3 ${
                                            scenario.highlight
                                                ? 'border-teal-800 bg-teal-950/20'
                                                : 'border-gray-700/50 bg-black/20'
                                        }`}
                                        key={scenario.label}
                                    >
                                        <p className="text-xs uppercase text-gray-500">{scenario.label}</p>
                                        <p className="mt-1 text-base font-semibold text-gray-100">
                                            {formatMoney(scenario.value)}
                                        </p>
                                        {scenario.probability !== null ? (
                                            <p className="text-xs text-gray-500">
                                                p = {formatPercent(scenario.probability, { digits: 0 })}
                                            </p>
                                        ) : null}
                                    </div>
                                ))}
                                <div className="rounded-lg border border-gray-700/50 bg-black/20 p-3">
                                    <p className="text-xs uppercase text-gray-500">Margen de seguridad</p>
                                    <p className="mt-1 text-base font-semibold text-gray-100">
                                        {formatPercent(demoThesis.marginOfSafety)}
                                    </p>
                                </div>
                            </div>
                            <h4 className="mt-4 text-xs font-semibold uppercase tracking-wide text-gray-400">
                                Catalizadores
                            </h4>
                            <ul className="mt-2 space-y-1 text-sm text-gray-300">
                                {demoThesis.catalysts.map((catalyst) => (
                                    <li key={catalyst.label}>
                                        {catalyst.label} · <span className="text-gray-400">{catalyst.date}</span>
                                    </li>
                                ))}
                            </ul>
                        </section>

                        <section className="min-w-0 rounded-xl border border-red-900/50 bg-red-950/10 p-5">
                            <h3 className="text-sm font-semibold text-gray-100">Qué invalidaría la tesis</h3>
                            <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-6 text-gray-300">
                                {demoThesis.invalidation.map((criterion) => (
                                    <li key={criterion}>{criterion}</li>
                                ))}
                            </ul>
                            <h4 className="mt-5 text-xs font-semibold uppercase tracking-wide text-gray-400">
                                Seguimiento de cambios
                            </h4>
                            <ul className="mt-2 space-y-2">
                                {demoChanges.map((change) => (
                                    <li className="text-sm leading-6 text-gray-300" key={change.date}>
                                        <span className="text-gray-500">{formatDate(change.date)}</span> · {change.what}
                                    </li>
                                ))}
                            </ul>
                        </section>
                    </div>
                </div>

                <p className="mt-6 text-sm text-gray-500">
                    Esta es una maqueta de ejemplo. La ficha de una empresa real se construye con los
                    documentos que tú subes y con los datos de mercado que ya tiene la plataforma.
                </p>
            </section>

            {/* Metodologia --------------------------------------------- */}
            <section className="border-y border-gray-700/50 bg-surface-1 py-14 sm:py-20">
                <div className="container">
                    <SectionHeading eyebrow="Metodología" title="Publicamos de dónde sale cada número">
                        La metodología completa, con los motores, los límites y los costes, está escrita
                        y es pública.
                    </SectionHeading>
                    <ul className="mt-8 grid gap-4 md:grid-cols-2">
                        {methodology.map(({ icon: MethodIcon, text }) => (
                            <li className="flex items-start gap-3" key={text}>
                                <MethodIcon aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-teal-300" />
                                <span className="text-sm leading-6 text-gray-300">{text}</span>
                            </li>
                        ))}
                    </ul>
                    <Button asChild className="mt-8" variant="outline">
                        <Link href="/metodologia">
                            Leer la metodología completa
                            <ArrowRight aria-hidden="true" />
                        </Link>
                    </Button>
                </div>
            </section>

            {/* Preguntas frecuentes ------------------------------------ */}
            <section className="container py-14 sm:py-20">
                <div className="max-w-3xl">
                    <h2 className="flex items-center gap-2 text-2xl font-bold text-gray-100 sm:text-3xl">
                        <CircleHelp aria-hidden="true" className="h-6 w-6 text-teal-300" />
                        Preguntas frecuentes
                    </h2>
                </div>
                <div className="mt-8 divide-y divide-gray-700/50 rounded-xl border border-gray-700/50 bg-surface-1">
                    {faqs.map((faq) => (
                        <details className="group px-5 py-4" key={faq.question}>
                            <summary className="cursor-pointer text-sm font-semibold text-gray-100 marker:text-teal-300">
                                {faq.question}
                            </summary>
                            <p className="mt-3 text-sm leading-6 text-gray-400">{faq.answer}</p>
                        </details>
                    ))}
                </div>
            </section>

            {/* Cierre --------------------------------------------------- */}
            <section className="container pb-16 sm:pb-24">
                <div className="rounded-2xl border border-teal-900/60 bg-teal-950/20 p-6 sm:p-10">
                    <CavaAIWordmark />
                    <h2 className="mt-5 text-2xl font-bold text-gray-100 sm:text-3xl">
                        Empieza por una empresa que ya conoces y comprueba si la tesis aguanta
                    </h2>
                    <p className="mt-3 max-w-2xl text-sm leading-7 text-gray-300">
                        Trae sus últimos informes, genera la primera versión de la tesis y contrástala con
                        el siguiente resultado. Si el registro está abierto en este momento, puedes crear la
                        cuenta en un minuto.
                    </p>
                    <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center">
                        {signUpOpen ? (
                            <Button asChild size="lg">
                                <Link href="/sign-up">
                                    Crear mi cuenta
                                    <ArrowRight aria-hidden="true" />
                                </Link>
                            </Button>
                        ) : (
                            <Button asChild size="lg">
                                <a href={waitlistHref}>
                                    Pedir acceso en la lista de espera
                                    <ArrowRight aria-hidden="true" />
                                </a>
                            </Button>
                        )}
                        <Button asChild size="lg" variant="outline">
                            <Link href="/help">Ver el centro de ayuda</Link>
                        </Button>
                    </div>
                    <p className="mt-5 text-xs leading-5 text-gray-400">
                        CavaAI es una herramienta educativa y de análisis, no asesoramiento de inversión.{' '}
                        <Link href="/terms" className="public-footer-link">
                            Términos de servicio
                        </Link>
                        . ¿Preguntas? Escribe a{' '}
                        <a href={`mailto:${SUPPORT_EMAIL}`} className="public-footer-link">
                            {SUPPORT_EMAIL}
                        </a>
                        .
                    </p>
                </div>
            </section>
        </main>
    );
}
