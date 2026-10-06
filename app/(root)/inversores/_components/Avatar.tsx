/** Inicial en un círculo: sin fotos hasta tener licencia libre con atribución. */
export function InvestorAvatar({ name, size = 'md' }: { name: string; size?: 'md' | 'lg' }) {
    const initial = name.trim().charAt(0).toUpperCase();
    const box = size === 'lg' ? 'h-16 w-16 text-2xl' : 'h-11 w-11 text-base';
    return (
        <span
            aria-hidden="true"
            className={`flex ${box} shrink-0 items-center justify-center rounded-full bg-lime-400/10 font-semibold text-lime-300`}
        >
            {initial}
        </span>
    );
}
