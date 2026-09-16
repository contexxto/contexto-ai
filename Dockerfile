FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg2 / GeoAlchemy2 / geopy.
# fonts-dejavu-core: TTF real para el banner "letrero" (Pillow) — sin esto, PIL cae al
# font bitmap por defecto (diminuto, feo, no escala) y el letrero impreso se ve mal.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev libgdal-dev fonts-dejavu-core && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ancla de confianza de Supabase, a una ruta RUNTIME ESTABLE.
#
# COPY PROPIO Y EXPLICITO, no arrastrado por el `COPY . .` de abajo. La razon es que un
# `.dockerignore` futuro podria excluir certs/ y el bundle desapareceria de la imagen SIN
# que nadie se entere: la app arrancaria y la verificacion TLS fallaria en caliente. Con
# esta linea, ese mismo escenario rompe el BUILD, que es donde se quiere que rompa.
#
# La ruta de destino es estable a proposito: el bundle esta versionado en el repo
# (bundle-v1, -v2...) para poder rotar, pero el codigo apunta siempre al mismo sitio. Una
# rotacion cambia el origen de esta linea, no el consumidor.
#
# ESTA UNIDAD NO ACTIVA TLS. Solo coloca el fichero. Ver certs/supabase/README.md.
COPY certs/supabase/bundle-v1.pem /app/certs/supabase-ca-bundle.pem

COPY . .

# Render injects PORT; uvicorn binds to it
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
