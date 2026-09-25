import { Metadata } from 'next';
import HelpTabs from '@/components/help/HelpTabs';

export const metadata: Metadata = {
  title: 'Centro de ayuda',
  description: 'Ayuda gratuita, documentacion de la API y soporte de la comunidad: sin barreras, solo orientacion',
};

// Forzar renderizado dinámico
export const dynamic = 'force-dynamic';

export default function HelpPage() {
  return <HelpTabs />;
}
