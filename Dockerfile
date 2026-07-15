# Imagen del modo demo (despliegue publico del TFM). Corre SIEMPRE el perfil demo:
# BD aislada tpv_demo.db, sin certificado, motor NullEngine (invariante 7).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TPV_PROFILE=demo

WORKDIR /app

# Instala la app y sus dependencias de runtime (sin [dev]). Se copia todo antes
# porque el build de hatchling necesita el paquete `app/` presente.
COPY . .
RUN pip install --no-cache-dir .

# La plataforma inyecta $PORT; el entrypoint migra + siembra y arranca uvicorn.
EXPOSE 8000
CMD ["sh", "./docker-entrypoint.sh"]
