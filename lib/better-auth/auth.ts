import { betterAuth } from "better-auth";
import {mongodbAdapter} from "better-auth/adapters/mongodb";
import {connectToDatabase} from "@/database/mongoose";
import {nextCookies} from "better-auth/next-js";


let authInstance: ReturnType<typeof betterAuth> | null = null;


export const getAuth = async () => {
    if(authInstance) {
        return authInstance;
    }

    try {
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
                    secret: process.env.BETTER_AUTH_SECRET || 'dummy-secret-for-build',
                    baseURL: process.env.BETTER_AUTH_URL || 'REDACTED_BY_AUDIT',
                    emailAndPassword: {
                        enabled: true,
                        disableSignUp: false,
                        requireEmailVerification: false,
                        minPasswordLength: 8,
                        maxPasswordLength: 128,
                        autoSignIn: true,
                    },
                    plugins: [nextCookies()],
                }) as any;
                
                return authInstance;
            }
            
            // En runtime, si no hay conexión a MongoDB, creamos una instancia sin base de datos como fallback
            // Esto permite que la aplicación funcione aunque MongoDB no esté disponible
            console.warn('⚠️ MongoDB connection not available, using memory adapter');
            authInstance = betterAuth({
                secret: process.env.BETTER_AUTH_SECRET || 'fallback-secret',
                baseURL: process.env.BETTER_AUTH_URL || process.env.VERCEL_URL || 'REDACTED_BY_AUDIT',
                emailAndPassword: {
                    enabled: true,
                    disableSignUp: false,
                    requireEmailVerification: false,
                    minPasswordLength: 8,
                    maxPasswordLength: 128,
                    autoSignIn: true,
                },
                plugins: [nextCookies()],
            }) as any;
            
            return authInstance;
        }

        const db = mongoose.connection;

        authInstance = betterAuth({
            database: mongodbAdapter(db as any),
           secret: process.env.BETTER_AUTH_SECRET,
            baseURL: process.env.BETTER_AUTH_URL,
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
    } catch (error: any) {
        // Proporcionar mensaje más útil
        if (error.message?.includes('MongoDB') || error.message?.includes('could not connect')) {
            console.error('\n❌ Error de conexión a MongoDB Atlas');
            console.error('📋 Pasos para solucionar:');
            console.error('1. Ve a: https://cloud.mongodb.com/');
            console.error('2. Selecciona tu proyecto');
            console.error('3. Ve a "Network Access" en el menú lateral');
            console.error('4. Click en "Add IP Address"');
            console.error('5. Para desarrollo: agrega "0.0.0.0/0" (permite todas las IPs)');
            console.error('   Para producción: agrega tu IP específica');
            console.error('6. Espera 1-2 minutos y vuelve a intentar\n');
            console.error('📄 Ver instrucciones completas en: MONGODB_SETUP.md\n');
            
            // En lugar de lanzar error, creamos una instancia fallback
            console.warn('⚠️ Using fallback auth instance without MongoDB');
            authInstance = betterAuth({
                secret: process.env.BETTER_AUTH_SECRET || 'fallback-secret',
                baseURL: process.env.BETTER_AUTH_URL || process.env.VERCEL_URL || 'REDACTED_BY_AUDIT',
                emailAndPassword: {
                    enabled: true,
                    disableSignUp: false,
                    requireEmailVerification: false,
                    minPasswordLength: 8,
                    maxPasswordLength: 128,
                    autoSignIn: true,
                },
                plugins: [nextCookies()],
            }) as any;
            
            return authInstance;
        }
        throw error;
    }
}
