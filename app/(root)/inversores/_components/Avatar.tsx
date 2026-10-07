import { NameAvatar } from @/components/ui/name-avatar;

import { INVESTOR_PHOTOS } from ./photos;

/** Foto con licencia libre verificada (ver photos.ts); si no la hay, iniciales con color estable por nombre. */
export function InvestorAvatar({ name, slug, size = md }: { name: string; slug?: string; size?: md | lg }) {
    const photo = slug ? INVESTOR_PHOTOS[slug] : undefined;
    return (
        <NameAvatar
            className={size === lg ? size-16 text-xl : size-11 text-sm}
            name={name}
            photoSrc={photo?.src}
            photoTitle={photo ? `Foto: ${photo.author}, ${photo.license}, vía Wikimedia Commons` : undefined}
        />
    );
}
