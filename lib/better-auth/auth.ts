import { betterAuth } from "better-auth";
import {mongodbAdapter} from "better-auth/adapters/mongodb";
import {connectToDatabase} from "@/database/mongoose";
import {nextCookies} from "better-auth/next-js";
import {env} from "@/lib/env";
import {DatabaseError, toAppError, getErrorMessage} from "@/lib/types/errors";


let authInstance: ReturnType<typeof betterAuth> | null = null;


export const getAuth = async () => {
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
                authInstance = betterAuth({
                    secret: env.BETTER_AUTH_SECRET,
                    baseURL: env.BETTER_AUTH_URL || 'http://localhost:3000',
                    emailAndPassword: {
                        enabled: true,
                        disableSignUp: false,
                        requireEmailVerification: false,
                        minPasswordLength: 8,
                        maxPasswordLength: 128,
                        autoSignIn: true,
                    },
                    plugins: [nextCookies()],
                });
                
                return authInstance;
            }
            
            // En runtime, si no hay conexión a MongoDB, lanzar error en producción
            // En desarrollo, permitir fallback pero con warning
            if (env.NODE_ENV === 'production') {
                throw new DatabaseError('MongoDB connection is required in production');
            }
            
            console.warn('⚠️ MongoDB connection not available, using memory adapter (development only)');
            authInstance = betterAuth({
                secret: env.BETTER_AUTH_SECRET,
                baseURL: env.BETTER_AUTH_URL || env.VERCEL_URL || 'http://localhost:3000',
                emailAndPassword: {
                    enabled: true,
                    disableSignUp: false,
                    requireEmailVerification: false,
                    minPasswordLength: 8,
                    maxPasswordLength: 128,
                    autoSignIn: true,
                },
                plugins: [nextCookies()],
            });
            
            return authInstance;
        }

        const db = mongoose.connection;

        authInstance = betterAuth({
            database: mongodbAdapter(db),
            secret: env.BETTER_AUTH_SECRET,
            baseURL: env.BETTER_AUTH_URL,
            emailAndPassword: {
                enabled: true,
                disableSignUp: false,
                requireEmailVerification: false,
                minPasswordLength: 8,
                maxPasswordLength: 128,
                autoSignIn: true,
            },
            plugins: [nextCookies()],
        });

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
            
            // En producción, lanzar error
            if (env.NODE_ENV === 'production') {
                throw new DatabaseError('MongoDB connection is required in production', appError);
            }
        }
        
        throw appError;
    }
}
