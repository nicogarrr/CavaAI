import { Metadata } from 'next';
import HelpTabs from '@/components/help/HelpTabs';

export const metadata: Metadata = {
  title: 'Centro de ayuda',
  description: 'Ayuda gratuita, documentacion de la API y soporte de la comunidad: sin barreras, solo orientacion',
  // Página pública: el centro de ayuda se lee sin iniciar sesión, aunque los
  // módulos que documenta (research, cartera, ProPicks) sí exijan cuenta.
  robots: { index: true, follow: true },
};

// Forzar renderizado dinámico
export const dynamic = 'force-dynamic';

export default function HelpPage() {
  return <HelpTabs />;
}
