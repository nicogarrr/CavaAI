'use client';

import { useState } from 'react';
import { SUPPORT_EMAIL } from '@/lib/config/brand';

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
        <div className="bg-green-300 border border-green-200 rounded-lg p-4 max-w-2xl mx-auto">
          <p className="text-black text-sm">
            🤝 <strong>Nuestra Promesa:</strong> Cada pregunta importa. Cada principiante es bienvenido.
          </p>
        </div>
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

      {/* API Docs Tab */}
      {activeTab === 'api' && (
        <div className="space-y-8">
          <div className="mb-8">
            <h2 className="text-3xl font-bold text-gray-100 mb-4">Documentación</h2>
            <p className="text-xl text-gray-200 mb-4">
              Guía completa para usar CavaAI
            </p>
          </div>

          {/* Philosophy */}
          <section className="bg-gray-800 rounded-lg shadow-sm p-6 border">
            <h2 className="text-2xl font-semibold text-gray-100 mb-4">🌍 Nuestra Filosofía</h2>
            <p className="text-gray-200 mb-4">
              Creemos que los datos de mercado deben ser accesibles para todos - estudiantes, 
              desarrolladores y cualquiera que quiera aprender sobre finanzas sin barreras.
            </p>
            <ul className="text-gray-200 space-y-2">
              <li>✅ <strong>Accesible:</strong> Funcionalidades principales gratuitas</li>
              <li>✅ <strong>Sin Barreras:</strong> Documentación clara y simple</li>
              <li>✅ <strong>Educativo:</strong> Diseñado para aprender y crecer</li>
            </ul>
          </section>

          {/* Features */}
          <section className="bg-gray-800 rounded-lg shadow-sm p-6 border">
            <h2 className="text-2xl font-semibold text-gray-100 mb-4">🛠️ Funcionalidades</h2>
            <div className="grid md:grid-cols-2 gap-4">
              <div className="bg-green-900/30 p-4 rounded-lg">
                <h3 className="font-semibold text-green-400 mb-2">📊 Análisis de Acciones</h3>
                <p className="text-gray-300 text-sm">
                  Métricas financieras, ratios, y análisis técnico completo.
                </p>
              </div>
              <div className="bg-blue-900/30 p-4 rounded-lg">
                <h3 className="font-semibold text-blue-400 mb-2">🤖 IA Integrada</h3>
                <p className="text-gray-300 text-sm">
                  Análisis automatizado con modelos de lenguaje avanzados.
                </p>
              </div>
            </div>
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
          <p className="text-xs text-gray-400 mt-4">
            ✨ Respondemos todas las consultas lo antes posible.
          </p>
        </section>
      )}
    </div>
  );
}
