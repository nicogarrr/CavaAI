import KnowledgeBaseManager from '@/components/knowledge/KnowledgeBaseManager';

export const metadata = {
    title: 'Base de Conocimiento | CavaAI',
    description: 'Gestiona tu base de conocimiento de Value Investing',
};

export default function KnowledgePage() {
    return (
        <div className="container max-w-5xl py-8 px-4">
            <KnowledgeBaseManager />
        </div>
    );
}
