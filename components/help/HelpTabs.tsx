'use client';

import { useState } from 'react';
import Link from 'next/link';
import { SUPPORT_EMAIL } from '@/lib/config/brand';

const modules = [
  {
    href: '/research',
    title: 'Research',
    text: 'Ficha por ticker: hechos financieros canónicos, métricas trazables, tesis, moat, pares, valoración y chat con fuentes.',
  },
  {
    href: '/research',
    title: 'Modelo a largo plazo',
    text: 'Modelo fundamental con supuestos visibles (crecimiento, margen FCF, WACC), escenarios Bear/Base/Bull con sus spreads, owner earnings, TAM/SAM/SOM y reverse DCF. Pestaña «Model» de la ficha.',
  },
  {
    href: '/portfolio',
    title: 'Cartera',
    text: 'Posiciones, transacciones, importación desde IBKR y desglose por sector y divisa.',
  },
  {
    href: '/risk',
    title: 'Riesgo',
    text: 'Pesos, concentración (top 1 y top 5) y exposición por sector y factor. No calcula VaR, drawdown ni volatilidad: son métricas de estructura de cartera.',
  },
  {
    href: '/screeners',
    title: 'Screener',
    text: 'Universo de grandes capitalizaciones con perfiles y precios reales para partir de candidatos verificables.',
  },
  {
    href: '/propicks',
    title: 'ProPicks',
    text: 'Scores 0-100 con motivos auditables (cada motivo muestra su métrica y su valor) y backtest por estrategia comparado contra el S&P 500.',
  },
  {
    href: '/alerts',
    title: 'Alertas',
    text: 'Señales con umbral de materialidad explícito, enlazadas a la ficha de la compañía.',
  },
  {
    href: '/insider',
    title: 'Insider',
    text: 'Operaciones de personas vinculadas (Form 4 de la SEC) con señales por cluster de compra.',
  },
  {
    href: '/knowledge',
    title: 'Knowledge y búsqueda',
    text: 'Biblioteca de principios de inversión e índice semántico que se reconstruye desde Postgres.',
  },
  {
    href: '/watchlist',
    title: 'Watchlist',
    text: 'Seguimiento de símbolos con enlace directo a su ficha de research.',
  },
  {
    href: '/metodologia',
    title: 'Metodología',
    text: 'Motores de valoración con sus supuestos, fuentes de datos, límites (look-ahead, cobertura parcial) y costes explícitos.',
  },
];

const faqs = [
  {
    question: "¿CavaAI es realmente gratuito?",
    answer: "Sí, las funcionalidades principales son gratuitas. Creemos que las herramientas financieras deben ser accesibles para todos."
  },
  {
    question: "Soy estudiante, ¿puedo usar esto para mis proyectos?",
    answer: "¡Por supuesto! Úsalo para proyectos escolares, aprendizaje o construir tu portafolio. La plataforma está diseñada para ser intuitiva y educativa."
  },
  {
    question: "¿Cómo añado acciones a mis favoritos?",
    answer: "Navega a cualquier página de acción y haz clic en el icono de estrella. También puedes buscar usando la barra de búsqueda y añadir directamente desde los resultados."
  },
  {
    question: "¿Qué hago si encuentro un bug o tengo una sugerencia?",
    answer: "¡Por favor cuéntanos! Envía un email a soporte y revisaremos tu comentario. Cada reporte es una oportunidad para mejorar la plataforma."
  },
  {
    question: "¿Los datos de mercado son en tiempo real?",
    answer: "Proporcionamos datos con un ligero retraso para la mayoría de mercados. Para análisis y educación, esto es más que suficiente."
  }
];

export default function HelpTabs() {
  const [activeTab, setActiveTab] = useState<'faq' | 'api' | 'community'>('faq');

  return (
    <div className="container mx-auto px-4 py-12 max-w-4xl">
      <div className="text-center mb-12">
        <h1 className="text-4xl font-bold text-gray-100 mb-4">Centro de Ayuda</h1>
        <p className="text-xl text-gray-200 mb-4">
          Documentación, preguntas frecuentes y soporte
        </p>
        <p className="mt-4 text-sm text-gray-400">
          ¿Quieres ver cómo analizamos y de dónde salen los datos?{' '}
          <Link href="/metodologia" className="text-teal-400 underline underline-offset-4 hover:text-teal-300">
            Metodología y fuentes
          </Link>
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-8 border-b border-gray-700">
        <button
          onClick={() => setActiveTab('faq')}
          className={`px-6 py-3 font-medium transition-colors ${
            activeTab === 'faq'
              ? 'text-teal-400 border-b-2 border-teal-400'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          FAQs
        </button>
        <button
          onClick={() => setActiveTab('api')}
          className={`px-6 py-3 font-medium transition-colors ${
            activeTab === 'api'
              ? 'text-teal-400 border-b-2 border-teal-400'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          Documentación
        </button>
        <button
          onClick={() => setActiveTab('community')}
          className={`px-6 py-3 font-medium transition-colors ${
            activeTab === 'community'
              ? 'text-teal-400 border-b-2 border-teal-400'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          Contacto
        </button>
      </div>

      {/* FAQ Tab */}
      {activeTab === 'faq' && (
        <>
          {/* Help Philosophy */}
          <div className="grid md:grid-cols-3 gap-6 mb-12">
            <div className="bg-gray-800 rounded-lg shadow-sm p-6 border hover:shadow-md transition-shadow">
              <h3 className="text-lg font-semibold text-blue-500 mb-2">Aprende</h3>
              <p className="text-gray-200 text-sm">
                Nuestras guías están escritas sin jerga técnica. No asumimos conocimiento previo.
              </p>
            </div>

            <div className="bg-gray-800 rounded-lg shadow-sm p-6 border hover:shadow-md transition-shadow">
              <h3 className="text-lg font-semibold text-green-500 mb-2">Soporte</h3>
              <p className="text-gray-200 text-sm">
                Personas reales ayudando a personas reales. Estudiantes, profesionales y mentores.
              </p>
            </div>

            <div className="bg-gray-800 rounded-lg shadow-sm p-6 border hover:shadow-md transition-shadow">
              <h3 className="text-lg font-semibold text-purple-500 mb-2">Diseño Intuitivo</h3>
              <p className="text-gray-200 text-sm">
                Cada función está diseñada con accesibilidad y facilidad de uso en mente.
              </p>
            </div>
          </div>

          {/* Community FAQs */}
          <section className="mb-12">
            <h2 className="text-3xl font-bold text-gray-100 mb-8 text-center">Preguntas Frecuentes</h2>
            <div className="space-y-4">
              {faqs.map((faq, index) => (
                <div key={index} className="bg-gray-800 rounded-lg shadow-sm p-6 border">
                  <h3 className="text-lg font-semibold text-gray-100 mb-2">{faq.question}</h3>
                  <p className="text-gray-200">{faq.answer}</p>
                </div>
              ))}
            </div>
          </section>
        </>
      )}

      {/* Documentation Tab */}
      {activeTab === 'api' && (
        <div className="space-y-8">
          <div className="mb-8">
            <h2 className="text-3xl font-bold text-gray-100 mb-4">Documentación</h2>
            <p className="text-xl text-gray-200 mb-4">
              Guía práctica por módulo: lo que la app hace hoy y cómo usarla.
            </p>
          </div>

          {/* Primeros pasos */}
          <section className="bg-gray-800 rounded-lg shadow-sm p-6 border">
            <h2 className="text-2xl font-semibold text-gray-100 mb-4">Primeros pasos: modelo → tesis → decisión</h2>
            <ol className="space-y-4 text-gray-200">
              <li>
                <strong className="text-teal-400">1. Modelo.</strong>{' '}
                En <Link href="/research" className="text-teal-400 underline underline-offset-4 hover:text-teal-300">Research</Link> elige
                la compañía y abre la pestaña «Model» → «Generate model». Revisa los supuestos (crecimiento, margen
                FCF, WACC) y los escenarios Bear/Base/Bull con sus spreads antes de fiarte del número.
              </li>
              <li>
                <strong className="text-teal-400">2. Tesis.</strong>{' '}
                Genera la tesis desde la misma ficha: hipótesis, escenarios con probabilidades, catalizadores con
                fecha y qué la invalidaría. El trabajo se puede exportar desde{' '}
                <Link href="/export" className="text-teal-400 underline underline-offset-4 hover:text-teal-300">/export</Link>.
              </li>
              <li>
                <strong className="text-teal-400">3. Decisión.</strong>{' '}
                Registra la decisión en el Decision Journal (compra / mantén / reduce / vende / vigila / evita) con la
                evidencia que la justifica y las condiciones verificables («what must be true»). Más adelante,
                «Expectation vs Reality» compara tu previsión con los hechos publicados.
              </li>
            </ol>
          </section>

          {/* Guía por módulo */}
          <section className="bg-gray-800 rounded-lg shadow-sm p-6 border">
            <h2 className="text-2xl font-semibold text-gray-100 mb-4">Guía por módulo</h2>
            <div className="grid md:grid-cols-2 gap-4">
              {modules.map((module) => (
                <div className="bg-gray-900/40 p-4 rounded-lg" key={module.title}>
                  <h3 className="font-semibold text-teal-400 mb-2">
                    <Link href={module.href} className="underline underline-offset-4 hover:text-teal-300">
                      {module.title}
                    </Link>
                  </h3>
                  <p className="text-gray-300 text-sm">{module.text}</p>
                </div>
              ))}
            </div>
          </section>

          {/* Glosario y metodología */}
          <section className="bg-gray-800 rounded-lg shadow-sm p-6 border">
            <h2 className="text-2xl font-semibold text-gray-100 mb-4">Glosario y metodología</h2>
            <p className="text-gray-200 mb-4">
              Los términos técnicos (DCF, WACC, reverse DCF, moat, margen de seguridad, look-ahead, owner earnings,
              TAM/SAM/SOM, ROIC, VaR, drawdown, Sharpe) llevan un tooltip con su definición dondequiera que aparecen.
              Los motores de valoración con sus supuestos, las fuentes de datos (Finnhub, Yahoo Finance, SEC EDGAR),
              los límites y los costes están documentados en{' '}
              <Link href="/metodologia" className="text-teal-400 underline underline-offset-4 hover:text-teal-300">
                /metodologia
              </Link>.
            </p>
          </section>
        </div>
      )}

      {/* Community Tab */}
      {activeTab === 'community' && (
        <section className="bg-gradient-to-r from-blue-900/50 to-purple-900/50 rounded-lg p-8 text-center">
          <h2 className="text-2xl font-bold text-gray-100 mb-4">Contacto</h2>
          <p className="text-gray-300 mb-6">
            ¿Tienes preguntas o sugerencias? Estamos aquí para ayudarte.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <a
                  href={`mailto:${SUPPORT_EMAIL}`}
                  className="bg-gray-800 text-gray-200 px-6 py-3 rounded-lg hover:bg-gray-700 transition-colors text-center inline-block"
              >
                  Enviar email a {SUPPORT_EMAIL}
              </a>
          </div>
        </section>
      )}
    </div>
  );
}
