import type { Metadata } from 'next';
import Link from 'next/link';
import React from 'react';
import { headers } from 'next/headers';
import { getAuth } from '@/lib/better-auth/auth';
import { CavaAIWordmark } from '@/components/CavaAIWordmark';
import { Button } from '@/components/ui/button';
import { SUPPORT_EMAIL } from '@/lib/config/brand';
import { isPublicSignUpOpen } from '@/lib/config/product';

/**
 * Shell de las paginas publicas: landing, metodologia, terminos y ayuda.
 *
 * Es un grupo de rutas aparte de `(root)` porque la exigibilidad cambia:
 * `(root)` exige sesion (`requireAuthenticatedUser`) y por eso un visitante sin
 * cuenta no podia ni leer los terminos.
 *
 * Aqui la sesion NO expulsa a nadie: un usuario que ya ha entrado debe poder
 * leer la ayuda y los terminos desde el menu de la app sin que le boten a `/`.
 * Solo cambia el CTA de la cabecera ("Iniciar sesion" <-> "Ir a mi panel").
 */

// `headers()` en la comprobacion de sesion obliga a render dinamico.
export const dynamic = 'force-dynamic';
export const revalidate = 0;

/**
 * La raiz declara `robots: { index: false }` porque la app autenticada es una
 * herramienta privada. Los metadatos anidados reemplazan campos, asi que
 * declarar aqui `robots` devuelve el indice SOLO a este arbol: `/`, `/terms`,
 * `/metodologia` y `/help`. El resto de la app sigue heredando el noindex de
 * `app/layout.tsx`.
 */
export const metadata: Metadata = {
    robots: { index: true, follow: true },
};

const legalLinks = [
    { href: '/metodologia', label: 'Metodología' },
    { href: '/terms', label: 'Términos' },
    { href: '/help', label: 'Ayuda' },
];

const Layout = async ({ children }: { children: React.ReactNode }) => {
    // Mismo criterio que `app/(auth)/layout.tsx`: en los e2e con
    // E2E_AUTH_BYPASS se acepta que no haya sesion real. El `.catch` importa:
    // si Mongo no responde, estas paginas deben seguir leyendose. Una caida de
    // base de datos no puede convertir los terminos legales en un 500.
    const browserTestBypass = process.env.E2E_AUTH_BYPASS === '1' && process.env.NODE_ENV !== 'production';
    let signedIn = false;
    if (!browserTestBypass) {
        const auth = await getAuth().catch(() => null);
        const session = auth ? await auth.api.getSession({ headers: await headers() }).catch(() => null) : null;
        signedIn = Boolean(session?.user);
    }

    const signUpOpen = isPublicSignUpOpen() && !signedIn;

    return (
        <div className="public-shell">
            <a href="#content" className="skip-link">Saltar al contenido</a>

            <header className="public-header">
                <div className="container public-header-inner">
                    <Link href="/" className="flex min-h-11 items-center" aria-label="CavaAI, inicio">
                        <CavaAIWordmark />
                    </Link>
                    <nav aria-label="Páginas de CavaAI" className="public-nav">
                        {legalLinks.map((link) => (
                            <Link key={link.href} href={link.href} className="public-nav-link">
                                {link.label}
                            </Link>
                        ))}
                    </nav>
                    <div className="flex items-center gap-2">
                        {signedIn ? (
                            <Button asChild className="h-11" size="sm">
                                <Link href="/">Ir a mi panel</Link>
                            </Button>
                        ) : (
                            <>
                                <Button asChild className="h-11" size="sm" variant="outline">
                                    <Link href="/sign-in">Iniciar sesión</Link>
                                </Button>
                                {signUpOpen ? (
                                    <Button asChild className="h-11" size="sm">
                                        <Link href="/sign-up">Crear cuenta</Link>
                                    </Button>
                                ) : null}
                            </>
                        )}
                    </div>
                </div>
            </header>

            {/* Cada pagina publica declara su unico <main id="content">; el
                layout no añade otro landmark ni envuelve a los hijos. */}
            <div className="public-content">{children}</div>

            <footer className="public-footer">
                <div className="container public-footer-inner">
                    <div className="max-w-sm">
                        <p className="font-medium text-gray-300">CavaAI</p>
                        <p className="mt-1">
                            Herramienta educativa de análisis: CavaAI no da asesoramiento de inversión y
                            las decisiones son tuyas.
                        </p>
                    </div>
                    <nav aria-label="Enlaces legales" className="flex flex-col items-start gap-2 sm:items-end">
                        {legalLinks.map((link) => (
                            <Link key={link.href} href={link.href} className="public-footer-link">
                                {link.label}
                            </Link>
                        ))}
                        <a href={`mailto:${SUPPORT_EMAIL}`} className="public-footer-link">
                            {SUPPORT_EMAIL}
                        </a>
                    </nav>
                </div>
            </footer>
        </div>
    );
};

export default Layout;
