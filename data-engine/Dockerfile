FROM python:3.12-slim

WORKDIR /app

# Salud: la capa de salud es docker-compose (healthcheck del servicio
# backend con /health/ready). Este Dockerfile no declara HEALTHCHECK propio
# para no duplicar la sonda ni enmascarar el estado real del compose.

# System deps for scipy / numpy / arch
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (better layer caching)
COPY requirements.txt .
# torch CPU-only primero (mismo pin que requirements.txt y Dockerfile.prod):
# sentence-transformers lo exige, y la wheel CUDA por defecto de PyPI son
# GB inservibles en una maquina CPU-only. Ver --extra-index-url en
# requirements.txt y data-engine/scripts/sync_requirements.py.
RUN pip install torch==2.9.1+cpu --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

# Copy source (quantstats package is vendored inside data-engine/)
COPY . .

EXPOSE 8000

CMD ["sh", "-c", "python -m alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000"]
