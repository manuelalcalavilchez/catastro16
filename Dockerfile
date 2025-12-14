FROM python:3.11-slim

# Instalar dependencias del sistema necesarias para psycopg (driver PostgreSQL)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    gdal-bin \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

# Crear directorio de trabajo
WORKDIR /app

# Copiar requirements e instalarlos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código del proyecto
COPY . .

# Exponer puerto
EXPOSE 8001

# Comando de arranque para EasyPanel
# Se asume que las migraciones se corren al inicio en app.py o via script separado.
# Para producción es mejor workers multiples con gunicorn, pero uvicorn directo es aceptable.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
