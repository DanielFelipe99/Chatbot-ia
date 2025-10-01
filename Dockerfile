# Dockerfile
FROM python:3.9-slim

# Instalar PHP y dependencias 
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    php \
    php-curl \
    php-mbstring \
    php-xml \
    php-zip \
    composer \
    tesseract-ocr \
    tesseract-ocr-spa \
    poppler-utils \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# Instalar Ollama
RUN curl -fsSL https://ollama.ai/install.sh | sh

# Crear directorio de la aplicación
WORKDIR /app

# Copiar archivos de composer primero
COPY composer.json composer.lock* ./
RUN composer install --no-dev --optimize-autoloader || true

# Copiar requirements de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar toda la aplicación
COPY . .

# Crear directorio para logs
RUN mkdir -p /var/log/chatbot

# Copiar configuración de supervisor
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Exponer solo el puerto de Flask
EXPOSE 5000

# Variables de entorno
ENV FLASK_ENV=production
ENV OLLAMA_HOST=0.0.0.0
ENV PHP_API_URL=http://localhost:8080/api.php
ENV OLLAMA_URL=http://localhost:11434

# Usar supervisor para manejar múltiples procesos
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]