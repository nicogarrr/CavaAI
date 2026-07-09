<div align="center">
  <br />
  <a href="#" target="_blank">
    <img src="./public/assets/images/dashboard.png" alt="Project Banner" />
  </a>

  <br />
  <br/>

  <div>
    <img src="https://img.shields.io/badge/-Next.js-black?style=for-the-badge&logoColor=white&logo=next.js&color=000000" alt="Next.js badge" />
    <img src="https://img.shields.io/badge/-TypeScript-black?style=for-the-badge&logoColor=white&logo=typescript&color=3178C6"/>
    <img src="https://img.shields.io/badge/-Tailwind%20CSS-black?style=for-the-badge&logoColor=white&logo=tailwindcss&color=38B2AC"/>
    <img src="https://img.shields.io/badge/-shadcn/ui-black?style=for-the-badge&logoColor=white&logo=shadcnui&color=000000"/>
    <img src="https://img.shields.io/badge/-Radix%20UI-black?style=for-the-badge&logoColor=white&logo=radixui&color=000000"/>
    <img src="https://img.shields.io/badge/-Better%20Auth-black?style=for-the-badge&logoColor=white&logo=betterauth&color=000000"/>
    <img src="https://img.shields.io/badge/-MongoDB-black?style=for-the-badge&logoColor=white&logo=mongodb&color=00A35C"/>
    <img src="https://img.shields.io/badge/-TradingView-black?style=for-the-badge&logoColor=white&logo=tradingview&color=2962FF"/>
    <img src="https://img.shields.io/badge/-Finnhub-black?style=for-the-badge&logoColor=white&color=30B27A"/>
  </div>
</div>

# JLCavaAI

JLCavaAI es una plataforma inteligente de seguimiento de mercados y análisis de inversiones. Analiza precios en tiempo real y accede a insights detallados de empresas y ETFs — construido con tecnología de vanguardia.

**Nota:** JLCavaAI es una herramienta educativa y de análisis. Los datos de mercado pueden tener retraso según las reglas del proveedor. Nada aquí constituye asesoramiento financiero.

## 📋 Table of Contents

1. ✨ [Introduction](#introduction)
2. ⚙️ [Tech Stack](#tech-stack)
3. 🔋 [Features](#features)
4. 🤸 [Quick Start](#quick-start)
5. 🔐 [Environment Variables](#environment-variables)
6. 🧱 [Project Structure](#project-structure)
7. 📡 [Data & Integrations](#data--integrations)
8. 📜 [License](#license)

## ✨ Introduction

JLCavaAI / CavaAI es una plataforma de seguimiento de mercados y un **Research OS** de inversión: dashboard Next.js + motor FastAPI con valoración determinista, tesis versionadas, auditoría de fuentes y workers de research.

**Importante:** el motor de valoración **no publica fair values** basados en bootstrap assumptions ni precios inventados. Sin hechos financieros coherentes → `status: insufficient_data`.

## ⚙️ Tech Stack

**Frontend**
- Next.js 16 (App Router), React 19
- TypeScript
- Tailwind CSS v4 (via @tailwindcss/postcss)
- shadcn/ui + Radix UI primitives
- Lucide icons

**Auth & app data**
- Better Auth (email/password) con MongoDB adapter
- MongoDB + Mongoose (auth / watchlists / legacy app state)
- Finnhub API + TradingView widgets

**Research OS (`data-engine/`)**
- FastAPI + SQLAlchemy + PostgreSQL (canonical research store)
- Qdrant (RAG), Redis (jobs/cache), MinIO (filings), DuckDB (analytics)
- Dramatiq workers, Microsoft Agent Framework (MAF), Langfuse (opcional)
- Valuation engine registry: `standard_dcf`, `sotp`, `pre_revenue`, `holding_company`, `commodity`

**Automation & Comms**
- Inngest (events, cron, AI inference via Gemini)
- Nodemailer (Gmail transport)

## 🔋 Features

- **Autenticación**: Email/password auth con Better Auth + MongoDB adapter
- **Research OS**: companies, financial facts, valuation engines, thesis versions, source audits
- **Valoración honesta**: bloquea DCF bootstrap; requiere snapshot temporal coherente; sin precio de mercado → `null` (nunca $100)
- **Búsqueda global y Command + K**: Búsqueda rápida de acciones con Finnhub
- **Watchlist / portfolio**: posiciones, riesgo, analytics
- **Detalles de acciones**: Widgets de TradingView, gráficos avanzados, técnicos
- **UI moderna**: Componentes shadcn/ui, Radix primitives

## 🤸 Quick Start

### 🐳 Opción 1: Docker (Recomendado)

La forma más fácil de ejecutar todo el stack (Frontend + Backend + MongoDB):

```bash
# 1. Clonar el repositorio
git clone https://github.com/nicogarrr/CavaAI.git
cd CavaAI

# 2. Copiar y configurar variables de entorno
cp docker.env.example .env
# Edita .env con tus API keys

# 3. Iniciar todo con Docker
docker-compose up

# ¡Listo! Abre http://localhost:3000
```

**Comandos útiles de Docker:**
```bash
docker-compose up              # Iniciar todo
docker-compose up -d           # Iniciar en background
docker-compose restart         # Reiniciar todo
docker-compose restart backend # Reiniciar solo backend
docker-compose down            # Parar todo
docker-compose up --build      # Rebuild si cambias dependencias
docker-compose logs -f         # Ver logs en tiempo real
```

### 📦 Opción 2: Manual (Sin Docker)

**Prerequisites**
- Node.js 20+ y npm
- Python 3.11+
- MongoDB (local o Atlas)
- API keys (Finnhub, FMP, Gemini)

**Frontend (Next.js)**
```bash
git clone https://github.com/nicogarrr/CavaAI.git
cd CavaAI
npm install
npm run dev
```

**Backend (Python)**
```bash
cd data-engine
pip install -r requirements.txt
# Optional for local tests/development:
pip install -e .[test]
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Open http://localhost:3000 to view the app.

## 🔐 Environment Variables

Crea `.env` en la raíz del proyecto:

```env
# Core
NODE_ENV=development

# Database
MONGODB_URI=mongodb+srv://<user>:<pass>@<cluster>/<db>?retryWrites=true&w=majority

# Better Auth
BETTER_AUTH_SECRET=your_better_auth_secret
BETTER_AUTH_URL=http://localhost:3000

# Finnhub
FINNHUB_API_KEY=your_finnhub_key
FINNHUB_BASE_URL=https://finnhub.io/api/v1

# APIs alternativas
TWELVE_DATA_API_KEY=your_twelve_data_key
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key

# Inngest AI (Gemini)
GEMINI_API_KEY=your_gemini_api_key

# Email (Nodemailer via Gmail)
NODEMAILER_EMAIL=youraddress@gmail.com
NODEMAILER_PASSWORD=your_gmail_app_password
```

## 🧱 Project Structure

```
app/
  (auth)/
    layout.tsx
    sign-in/page.tsx
    sign-up/page.tsx
  (root)/
    layout.tsx
    page.tsx
    stocks/[symbol]/page.tsx
  api/inngest/route.ts
  globals.css
  layout.tsx
components/
  ui/…          # shadcn/radix primitives
  forms/…       # InputField, SelectField, etc.
  stocks/…      # Componentes de análisis de acciones
database/
  models/watchlist.model.ts
  mongoose.ts
lib/
  actions/…     # server actions
  better-auth/…
  inngest/…     # client, functions, prompts
  nodemailer/…  # transporter, email templates
  constants.ts, utils.ts
```

## 📡 Data & Integrations

- **Finnhub**: Búsqueda de acciones, perfiles de empresas y noticias de mercado
- **TradingView**: Widgets embebidos para gráficos, heatmap y cotizaciones
- **Better Auth + MongoDB**: Email/password con MongoDB adapter
- **Inngest**: Workflows y cron jobs
- **Email (Nodemailer)**: Gmail transport para emails automatizados

## 📜 License

© 2025 Nicolas Iglesias Garcia. Todos los derechos reservados.

---

*Desarrollado por Nicolas Iglesias Garcia*
