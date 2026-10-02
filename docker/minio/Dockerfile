# MinIO compilado desde el codigo fuente, fijado a una release VERIFICADA.
#
# Por que: la imagen oficial (quay.io/minio/minio) ya no se puede bajar de forma
# anonima y minio/minio no existe en Docker Hub (verificado el 2026-10-02: 401
# UNAUTHORIZED en el manifest de quay, "object not found" en Docker Hub). El
# repositorio github.com/minio/minio esta ARCHIVADO (solo lectura desde abril de
# 2026): esta release es la ultima publicada y no habra parches posteriores.
#
# Tag y commit verificados en la API de GitHub (git/ref/tags/<tag>):
#   RELEASE.2025-10-15T17-29-55Z -> 9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a
# El build FALLA si el tag apunta a otro commit (proteccion contra retag).
# El formato de datos es el de siempre: el volumen /data existente se reutiliza
# sin migrar (MinIO lee los datos de releases anteriores).

FROM golang:1.24-bookworm AS build

ARG MINIO_TAG=RELEASE.2025-10-15T17-29-55Z
ARG MINIO_COMMIT=9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a

ENV CGO_ENABLED=0
WORKDIR /src
RUN git clone --depth 1 --branch "${MINIO_TAG}" https://github.com/minio/minio.git . \
    && test "$(git rev-parse HEAD)" = "${MINIO_COMMIT}" \
    || (echo "El tag ${MINIO_TAG} no apunta a ${MINIO_COMMIT}: build abortado" >&2; exit 1)
# Mismos ldflags que el release oficial (version, release tag y commit).
RUN MINIO_RELEASE=RELEASE \
    LDFLAGS="$(go run buildscripts/gen-ldflags.go "${MINIO_TAG#RELEASE.}")" \
    && go build -trimpath -ldflags "${LDFLAGS}" -o /out/minio .

FROM debian:bookworm-slim
# bash: lo usa el healthcheck de los compose (sonda /dev/tcp, sin curl).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates bash \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /out/minio /usr/bin/minio
# Como la imagen oficial: root, para conservar los permisos del volumen existente.
VOLUME ["/data"]
EXPOSE 9000 9001
ENTRYPOINT ["/usr/bin/minio"]
CMD ["server", "/data"]
