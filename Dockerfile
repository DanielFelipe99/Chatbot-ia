FROM python:3.10-slim

# Instalar TODAS las dependencias del sistema necesarias
RUN apt-get update && apt-get install -y \
    # Básicas
    curl wget \
    # PHP
    php-cli php-curl php-mbstring php-xml php-zip \
    composer \
    # Python build tools 
    build-essential \
    python3-dev \
    gcc \
    g++ \
    # Otras herramientas
    tesseract-ocr tesseract-ocr-spa \
    poppler-utils \
    netcat-openbsd \
    procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar requirements
COPY requirements.txt .

# Actualizar pip primero
RUN pip install --upgrade pip setuptools wheel

# Instalar dependencias en orden (para mejor debugging)
RUN pip install --no-cache-dir flask flask-cors requests
RUN pip install --no-cache-dir beautifulsoup4 edge-tts urllib3
RUN pip install --no-cache-dir sentence-transformers
RUN pip install --no-cache-dir chromadb

# Instalar el resto si hay más
RUN pip install --no-cache-dir -r requirements.txt || true

# Copiar composer files
COPY composer.json composer.lock* ./
RUN if [ -f composer.json ]; then composer install --no-dev --optimize-autoloader; fi

# Copiar aplicación
COPY . .

# Crear directorios
RUN mkdir -p /app/docs /app/chroma_db /var/log/chatbot

#CMD sh -c 'php -S 0.0.0.0:8000 api.php & cd app && python app.py'

EXPOSE 5000 8000

# Copiar entrypoint y darle permisos ejecutables
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]