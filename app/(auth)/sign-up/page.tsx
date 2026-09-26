import SignUpForm from '@/components/forms/SignUpForm';
import { isPublicSignUpOpen } from '@/lib/config/product';

// El formulario es un componente de cliente (react-hook-form) y necesita saber
// si el alta está abierta, pero `ALLOW_PUBLIC_SIGNUP` no es `NEXT_PUBLIC_*`:
// en el cliente siempre valdría `undefined`. La página se queda como capa de
// servidor y le pasa el dato ya resuelto.
export const dynamic = 'force-dynamic';

export default function SignUp() {
    return <SignUpForm signUpOpen={isPublicSignUpOpen()} />;
}
