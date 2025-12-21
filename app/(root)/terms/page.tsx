import { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Términos de Servicio - JLCavaAI',
  description: 'Términos de servicio justos - construidos sobre confianza y transparencia',
};

// Forzar renderizado dinámico
export const dynamic = 'force-dynamic';

export default function TermsPage() {
  return (
    <div className="container mx-auto px-4 py-12 max-w-4xl">
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-gray-100 mb-4">Términos de Servicio</h1>
        <p className="text-gray-300 mb-4">
          Última actualización: Diciembre 2024
        </p>
        <div className="bg-green-900 border border-green-700 rounded-lg p-4">
          <p className="text-green-200 text-sm">
            🤝 <strong>Escrito en lenguaje claro:</strong> Sin jerga legal. Estos términos están diseñados para ser justos y comprensibles.
          </p>
        </div>
      </div>

      <div className="prose prose-lg max-w-none">
        {/* Our Approach */}
        <section className="mb-8 bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h2 className="text-2xl font-semibold text-gray-100 mb-4">🌟 Nuestro Enfoque</h2>
          <p className="text-gray-200 mb-4">
            Creemos que los términos de servicio deben proteger tanto a usuarios como a creadores sin ser explotadores.
          </p>
          <ul className="text-gray-200 space-y-2">
            <li>✅ <strong>Sin Trucos:</strong> Lo que ves es lo que obtienes</li>
            <li>✅ <strong>Uso Justo:</strong> Límites razonables que protegen a todos</li>
            <li>✅ <strong>Transparencia:</strong> Comunicación clara sobre cambios</li>
          </ul>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold text-gray-100 mb-4">🎯 Lo Básico</h2>
          <p className="text-gray-200 mb-4">
            Al usar JLCavaAI, esto es lo que esperamos:
          </p>
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
            <ul className="text-gray-200 space-y-3">
              <li>💙 <strong>Uso Respetuoso:</strong> Usa JLCavaAI para aprender y crecer</li>
              <li>🎓 <strong>Enfoque Educativo:</strong> Perfecto para estudiantes y aprendizaje</li>
              <li>🔓 <strong>Uso Personal:</strong> Diseñado para uso personal y educativo</li>
            </ul>
          </div>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold text-gray-100 mb-4">🛡️ Descargo de Responsabilidad de Inversión</h2>
          <div className="bg-yellow-900 border border-yellow-700 rounded-lg p-6">
            <p className="text-yellow-200 font-medium mb-2">Importante:</p>
            <div className="text-gray-200 space-y-3">
              <p>
                <strong>JLCavaAI es una herramienta educativa y de análisis, no asesoramiento de inversión.</strong>
                Proporcionamos datos y herramientas para ayudarte a tomar decisiones informadas, pero las decisiones son tuyas.
              </p>
              <p>
                <strong>No somos asesores financieros.</strong> Somos desarrolladores que construyeron herramientas que deseaban tener cuando aprendían sobre inversión.
              </p>
              <p>
                <strong>Siempre haz tu propia investigación.</strong> Usa múltiples fuentes, consulta profesionales, y nunca inviertas más de lo que puedes permitirte perder.
              </p>
            </div>
          </div>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold text-gray-100 mb-4">👥 Tu Cuenta y Responsabilidades</h2>
          <p className="text-gray-200 mb-4">
            Confiamos en que serás un buen usuario. Esto es lo que pedimos:
          </p>
          <div className="grid md:grid-cols-2 gap-4">
            <div className="bg-blue-900 border border-blue-700 rounded-lg p-4">
              <h3 className="font-semibold text-blue-200 mb-2">✨ Lo que Esperamos</h3>
              <ul className="text-blue-200 text-sm space-y-1">
                <li>• Reportar bugs y sugerir mejoras</li>
                <li>• Mantener tu información actualizada</li>
                <li>• Usar la plataforma para aprender</li>
              </ul>
            </div>
            <div className="bg-red-900 border border-red-700 rounded-lg p-4">
              <h3 className="font-semibold text-red-200 mb-2">❌ Lo que No Permitimos</h3>
              <ul className="text-red-200 text-sm space-y-1">
                <li>• Compartir cuentas</li>
                <li>• Intentar explotar el sistema</li>
                <li>• Usar la plataforma para actividades ilegales</li>
              </ul>
            </div>
          </div>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold text-gray-100 mb-4">📊 Datos y Contenido</h2>
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
            <p className="text-gray-200 mb-4">
              <strong>Tus datos te pertenecen.</strong> Proporcionamos herramientas para exportar todo en cualquier momento.
            </p>
            <p className="text-gray-200 mb-4">
              <strong>Los datos de mercado provienen de fuentes con licencia.</strong> Aunque los proporcionamos gratuitamente, por favor respeta que están destinados a uso personal y aprendizaje.
            </p>
          </div>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold text-gray-100 mb-4">🔧 Disponibilidad del Servicio</h2>
          <p className="text-gray-200 mb-4">
            Estamos comprometidos a mantener JLCavaAI funcionando:
          </p>
          <ul className="text-gray-200 space-y-2 ml-6">
            <li>• Apuntamos a alta disponibilidad, pero pueden ocurrir interrupciones</li>
            <li>• Daremos aviso previo para mantenimiento planificado</li>
            <li>• Las interrupciones mayores serán comunicadas</li>
          </ul>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold text-gray-100 mb-4">🔄 Cambios a Estos Términos</h2>
          <div className="bg-purple-900 border border-purple-700 rounded-lg p-6">
            <p className="text-purple-200 mb-3">
              <strong>Transparencia en cambios:</strong>
            </p>
            <ul className="text-gray-200 space-y-2">
              <li>• Explicación clara de qué cambia y por qué</li>
              <li>• Aviso previo razonable</li>
            </ul>
          </div>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold text-gray-100 mb-4">🤔 ¿Preguntas?</h2>
          <p className="text-gray-200 mb-4">
            Los documentos legales no deberían ser misteriosos. Si algo aquí te confunde o parece injusto, hablemos.
          </p>
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
            <p className="text-gray-200">
              <strong>Contacto:</strong>{' '}
              <a href="mailto:soporte@jlcavaai.com" className="text-blue-400 hover:text-blue-300">
                soporte@jlcavaai.com
              </a>
            </p>
          </div>
        </section>

        <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 text-center">
          <h3 className="text-xl font-semibold text-gray-100 mb-3">Gracias por usar JLCavaAI</h3>
          <p className="text-gray-200 mb-2">
            Construimos herramientas que empoderan a las personas y crean conocimiento accesible para todos.
          </p>
          <p className="text-gray-300 text-sm">
            Gracias por ser parte de nuestra comunidad. 🚀
          </p>
          <p className="text-gray-500 text-xs mt-4">
            © 2025 Nicolas Iglesias Garcia. Todos los derechos reservados.
          </p>
        </div>
      </div>
    </div>
  );
}
