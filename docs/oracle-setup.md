# Despliegue permanente en Oracle Cloud Always Free (backend personal)

Objetivo: que el backend de CavaAI (FastAPI + Postgres + Redis + Qdrant +
MinIO + workers) este siempre disponible desde PC y movil, a **0 EUR/mes**,
sin depender del portatil. El frontend sigue en Vercel Hobby; la auth sigue
en MongoDB Atlas M0 (gratis). Lo unico de pago potencial son las APIs
externas de datos/LLM, como hoy.

## Que incluye el repo (ya listo)

- `data-engine/Dockerfile.prod` - imagen ARM64 con torch CPU-only (sin los
  ~2-5 GB de wheels CUDA, inutiles en una VM sin GPU).
- `docker-compose.prod.yml` - stack completo en una sola VM, limites de
  memoria pensados para 12 GB, Caddy con TLS automatico.
- `infra/caddy/Caddyfile` - reverse proxy + Let's Encrypt.
- `scripts/backup.sh` / `scripts/restore.sh` - backups de Postgres, Qdrant,
  MinIO y DuckDB, con subida opcional a Cloudflare R2 (free tier 10 GB).
- CI ARM64 nativo (job `ARM64 compatibility smoke`) que ya prueba que el
  backend instala y arranca en aarch64.

## Lo que Always Free incluye (limites a respetar)

- VM.Standard.A1.Flex (Ampere ARM): hasta **2 OCPU y 12 GB RAM** en total
  en cuentas Always Free sin ampliar (cuentas con upgrade llegan a 4/24).
  Esta app esta dimensionada para **2 OCPU / 12 GB**.
- **200 GB** de block storage en total (boot volumes incluidos).
- 10 TB/mes de salida de red (de sobra para uso personal).
- Cuentas nuevas de pago tardio ("Pay As You Go") pueden tener Always Free
  igualmente; el riesgo de coste viene SOLO de crear recursos fuera del
  programa Always Free. Sigue estas reglas:
  - Crea la VM con shape `VM.Standard.A1.Flex` marcada **"Always Free
    Eligible"** (aparece la etiqueta en la consola).
  - No superes 2 OCPU / 12 GB RAM / 200 GB disco en total (cuenta sin
    upgrade; con upgrade el tope es 4 OCPU / 24 GB).
  - No crees Load Balancers, bases de datos gestionadas ni boot volumes
    extra de mas de 200 GB combinados.
  - Opcional pero recomendado: presupuesto con alerta a 1 EUR
    (Billing > Budgets) para enterarte si algo se sale.

## Pasos exactos (cuenta de Oracle)

1. **Crear cuenta**: cloud.oracle.com > Sign Up. Pide tarjeta para
   verificacion de identidad pero **no cobra** si solo usas recursos Always
   Free. Elige la home region con cuidado: no se puede cambiar despues y
   Always Free solo aplica en esa region. Madrid no existe; las mas
   cercanas son **Frankfurt** o **Marsella** (Amsterdam tambien suele tener
   capacidad ARM limitada).
2. **Crear la VM**: Compute > Instances > Create instance.
   - Image: **Ubuntu 24.04 (aarch64)**.
   - Shape: `VM.Standard.A1.Flex`, 2 OCPU, 12 GB RAM (etiqueta Always Free).
   - Boot volume: 100 GB (quedan 100 GB libres del cupo).
   - Networking: nueva VCN con IP publica.
   - Sube tu clave SSH publica.
3. **Abrir puertos** (dos sitios, Oracle lo exige en ambos):
   - En la VCN: Security List > Add Ingress Rules: TCP 80 y 443 desde
     0.0.0.0/0.
   - En la VM (Ubuntu): `sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT && sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT && sudo netfilter-persistent save`
4. **Dominio gratis para TLS**: DuckDNS (duckdns.org) > login > crea un
   subdominio (p.ej. `cavaai-api.duckdns.org`) apuntando a la IP publica de
   la VM. Es gratis y Caddy saca el certificado solo.
5. **Instalar Docker** en la VM:
   `curl -fsSL https://get.docker.com | sh && sudo usermod -aG docker ubuntu`
   (cierra sesion y vuelve a entrar).
6. **Clonar y configurar**:
   ```
   git clone https://github.com/nicogarrr/CavaAI.git && cd CavaAI
   cp .env.production.example .env.production   # rellena los secretos
   docker compose -f docker-compose.prod.yml up -d --build
   ```
7. **Apuntar Vercel al backend**: en el proyecto de Vercel define estas
   variables y redeploy (sin ellas el frontend prod no autentica ni firma
   contra el backend):
   `FMP_BACKEND_URL=https://cavaai-api.duckdns.org`,
   `RESEARCH_AUTH_SECRET` (el mismo valor que en la VM),
   `BETTER_AUTH_SECRET`, `BETTER_AUTH_URL=https://<tu-app>.vercel.app`,
   `MONGODB_URI` (Atlas M0), `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`.
8. **Backups**: `crontab -e` y anade
   `17 4 * * * cd /home/ubuntu/CavaAI && RCLONE_REMOTE=r2:cavaai-backups ./scripts/backup.sh >> /var/log/cavaai-backup.log 2>&1`
   (configura rclone una vez con las claves R2; ver abajo).

## Cloudflare R2 para backups (gratis, 10 GB)

1. Cloudflare dashboard > R2 > Create bucket `cavaai-backups`.
2. R2 > Manage R2 API Tokens > Create API token (Object Read & Write, solo
   ese bucket).
3. En la VM: `rclone config` > new remote `r2` > S3 > provider Cloudflare >
   access_key_id + secret + endpoint
   `https://<account-id>.r2.cloudflarestorage.com`.
4. R2 free tier: 10 GB almacenamiento, sin costes de egreso. Con dumps
   diarios comprimidos de una app personal sobra; el script crea una carpeta
   por fecha asi que conviene borrar backups de mas de 30 dias
   (`rclone delete r2:cavaai-backups --min-age 30d`, se puede anadir al cron).

## Verificacion tras el despliegue

- `curl -fsS https://cavaai-api.duckdns.org/health/ready` responde OK.
- En la app (Vercel): /portfolio, /research, /knowledge cargan datos en vez
  del panel "motor de analisis desconectado".
- Un backup manual: `./scripts/backup.sh` y comprobar `backups/*/manifest.txt`.

## Coste total

0 EUR/mes (Oracle Always Free + Vercel Hobby + Atlas M0 + DuckDNS + R2
10 GB). Se mantienen los costes actuales de APIs externas (datos/LLM), que
no cambian con este despliegue.
