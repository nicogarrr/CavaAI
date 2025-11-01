import mongoose from "mongoose";

const MONGODB_URI = process.env.MONGODB_URI;

declare global {
    var mongooseCache: {
        conn: typeof mongoose | null;
        promise: Promise<typeof mongoose> | null;
    }
}

let cached = global.mongooseCache;

if (!cached){
    cached = global.mongooseCache = { conn: null, promise: null };
}

export const connectToDatabase = async () => {
    if(!MONGODB_URI){
        throw new Error("MongoDB URI is missing. Por favor, configura MONGODB_URI en tu archivo .env");
    }

    if(cached.conn) return cached.conn;

    if(!cached.promise) {
        cached.promise = mongoose.connect(MONGODB_URI, {
            bufferCommands: false,
            serverSelectionTimeoutMS: 30000, // Timeout de 30 segundos para dar tiempo a que se propaguen los cambios
            connectTimeoutMS: 30000,
        });
    }

    try{
        cached.conn = await cached.promise;
    }
    catch(err: any){
        cached.promise = null;
        
        // Mensaje de error más descriptivo
        if(err?.name === 'MongooseServerSelectionError' || err?.message?.includes('could not connect')) {
            throw new Error(
                `No se pudo conectar a MongoDB Atlas. ` +
                `Razones comunes: ` +
                `1) Tu IP no está en la whitelist de MongoDB Atlas - ` +
                `ve a Network Access y agrega tu IP o permite 0.0.0.0/0 para desarrollo. ` +
                `2) La URI de conexión es incorrecta. ` +
                `Error original: ${err.message}`
            );
        }
        
        throw err;
    }

    console.log(`MongoDB Connected successfully in ${process.env.NODE_ENV}`);
    return cached.conn;
}