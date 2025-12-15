FROM python:3.11-slim

# Instalar dependencias del sistema para PostgreSQL, GDAL, Cairo y librerías científicas
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    libspatialindex-dev \
    libcairo2-dev \
    pkg-config \
    libfreetype6-dev \
    libpng-dev \
    && rm -rf /var/lib/apt/lists/*

# Configurar variable de entorno para GDAL
ENV GDAL_CONFIG=/usr/bin/gdal-config

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
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
