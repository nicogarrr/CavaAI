import { Metadata } from 'next';
import HelpTabs from '@/components/help/HelpTabs';

export const metadata: Metadata = {
  title: 'Help Center - OpenStock',
  description: 'Free help, API documentation, and community support - no barriers, just guidance',
};

export default function HelpPage() {
  return <HelpTabs />;
}
