import { Metadata } from 'next';
import HelpTabs from '@/components/help/HelpTabs';

export const metadata: Metadata = {
  title: 'Centro de ayuda',
  description: 'Documentación por módulo, preguntas frecuentes y contacto de CavaAI',
  // Página pública: el centro de ayuda se lee sin iniciar sesión, aunque los
  // módulos que documenta (research, cartera, ProPicks) sí exijan cuenta.
  robots: { index: true, follow: true },
};

// Forzar renderizado dinámico
export const dynamic = 'force-dynamic';

export default function HelpPage() {
  return <HelpTabs />;
}
