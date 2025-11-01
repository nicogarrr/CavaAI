# 🔧 Configuración de MongoDB Atlas - Solución Rápida

## ❌ Error Actual
```
Could not connect to any servers in your MongoDB Atlas cluster.
Your IP address is not whitelisted.
```

## ✅ Solución Rápida (2 minutos)

### Paso 1: Ir a MongoDB Atlas
1. Abre: https://cloud.mongodb.com/
2. Inicia sesión en tu cuenta

### Paso 2: Agregar IP a la Whitelist
1. En el menú lateral izquierdo, haz clic en **"Network Access"** (o "Security" → "Network Access")
2. Haz clic en el botón verde **"Add IP Address"**
3. Tienes dos opciones:

   **Opción A - Desarrollo Rápido (Recomendado para pruebas):**
   - Selecciona **"Allow Access from Anywhere"**
   - Agrega: `0.0.0.0/0`
   - Haz clic en **"Confirm"**
   - ⚠️ **Nota:** Esto permite acceso desde cualquier IP. Solo para desarrollo.

   **Opción B - Más Seguro (Producción):**
   - Obtén tu IP actual visitando: https://whatismyipaddress.com/
   - Agrega tu IP específica (ej: `123.45.67.89`)
   - Haz clic en **"Confirm"**

### Paso 3: Esperar y Verificar
- Espera **1-2 minutos** para que los cambios se propaguen
- Verifica que tu IP aparezca en la lista de Network Access

### Paso 4: Probar Conexión
```bash
cd OpenStock
npm run test:db
```

Deberías ver: `✅ OK: Connected to MongoDB`

## 📝 Verificar tu Connection String

Tu archivo `.env` debe tener:
```env
MONGODB_URI=mongodb+srv://usuario:contraseña@cluster.mongodb.net/openstock?retryWrites=true&w=majority
```

**Importante:**
- Reemplaza `usuario` y `contraseña` con tus credenciales de MongoDB Atlas
- Agrega `/openstock` antes del `?` para especificar la base de datos

## 🚀 Si sigues teniendo problemas

1. **Verifica que tu IP esté agregada:**
   - Ve a Network Access en MongoDB Atlas
   - Confirma que tu IP (o 0.0.0.0/0) aparezca en la lista

2. **Verifica tu Connection String:**
   ```bash
   # En PowerShell o CMD:
   echo $env:MONGODB_URI
   
   # Debe mostrar tu connection string completa
   ```

3. **Reinicia tu servidor de desarrollo:**
   ```bash
   # Detén el servidor (Ctrl+C) y reinícialo:
   npm run dev
   ```

## 🔒 Seguridad

- **Para Desarrollo:** `0.0.0.0/0` está bien
- **Para Producción:** Agrega solo IPs específicas de tus servidores
- **Nunca:** Compartas tu connection string públicamente

---

**¿Necesitas ayuda adicional?**
- Documentación oficial: https://www.mongodb.com/docs/atlas/security-whitelist/
- Tu cluster está en: https://cloud.mongodb.com/

