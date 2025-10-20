#!/bin/bash
# # Instalar Ollama usando el script oficial
# curl -fsSL https://ollama.ai/install.sh | sh

# exec ollama serve &

# ollama pull phi3:mini


# Exit on first error
#set -e

# Instalar Ollama usando el script oficial
curl -fsSL https://ollama.ai/install.sh | sh

# Iniciar el servidor Ollama en segundo plano
ollama serve &

# Esperar para asegurar que el servidor esté listo
sleep 10

# Descargar el modelo phi3:mini
ollama pull phi3:mini

pwd

python - <<'PY'
from pathlib import Path

FILES = [
    Path('/app/app/static/OllamaIAService.php'),
    Path('/app/app/app.py'),
    Path('/app/app/rag_system.py'),
]

for path in FILES:
    if not path.exists():
        continue
    data = path.read_text(encoding='utf-8-sig')
    path.write_text(data, encoding='utf-8')
    print(f'Sanitized BOM (if any) in {path}')
PY

exec sh -c 'php -S 0.0.0.0:8000 api.php & cd app && python app.py'
#php -S 0.0.0.0:8000 api.php
#cd app 
#exec python app.py
# Esperar que terminen los procesos en segundo plano si es necesario
#wait
