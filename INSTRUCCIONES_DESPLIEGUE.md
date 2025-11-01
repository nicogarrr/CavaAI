# Instrucciones de Despliegue - OpenStock con Portfolio Tracker

## 🎉 Nueva Funcionalidad Añadida: Portfolio Tracker

Se ha añadido un sistema completo de gestión de carteras de inversión con las siguientes características:

### Características del Portfolio Tracker

1. **Gestión de Carteras**
   - Crear múltiples carteras con nombre y descripción
   - Ver todas tus carteras en un dashboard
   - Eliminar carteras cuando ya no las necesites

2. **Gestión de Posiciones**
   - Añadir posiciones con símbolo, compañía, cantidad de acciones y precio de compra
   - Ver el rendimiento en tiempo real de cada posición
   - Eliminar posiciones de las carteras

3. **Análisis de Performance**
   - Valor total invertido
   - Valor actual del portfolio
   - Ganancia/Pérdida total en USD y porcentaje
   - Análisis detallado por posición
   - Cálculo automático de P&L usando precios en tiempo real de Finnhub

4. **Interfaz Intuitiva**
   - Diseño moderno con Tailwind CSS
   - Tablas responsivas con todos los datos
   - Colores verdes para ganancias, rojos para pérdidas
   - Navegación fluida entre carteras

### Archivos Nuevos Creados

**Modelos y Lógica:**
- `database/models/portfolio.model.ts` - Modelo de datos del portfolio
- `lib/actions/portfolio.actions.ts` - Acciones del servidor para portfolios

**Páginas:**
- `app/(root)/portfolio/page.tsx` - Lista de portfolios
- `app/(root)/portfolio/[id]/page.tsx` - Detalle de portfolio individual

**Componentes:**
- `components/portfolio/PortfolioList.tsx` - Lista de carteras
- `components/portfolio/CreatePortfolioButton.tsx` - Botón para crear cartera
- `components/portfolio/PortfolioHeader.tsx` - Cabecera del portfolio
- `components/portfolio/PortfolioSummary.tsx` - Resumen de métricas
- `components/portfolio/PositionsTable.tsx` - Tabla de posiciones
- `components/portfolio/AddPositionButton.tsx` - Botón para añadir posición

**Actualizaciones:**
- `types/global.d.ts` - Tipos TypeScript para portfolios
- `lib/constants.ts` - Añadido item "Portfolio" al menú de navegación

## 📋 Configuración de MongoDB Atlas (Gratis)

Como Docker no está corriendo, la forma más sencilla es usar MongoDB Atlas (servicio cloud gratuito):

### Paso 1: Crear cuenta en MongoDB Atlas

1. Ve a [https://www.mongodb.com/cloud/atlas/register](https://www.mongodb.com/cloud/atlas/register)
2. Regístrate con tu email o Google
3. Selecciona el plan **FREE** (M0 Sandbox - 512 MB)

### Paso 2: Crear un Cluster

1. Selecciona el proveedor (AWS, Google Cloud, o Azure)
2. Elige la región más cercana a ti
3. Dale un nombre a tu cluster (ej: "OpenStock")
4. Click en "Create Deployment"

### Paso 3: Configurar Acceso

1. **Crear usuario de base de datos:**
   - Cuando te lo pida, crea un usuario con contraseña
   - Guarda el usuario y contraseña (los necesitarás para la URI)

2. **Configurar IP Whitelist:**
   - Añade tu IP actual, O para desarrollo usa `0.0.0.0/0` (permite todas las IPs)
   - **Nota:** En producción, restringe esto a IPs específicas

### Paso 4: Obtener la Connection String

1. En el dashboard de Atlas, click en "Connect"
2. Selecciona "Connect your application"
3. Copia la connection string, se verá así:
   ```
   mongodb+srv://nicoiglesiasgarcia10_db_user:89F8suxKTkXUlfNq@jlcavaai.sj0wk0l.mongodb.net/?retryWrites=true&w=majority&appName=JLCavaAI
   ```

### Paso 5: Actualizar el archivo .env

Reemplaza la línea `MONGODB_URI` en el archivo `.env` con tu connection string de Atlas:

```env
# Reemplaza <username> y <password> con tus credenciales
MONGODB_URI=mongodb+srv://tuusuario:tucontraseña@cluster0.xxxxx.mongodb.net/openstock?retryWrites=true&w=majority
```

**Nota:** Añade `/openstock` antes del `?` para especificar el nombre de la base de datos.

## 🚀 Ejecutar la Aplicación

### 1. Verificar Conexión a la Base de Datos

```bash
npm run test:db
```

Deberías ver: "✅ Successfully connected to MongoDB"

### 2. Iniciar el Servidor de Desarrollo

```bash
npm run dev
```

### 3. Iniciar Inngest (en otra terminal)

Para que funcionen los emails y procesos en segundo plano:

```bash
npx inngest-cli@latest dev
```

### 4. Acceder a la Aplicación

Abre tu navegador en: [http://localhost:3000](http://localhost:3000)

## 📱 Cómo Usar el Portfolio Tracker

1. **Registrarse/Iniciar Sesión**
   - Crea una cuenta o inicia sesión
   
2. **Crear tu Primera Cartera**
   - Ve a "Portfolio" en el menú de navegación
   - Click en "Nueva Cartera"
   - Dale un nombre y descripción (opcional)
   
3. **Añadir Posiciones**
   - Entra a una cartera
   - Click en "Añadir Posición"
   - Completa:
     - Símbolo (ej: AAPL)
     - Compañía (ej: Apple Inc.)
     - Cantidad de acciones (ej: 10)
     - Precio de compra en USD (ej: 150.00)
   
4. **Ver Performance**
   - El sistema automáticamente calcula:
     - Precio actual usando la API de Finnhub
     - Valor invertido vs valor actual
     - Ganancia/Pérdida en USD y %
     - Performance total del portfolio

## 🔧 Solución de Problemas

### Error de Conexión a MongoDB

Si ves errores de conexión:
- Verifica que tu connection string sea correcta
- Asegúrate de haber configurado la IP Whitelist
- Comprueba que el usuario y contraseña sean correctos

### No se Cargan los Precios

Si no ves precios actuales:
- Verifica que tu API key de Finnhub sea válida
- El plan gratuito de Finnhub tiene límites de rate
- Espera unos segundos y recarga la página

### Error 401/403 al Acceder al Portfolio

- Asegúrate de estar autenticado
- Intenta cerrar sesión y volver a iniciar

## 📊 APIs Configuradas

Las siguientes APIs ya están configuradas en el archivo `.env`:

- **Finnhub API:** `d3oc1kpr01qmj830ml2gd3oc1kpr01qmj830ml30`
  - Para cotizaciones y datos de mercado en tiempo real
  
- **Google Gemini API:** `AIzaSyB49QhQQ-FpXFvj3ZUCFI5QeiWx0yfbOjU`
  - Para emails personalizados con IA

## 🎨 Stack Tecnológico

- **Frontend:** Next.js 15, React 19, Tailwind CSS v4
- **UI Components:** shadcn/ui, Radix UI
- **Backend:** Next.js Server Actions
- **Base de Datos:** MongoDB (Atlas o Docker)
- **Autenticación:** Better Auth
- **APIs:** Finnhub (mercado), Gemini (IA)
- **Automatización:** Inngest
- **Email:** Nodemailer

## 📝 Notas Importantes

1. **Límites del Plan Gratuito de Finnhub:**
   - 60 llamadas por minuto
   - Cotizaciones pueden tener 15 minutos de delay
   
2. **MongoDB Atlas Gratis:**
   - 512 MB de almacenamiento
   - Suficiente para desarrollo y pruebas
   
3. **Variables de Email:**
   - Actualmente configuradas con valores placeholder
   - Para que funcionen los emails, configura Gmail SMTP con una contraseña de aplicación

## 🚀 Próximos Pasos Recomendados

1. Configurar un dominio personalizado
2. Desplegar en Vercel o similar
3. Configurar un servicio SMTP real para emails
4. Añadir gráficos de performance histórica
5. Exportar portfolios a CSV/PDF
6. Alertas de precio para portfolios

---

**¡Tu aplicación OpenStock con Portfolio Tracker está lista para usar!** 🎉

