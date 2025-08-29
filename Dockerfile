# Usar una imagen base de Python
FROM python:3.9-slim

# Instalar dependencias del sistema necesarias
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Instalar Ollama usando el script oficial (MÁS ESTABLE)
RUN curl -fsSL https://ollama.ai/install.sh | sh

# Crear directorio de la aplicación
WORKDIR /app

# Copiar requirements.txt primero
COPY app/requirements.txt .

# Instalar dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto de la aplicación
COPY app/ .

# Exponer los puertos necesarios
EXPOSE 5000
EXPOSE 11434

# Variables de entorno
ENV FLASK_ENV=production
ENV OLLAMA_HOST=0.0.0.0

# Comando para iniciar la aplicación
CMD sh -c "ollama serve & sleep 10 && ollama pull llama3 && python app.py"