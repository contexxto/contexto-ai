FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg2 / GeoAlchemy2 / geopy
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev libgdal-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render injects PORT; uvicorn binds to it
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
