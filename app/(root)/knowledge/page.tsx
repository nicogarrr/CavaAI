import { permanentRedirect } from 'next/navigation';

export default function LegacyKnowledgeRedirect() {
    permanentRedirect('/research/sources');
}
