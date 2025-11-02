import { Metadata } from 'next';
import HelpTabs from '@/components/help/HelpTabs';

export const metadata: Metadata = {
  title: 'Help Center - OpenStock',
  description: 'Free help, API documentation, and community support - no barriers, just guidance',
};

// Forzar renderizado dinámico
export const dynamic = 'force-dynamic';

export default function HelpPage() {
  return <HelpTabs />;
}
