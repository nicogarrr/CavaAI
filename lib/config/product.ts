import { Database, FileSearch, GitBranch, type LucideIcon } from 'lucide-react';

export type ProductModule = {
    icon: LucideIcon;
    title: string;
    description: string;
};

/**
 * Los tres modulos del producto, en UNA sola lista.
 *
 * Antes vivian duplicados dentro de `app/(auth)/layout.tsx`: la landing, la
 * pantalla de acceso y el panel de la derecha de auth.tenian cada uno su
 * propia copia, y cualquier retoque de copy se aplicaba a una de ellas. Ahora
 * los tres importan de aqui, asi que no pueden desincronizarse.
 */
export const productModules: ProductModule[] = [
    { icon: FileSearch, title: 'Evidencia', description: 'Cada hecho y afirmación conserva su fuente.' },
    { icon: Database, title: 'Modelo a largo plazo', description: 'Motores y supuestos adaptados a cada empresa.' },
    { icon: GitBranch, title: 'Expectativa frente a realidad', description: 'Cada resultado revisa su previsión.' },
];

/**
 * El flujo que resume el producto, usado como titular de la demo publica.
 * Vive aqui para que la landing y la pantalla de acceso digan lo mismo.
 */
export const productChain = 'Evidencia → Modelo → Tesis';

/**
 * Si el alta de cuentas esta abierta.
 *
 * Refleja EXACTAMENTE la regla de `lib/better-auth/auth.ts`:
 *   signup cerrado = NODE_ENV === 'production' && ALLOW_PUBLIC_SIGNUP !== 'true'
 * (ver `signUpDisabled`). No se inventa una regla nueva: el servidor rechaza
 * el alta con esa misma condicion, asi que la landing y los formularios de
 * acceso pueden anticiparlo en lugar de dejar que el usuario descubra el
 * bloqueo al enviar el formulario.
 *
 * OJO: `ALLOW_PUBLIC_SIGNUP` no es `NEXT_PUBLIC_*`, asi que solo se puede
 * llamar desde un SERVER component. En cliente daria siempre `undefined`.
 * Si un cliente necesita el dato, que lo pase el layout como prop.
 */
export function isPublicSignUpOpen(): boolean {
    return process.env.NODE_ENV !== 'production' || process.env.ALLOW_PUBLIC_SIGNUP === 'true';
}
