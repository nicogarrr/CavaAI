import { betterAuth } from "better-auth";
import {mongodbAdapter} from "better-auth/adapters/mongodb";
import {connectToDatabase} from "@/database/mongoose";
import {nextCookies} from "better-auth/next-js";
import {env} from "@/lib/env";
import {DatabaseError, toAppError} from "@/lib/types/errors";


const authOptions = {
    emailAndPassword: {
        enabled: true,
        disableSignUp: false,
        requireEmailVerification: false,
        minPasswordLength: 8,
        maxPasswordLength: 128,
        autoSignIn: true,
    },
    plugins: [nextCookies()],
};

const createAuthInstance = (database?: ReturnType<typeof mongodbAdapter>) => betterAuth({
    ...(database ? { database } : {}),
    secret: env.BETTER_AUTH_SECRET,
    baseURL: env.BETTER_AUTH_URL || env.VERCEL_URL || 'http://localhost:3000',
    ...authOptions,
});

type AuthInstance = ReturnType<typeof createAuthInstance>;

let authInstance: AuthInstance | null = null;


export const getAuth = async (): Promise<AuthInstance> => {
    if(authInstance) {
        return authInstance;
    }

    try {
        // Validar que BETTER_AUTH_SECRET existe y no es un valor por defecto inseguro
        if (!env.BETTER_AUTH_SECRET) {
            throw new Error('BETTER_AUTH_SECRET is required. Please configure it in your .env file.');
        }

        const mongoose = await connectToDatabase();
        
        // Durante el build, si connectToDatabase retorna null, creamos una instancia sin base de datos
        // Esto permite que el build complete sin necesidad de MongoDB
        if (!mongoose || !mongoose.connection) {
            const isBuildTime = process.env.NEXT_PHASE === 'phase-production-build' || 
                               process.env.NEXT_PHASE === 'phase-development-build';
            
            if (isBuildTime) {
                // Durante el build, creamos una instancia mock sin base de datos
                // Esto permite que Next.js complete el build
                authInstance = createAuthInstance();
                
                return authInstance;
            }
            
            throw new DatabaseError('MongoDB connection is required at runtime');
        }

        const db = mongoose.connection;

        authInstance = createAuthInstance(mongodbAdapter(db));

        return authInstance;
    } catch (error: unknown) {
        const appError = toAppError(error);
        
        // Proporcionar mensaje más útil para errores de MongoDB
        if (appError.message.includes('MongoDB') || appError.message.includes('could not connect')) {
            console.error('\n❌ Error de conexión a MongoDB Atlas');
            console.error('📋 Pasos para solucionar:');
            console.error('1. Ve a: https://cloud.mongodb.com/');
            console.error('2. Selecciona tu proyecto');
            console.error('3. Ve a "Network Access" en el menú lateral');
            console.error('4. Click en "Add IP Address"');
            console.error('5. Para desarrollo: agrega "0.0.0.0/0" (permite todas las IPs)');
            console.error('   Para producción: agrega tu IP específica');
            console.error('6. Espera 1-2 minutos y vuelve a intentar\n');
            
            throw new DatabaseError('MongoDB connection is required at runtime', appError);
        }
        
        throw appError;
    }
}
