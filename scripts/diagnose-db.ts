import mongoose from 'mongoose';

async function diagnoseConnection() {
    const uri = process.env.MONGODB_URI;
    
    if (!uri) {
        console.error('❌ ERROR: MONGODB_URI no está configurado en .env');
        process.exit(1);
    }

    console.log('🔍 Diagnóstico de conexión a MongoDB Atlas\n');
    console.log('📋 Connection String (sin contraseña):');
    // Ocultar contraseña en el log
    const hiddenUri = uri.replace(/:([^:@]+)@/, ':***@');
    console.log(`   ${hiddenUri}\n`);

    console.log('🔌 Intentando conectar...\n');

    try {
        const startTime = Date.now();
        
        await mongoose.connect(uri, {
            bufferCommands: false,
            serverSelectionTimeoutMS: 30000,
            connectTimeoutMS: 30000,
        });

        const elapsed = Date.now() - startTime;
        const dbName = mongoose.connection?.name || '(unknown)';
        const host = mongoose.connection?.host || '(unknown)';
        const readyState = mongoose.connection?.readyState;

        console.log('✅ Conexión exitosa!');
        console.log(`   Base de datos: ${dbName}`);
        console.log(`   Host: ${host}`);
        console.log(`   Estado: ${readyState === 1 ? 'Conectado' : 'Desconectado'}`);
        console.log(`   Tiempo de conexión: ${elapsed}ms\n`);

        // Probar una operación simple
        try {
            if (mongoose.connection.db) {
                await mongoose.connection.db.admin().ping();
                console.log('✅ Ping exitoso - El servidor responde correctamente\n');
            }
        } catch (pingError: any) {
            console.error('⚠️  Ping falló:', pingError.message);
        }

        await mongoose.connection.close();
        console.log('✅ Conexión cerrada correctamente');
        
        process.exit(0);
    } catch (error: any) {
        console.error('\n❌ Error de conexión:\n');
        console.error(`   Tipo: ${error.name}`);
        console.error(`   Mensaje: ${error.message}\n`);

        if (error.message?.includes('authentication failed') || error.message?.includes('auth failed')) {
            console.error('🔐 PROBLEMA: Autenticación falló');
            console.error('   - Verifica tu usuario y contraseña en el connection string');
            console.error('   - Asegúrate de que el usuario tenga permisos en la base de datos\n');
        }

        if (error.message?.includes('could not connect') || error.message?.includes('IP')) {
            console.error('🌐 PROBLEMA: Acceso de red bloqueado');
            console.error('   - Ve a: https://cloud.mongodb.com/');
            console.error('   - Selecciona tu proyecto');
            console.error('   - Ve a "Network Access"');
            console.error('   - Verifica que tu IP o 0.0.0.0/0 esté en la lista');
            console.error('   - Espera 2-3 minutos después de agregar IPs\n');
        }

        if (error.message?.includes('bad auth') || error.message?.includes('Authentication failed')) {
            console.error('🔑 PROBLEMA: Credenciales incorrectas');
            console.error('   - Verifica usuario y contraseña en MongoDB Atlas');
            console.error('   - Asegúrate de que el usuario tenga acceso a la base de datos\n');
        }

        console.error('💡 Soluciones comunes:');
        console.error('   1. Verifica Network Access en MongoDB Atlas');
        console.error('   2. Verifica tus credenciales de usuario');
        console.error('   3. Verifica que el cluster esté activo');
        console.error('   4. Espera 2-3 minutos después de cambiar Network Access\n');

        process.exit(1);
    }
}

diagnoseConnection();

