import type { Metadata } from 'next';

import { INVESTOR_CHANNELS, type ChannelCategory } from './channels';

export const metadata: Metadata = {
    title: 'Canales de inversión',
    description: 'Canales de YouTube de inversión con enlace directo, fuente y fecha de comprobación.',
};

const SECTIONS: { category: ChannelCategory; title: string }[] = [
    { category: 'inversion', title: 'Inversión y finanzas' },
    { category: 'negocio', title: 'Negocio y tecnología' },
    { category: 'referencia', title: 'Referencias en inglés' },
    { category: 'empresa', title: 'Empresas' },
];

export default function ChannelsPage() {
    return (
        <main id="content" tabIndex={-1} className="mx-auto flex w-full min-w-0 max-w-5xl flex-col gap-12 overflow-x-clip py-6">
            <header className="flex flex-col gap-3">
                <h1 className="text-3xl font-semibold text-gray-100">Canales de inversión</h1>
            </header>
            {SECTIONS.map((section) => {
                const items = INVESTOR_CHANNELS.filter((channel) => channel.category === section.category);
                return (
                    <section className="flex flex-col gap-3" key={section.category}>
                        <h2 className="text-xl font-semibold text-gray-100">{section.title}</h2>
                        <ul className="flex flex-col divide-y divide-gray-900">
                            {items.map((channel) => (
                                <li className="flex flex-col gap-1 py-3" key={channel.url}>
                                    <a
                                        className="text-base font-medium text-gray-100 underline-offset-2 hover:underline"
                                        href={channel.url}
                                        rel="noreferrer"
                                        target="_blank"
                                    >
                                        {channel.name}
                                    </a>
                                    <p className="text-xs text-gray-500">
                                        {channel.handle} · {channel.language === 'es' ? 'Español' : 'Inglés'} · {channel.source}
                                        {channel.note ? ` · ${channel.note}` : ''}
                                    </p>
                                </li>
                            ))}
                        </ul>
                    </section>
                );
            })}
        </main>
    );
}
