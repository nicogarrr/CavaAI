import Image from 'next/image';

import { INVESTOR_PHOTOS } from './photos';

/** Foto con licencia libre verificada (ver photos.ts); si no la hay, la inicial en un círculo. */
export function InvestorAvatar({ name, slug, size = 'md' }: { name: string; slug?: string; size?: 'md' | 'lg' }) {
    const photo = slug ? INVESTOR_PHOTOS[slug] : undefined;
    const px = size === 'lg' ? 64 : 44;
    const box = size === 'lg' ? 'h-16 w-16 text-2xl' : 'h-11 w-11 text-base';
    if (photo) {
        return (
            <Image
                alt={`Foto de ${name}`}
                className={`${box} shrink-0 rounded-full object-cover object-top`}
                height={px}
                src={photo.src}
                width={px}
            />
        );
    }
    const initial = name.trim().charAt(0).toUpperCase();
    return (
        <span
            aria-hidden="true"
            className={`flex ${box} shrink-0 items-center justify-center rounded-full bg-lime-400/10 font-semibold text-lime-300`}
        >
            {initial}
        </span>
    );
}
