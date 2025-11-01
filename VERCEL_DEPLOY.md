# Guía de Despliegue en Vercel

## Pasos para desplegar OpenStock en Vercel

### 1. Preparación

1. **Asegúrate de tener tu código en un repositorio Git** (GitHub, GitLab, Bitbucket)
2. **Inicia sesión en Vercel**: [https://vercel.com](https://vercel.com)

### 2. Crear un nuevo proyecto en Vercel

1. Ve al dashboard de Vercel
2. Click en **"Add New..."** > **"Project"**
3. Importa tu repositorio de Git
4. Selecciona el repositorio donde está tu proyecto OpenStock

### 3. Configurar el Proyecto

#### Framework Preset
- **Framework Preset**: Next.js (debería detectarlo automáticamente)

#### Build Command
- **Build Command**: `npm run build` (por defecto)
- Vercel detectará automáticamente Next.js y usará el comando correcto

#### Output Directory
- **Output Directory**: `.next` (por defecto)
- No es necesario cambiarlo, Vercel lo detecta automáticamente

#### Install Command
- **Install Command**: `npm install` (por defecto)

### 4. Configurar Variables de Entorno

En la página de configuración del proyecto, ve a **"Environment Variables"** y añade todas estas variables:

#### Variables Requeridas

```
MONGODB_URI
```
- Tu connection string de MongoDB Atlas
- Ejemplo: `mongodb+srv://usuario:password@cluster.mongodb.net/openstock?retryWrites=true&w=majority`

```
BETTER_AUTH_SECRET
```
- Genera un secret aleatorio (mínimo 32 caracteres)
- Puedes generar uno aquí: `openssl rand -base64 32`
- O usar: `node -e "console.log(require('crypto').randomBytes(32).toString('base64'))"`

```
BETTER_AUTH_URL
```
- URL de tu aplicación en Vercel (se configurará después del despliegue)
- Ejemplo: `https://tu-proyecto.vercel.app`
- También añádela como `NEXT_PUBLIC_BETTER_AUTH_URL` con el mismo valor

#### Variables de APIs

```
FINNHUB_API_KEY
```
- Tu API key de Finnhub
- Obtén una gratis en: [https://finnhub.io/register](https://finnhub.io/register)

```
NEXT_PUBLIC_FINNHUB_API_KEY
```
- La misma API key de Finnhub (para uso en cliente si es necesario)

```
GEMINI_API_KEY
```
- Tu API key de Google Gemini
- Obtén una en: [https://makersuite.google.com/app/apikey](https://makersuite.google.com/app/apikey)

```
GOOGLE_API_KEY
```
- Opcional: misma que GEMINI_API_KEY (para compatibilidad)

#### Variables Opcionales de Gemini

```
GEMINI_MODEL=gemini-2.5-flash
GEMINI_MODEL_THESIS=gemini-2.5-flash
GEMINI_MODEL_DCF=gemini-2.5-flash
```
- Modelos de Gemini a usar (por defecto: gemini-2.5-flash)

#### Variables de Email (Opcional)

```
NODEMAILER_EMAIL
```
- Tu email de Gmail (o servidor SMTP)

```
NODEMAILER_PASSWORD
```
- Contraseña de aplicación de Gmail (no tu contraseña normal)
- Cómo crear contraseña de aplicación: [https://support.google.com/accounts/answer/185833](https://support.google.com/accounts/answer/185833)

### 5. Configurar Entornos

Para cada variable, selecciona en qué entornos aplica:
- ✅ **Production**: Para producción
- ✅ **Preview**: Para preview deployments
- ✅ **Development**: Para desarrollo local (opcional)

### 6. Desplegar

1. Click en **"Deploy"**
2. Vercel comenzará el proceso de build
3. Espera a que termine (puede tomar 2-5 minutos)

### 7. Actualizar BETTER_AUTH_URL

Después del primer despliegue:

1. Ve a la página de **"Settings"** > **"Environment Variables"**
2. Actualiza `BETTER_AUTH_URL` y `NEXT_PUBLIC_BETTER_AUTH_URL` con la URL real de tu proyecto
3. Ejemplo: `https://tu-proyecto.vercel.app`
4. **Redeploy** el proyecto para que los cambios surtan efecto

### 8. Configurar MongoDB Atlas para Vercel

1. Ve a tu MongoDB Atlas Dashboard
2. **Network Access** > **IP Access List**
3. Añade la IP de Vercel: `0.0.0.0/0` (permite todas las IPs)
   - **Nota**: Para producción, considera restringir a IPs específicas de Vercel

### 9. Verificar el Despliegue

1. Abre la URL de tu proyecto (ej: `https://tu-proyecto.vercel.app`)
2. Verifica que la aplicación carga correctamente
3. Prueba crear una cuenta y hacer login
4. Verifica que las funciones principales funcionan

## Solución de Problemas

### Error: "MongoDB connection failed"

- Verifica que `MONGODB_URI` esté correctamente configurada
- Asegúrate de que MongoDB Atlas permita conexiones desde `0.0.0.0/0`
- Verifica que el usuario de MongoDB tenga permisos suficientes

### Error: "BETTER_AUTH_SECRET is missing"

- Asegúrate de haber añadido `BETTER_AUTH_SECRET` en Vercel
- Genera un secret nuevo y cámbialo en Vercel
- Haz un redeploy después de cambiar variables de entorno

### Error: Build fails

- Verifica los logs de build en Vercel
- Asegúrate de que `package.json` tenga todas las dependencias
- Verifica que no haya errores de TypeScript (aunque están ignorados en build)

### API Rate Limits

- El plan gratuito de Finnhub tiene límites (60 llamadas/minuto)
- Considera actualizar a un plan superior si necesitas más llamadas
- Implementa caching cuando sea posible

## Notas Importantes

1. **Turbopack**: Se usa en desarrollo local (`dev`), pero el build en Vercel usa el compilador estándar de Next.js
2. **Variables Públicas**: Variables que empiezan con `NEXT_PUBLIC_` se exponen al cliente, úsalas con cuidado
3. **Secrets**: Nunca subas archivos `.env` al repositorio, usa solo `.env.example`
4. **Dominio Personalizado**: Puedes configurar un dominio personalizado en Vercel Settings > Domains

## Próximos Pasos

- Configurar un dominio personalizado
- Configurar Inngest para procesos en segundo plano (opcional)
- Configurar monitoreo y alertas
- Optimizar imágenes y assets
- Configurar CDN para assets estáticos

---

¡Tu aplicación OpenStock estará desplegada en Vercel! 🚀

