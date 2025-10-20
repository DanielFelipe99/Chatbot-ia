from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import requests
import edge_tts
import asyncio
import base64
import tempfile
import os
import threading
from bs4 import BeautifulSoup
import urllib3
from urllib.parse import urljoin
import time
import json
import logging
import glob
from pathlib import Path
import re
import unicodedata
from collections import OrderedDict
from typing import Optional
from rag_system import RAGSystem

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Desactivar warnings de SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
CORS(app)

# Cache simple en memoria para respuestas recientes
MAX_CACHE_ITEMS = 25
response_cache = OrderedDict()
QUICK_REPLIES = {
    "hola": "¡Hola! Soy el profe Axel. ¿Qué te gustaría aprender hoy?",
    "buenos dias": "¡Buenos días! Cuéntame qué tema quieres repasar.",
    "buenas tardes": "¡Buenas tardes! ¿Listo para aprender algo nuevo?",
    "gracias": "¡Con gusto! Si necesitas otra explicación, solo dime.",
    "como estas": "¡Muy bien y con ganas de ayudarte a aprender! ¿Cuál es tu pregunta?"
}


def cache_chat_response(cache_key: str, payload: dict) -> None:
    if not cache_key:
        return
    response_cache[cache_key] = payload
    response_cache.move_to_end(cache_key)
    while len(response_cache) > MAX_CACHE_ITEMS:
        response_cache.popitem(last=False)


def get_cached_chat_response(cache_key: str):
    if not cache_key:
        return None
    cached = response_cache.get(cache_key)
    if cached:
        response_cache.move_to_end(cache_key)
    return cached

# ============ CONFIGURACIÃ“N CORREGIDA ============
# Determinar entorno
IS_SERVER = os.getenv('IS_SERVER', 'false').lower() == 'true'
SERVER_IP = os.getenv('SERVER_IP', '200.7.106.68')

# ConfiguraciÃ³n de URLs segÃºn entorno
if IS_SERVER:
    # En producciÃ³n/Docker
    PHP_API_URL = os.getenv("PHP_API_URL", "http://localhost:8000/api.php")  # Puerto correcto: 8000
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")  # Ollama en el host
    PUBLIC_URL = f"http://{SERVER_IP}:955"
else:
    # En desarrollo local
    PHP_API_URL = os.getenv("PHP_API_URL", "http://localhost:8000/api.php")
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
    PUBLIC_URL = "http://localhost:5000"

# Modelo y configuración de Ollama
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi3:mini")  # Usar modelo rápido
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "30"))  # Reducido a 30s
OLLAMA_MAX_TOKENS = int(os.getenv("OLLAMA_MAX_TOKENS", "350"))  # Respuestas más cortas

# URL de AVAS-2
AVAS2_URL = "https://investic.narino.gov.co/avas-2/"

# Logging de configuración
logger.info("=" * 50)
logger.info("CONFIGURACIÓN DEL SISTEMA:")
logger.info(f"   - Entorno: {'SERVIDOR' if IS_SERVER else 'LOCAL'}")
logger.info(f"   - PHP API: {PHP_API_URL}")
logger.info(f"   - Ollama: {OLLAMA_URL}")
logger.info(f"   - Modelo: {OLLAMA_MODEL}")
logger.info(f"   - URL Publica: {PUBLIC_URL}")
logger.info("=" * 50)

# ============ INICIALIZAR RAG ============
logger.info("Inicializando sistema RAG...")
try:
    # Determinar ruta de documentos segÃºn entorno
    if IS_SERVER:
        docs_path = "/app/docs"
    else:
        # LOCAL: desde app/app.py, subir un nivel a la rai­z del proyecto
        current_file = os.path.abspath(__file__)  # /ruta/proyecto/app/app.py
        app_dir = os.path.dirname(current_file)   # /ruta/proyecto/app
        project_root = os.path.dirname(app_dir)   # /ruta/proyecto
        docs_path = os.path.join(project_root, "docs")  # /ruta/proyecto/docs
    
    docs_path = os.path.abspath(docs_path)
    
    logger.info("=" * 60)
    logger.info("VERIFICANDO DOCUMENTOS:")
    logger.info(f"   Archivo actual: {os.path.abspath(__file__)}")
    logger.info(f"   Directorio app: {os.path.dirname(os.path.abspath(__file__))}")
    logger.info(f"   Ruta docs calculada: {docs_path}")
    logger.info(f"   ¿Existe la ruta? {os.path.exists(docs_path)}")
    
    if os.path.exists(docs_path):
        # Listar contenido
        all_files = os.listdir(docs_path)
        txt_files = [f for f in all_files if f.endswith('.txt')]
        
        logger.info(f"   Todos los archivos: {all_files}")
        logger.info(f"   Archivos .txt: {txt_files}")
        
        if not txt_files:
            logger.error("No hay archivos TXT en la carpeta docs!")
            logger.info("   Verifica que los archivos existan en: " + docs_path)
            rag = None
        else:
            # Mostrar preview de cada archivo
            for txt_file in txt_files:
                filepath = os.path.join(docs_path, txt_file)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                logger.info(f"  {txt_file}: {len(content)} caracteres")
                logger.info(f"      Preview: {content[:100]}...")
            
            logger.info("=" * 60)
            
            # Inicializar RAG
            logger.info("Inicializando RAG System...")
            rag = RAGSystem(docs_dir=docs_path)
            
            # Verificar indexacion
            stats = rag.get_stats()
            logger.info(f"RAG Stats:")
            logger.info(f"   - Total chunks: {stats.get('total_chunks', 0)}")
            logger.info(f"   - Por materia: {stats.get('subjects', {})}")
            
            if stats.get('total_chunks', 0) == 0:
                logger.error("RAG inicializado pero SIN CHUNKS!")
                rag = None
            else:
                logger.info("RAG inicializado correctamente")
                
                # HACER BÚSQUEDA DE PRUEBA
                logger.info("PRUEBA DE BÚSQUEDA:")
                test_query = "¿Que es la suma?"
                context, sources, distance = rag.search_forced(test_query, n_results=3)
                logger.info(f"   Query: {test_query}")
                logger.info(f"   Contexto encontrado: {len(context)} chars")
                logger.info(f"   Fuentes: {sources}")
                logger.info(f"   Distancia: {distance:.3f}")
                if context:
                    logger.info(f"   Preview: {context[:200]}...")
                else:
                    logger.error("    NO SE ENCONTRo CONTEXTO!")
                logger.info("=" * 60)
    else:
        logger.error(f"No existe la carpeta: {docs_path}")
        logger.error(f"   Verifica que la carpeta 'docs' estÃ© en la rai­z del proyecto")
        rag = None
        
except Exception as e:
    logger.error(f"Error al iniciar RAG: {e}")
    import traceback
    logger.error(traceback.format_exc())
    rag = None

# ============ CONFIGURACIÃ“N DE VOCES ============
EDGE_VOICES_ES = {
    'helena': 'es-ES-HelenaNeural',
    'alvaro': 'es-ES-AlvaroNeural',
    'elvira': 'es-ES-ElviraNeural',
    'dalia': 'es-MX-DaliaNeural',
    'jorge': 'es-MX-JorgeNeural',
    'larissa': 'es-MX-LarissaNeural',
    'elena': 'es-AR-ElenaNeural',
    'tomas': 'es-AR-TomasNeural',
    'salome': 'es-CO-SalomeNeural',
    'gonzalo': 'es-CO-GonzaloNeural',
}

# ============ CACHE Y CONFIGURACIÃ“N ============
SCRAPED_CACHE = {}
CACHE_TIMEOUT = 3600  # 1 hora

# Palabras clave por materia
SUBJECT_KEYWORDS = {
    'ciencias_naturales': [
        'ciencias naturales', 'naturales', 'ciencia', 'biologia', 'agua',
        'ciclo del agua', 'sol', 'energia', 'entorno', 'seres vivos'
    ],
    'ciencias_sociales': [
        'ciencias sociales', 'sociales', 'cultura', 'familia', 'convivencia',
        'derechos', 'deberes', 'sociedad', 'comunidad'
    ],
    'matematicas': [
        'matematicas', 'matematicas', 'reciclaje', 'numeros', 'suma', 'resta',
        'multiplicacion', 'division', 'geometria', 'algebra'
    ],
    'espanol': [
        'espaÃ±ol', 'espanol', 'literatura', 'cuento', 'fabula', 'texto',
        'lectura', 'escritura', 'ortografi­a', 'gramatica'
    ],
    'ingles': [
        'ingles', 'ingles', 'english', 'colors', 'numbers', 'family',
        'alphabet', 'greetings'
    ]
}

# ============ INFORMACIÃ“N DE AVAS-2 ============
AVAS2_REAL_INFO = {
    "titulo": "AVAS-2 - Ambientes Virtuales de Aprendizaje",
    "plataforma": "Investic - Secretari­a de Educacion de Nariño",
    "url_base": AVAS2_URL,
    "asignaturas": {
        "ciencias_naturales": {
            "nombre": "Ciencias Naturales",
            "url": f"{AVAS2_URL}ava-ciencias-naturales/",
            "temas": ["Manejo del agua","Seres de mi entorno", "Ciclo del agua", "El sol", "Ecosistemas",
                      "Estados fisicos del agua","El sol como fuente de energia","Luz y calor"]
        },
        "ciencias_sociales": {
            "nombre": "Ciencias Sociales",
            "url": f"{AVAS2_URL}ava-ciencias-sociales/",
            "temas": ["Identidad cultural", "Diversidad", "Cultura", "Derechos","Conflicto","Organizaciones sociales",
                      "Familia, escuela, barrio","Manuel de convivencia","Deberes"]
        },
        "matematicas": {
            "nombre": "Matematicas",
            "url": f"{AVAS2_URL}ava-matematicas/",
            "temas": ["NÃºmeros", "Operaciones", "GeometrÃ­a", "Medidas","Sumas","Restas","Multiplicaciones","Divisiones",]
        },
        "espanol": {
            "nombre": "Español",
            "url": f"{AVAS2_URL}ava-espanol/",
            "temas": ["Textos informativos","Narracion","Anecdota","Receta","Fabula", "Escritura", "Literatura", "GramÃ¡tica",
                      "Cuento","Poema","Mitos y leyendas","Coplas","La cancion","El periodico","La noticia","El telefono", "La carta",
                      "Television, radio e internet"]
        },
        "ingles": {
            "nombre": "Ingles",
            "url": f"{AVAS2_URL}ava-ingles/",
            "temas": ["Vocabulary", "Grammar", "Conversation", "What's your name?","The alphabet","Greetings",
                      "The colors","The family","The numbers","The body","Objects of my house","School supplies","Geoemtric figures",
                      "Fruits and vegetables"] 
        }
    }
}

# ============ CONFIGURACIÃ“N ASYNCIO PARA TTS ============
loop = None
thread = None

def start_async_loop():
    global loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_forever()

thread = threading.Thread(target=start_async_loop, daemon=True)
thread.start()
time.sleep(0.5)

def run_async(coro):
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()

# ============ FUNCIONES AUXILIARES ============
def normalize_text(text):
    """Normalizar texto para busquedas"""
    if not text:
        return ''
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()

# ============ RUTAS PRINCIPALES ============
@app.route("/")
def index():
    """PÃ¡gina principal"""
    return render_template("index.html")

@app.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    """Endpoint con respuestas amigables y empaticas"""
    if request.method == "OPTIONS":
        return '', 204
    
    data = request.get_json()
    prompt = data.get("prompt", "")
    
    if not prompt:
        return jsonify({"error": "No se proporciona pregunta"}), 400
    
    cache_key = normalize_text(prompt)

    if cache_key:
        quick_reply = QUICK_REPLIES.get(cache_key)
        if quick_reply:
            result = {
                "response": quick_reply,
                "strategy": "quick_reply",
                "sources": [],
                "used_docs": False,
                "model": OLLAMA_MODEL
            }
            cache_chat_response(cache_key, result)
            return jsonify({**result, "cached": False})

        cached = get_cached_chat_response(cache_key)
        if cached:
            logger.info("Cache hit: reusing cached reply")
            cached_copy = dict(cached)
            cached_copy["cached"] = True
            return jsonify(cached_copy)

    try:
        # 1. BUSCAR EN DOCUMENTOS LOCALES
        context_rag = ""
        sources = []
        best_distance = 999
        
        if rag:
            logger.info(f"ðŸ” Buscando en documentos: {prompt[:50]}...")
            context_rag, sources, best_distance = rag.search_forced(prompt, n_results=2)  # Solo 2 chunks
            
            if context_rag:
                logger.info(f"Encontrado: {len(context_rag)} chars de {sources} (dist: {best_distance:.3f})")
            else:
                logger.info(f"Sin docs relevantes")
        
        # 2. DECIDIR ESTRATEGIA Y CREAR PROMPT AMIGABLE
        
        if context_rag and len(context_rag) > 50 and best_distance < 0.9:
            # ESTRATEGIA: Docs disponibles
            strategy = "docs_friendly"
            logger.info(f"Usando documentos (distancia: {best_distance:.3f})")
            
            # PROMPT MUY AMIGABLE PARA DOCS
            contexto_final = f"""Eres el Profesor Axel, un maestro amable y paciente que explica las cosas de manera simple y clara.

TU PERSONALIDAD:
- Eres calido, motivador y siempre positivo
- Explicas con ejemplos cotidianos que los niños entienden
- Celebras el aprendizaje: "¡Excelente pregunta!", "¡Muy bien!"
- Hablas de manera natural, como un amigo que enseña

MATERIAL EDUCATIVO:
{context_rag[:800]}

INSTRUCCIONES:
1. Responde de manera SIMPLE y DIRECTA (maximo 3 oraciones cortas)
2. Usa ejemplos de la vida diaria
3. Sé motivador y positivo
4. NO copies textual del material, explica con tus palabras
5. Si puedes, da un ejemplo práctico

PREGUNTA: {prompt}

RESPUESTA AMIGABLE:"""
            
            temperature = 0.25
            optimal_tokens = 120  # Respuestas mÃ¡s cortas

        else:
            # ESTRATEGIA: Solo modelo
            strategy = "model_friendly"
            logger.info(f"Usando conocimiento general")
            
            # PROMPT MUY AMIGABLE PARA MODELO
            contexto_final = f"""Eres el Profesor Axel, un maestro amable y entusiasta que adora enseñar.

TU ESTILO:
- Explicas de forma simple, clara y divertida
- Siempre eres positivo y motivador
- Usas ejemplos que los niños conocen de su vida diaria
- Eres paciente y comprensivo
- Te emociona cuando los niños hacen preguntas

REGLAS:
1. Responde en MÁXIMO 3 oraciones simples
2. Usa palabras sencillas que un niño entienda
3. Da un ejemplo práctico si es posible
4. Sé entusiasta pero no exagerado

PREGUNTA: {prompt}

TU RESPUESTA COMO PROFESOR AXEL:"""
            
            temperature = 0.35
            optimal_tokens = 90  
        
        # 3. PREPARAR PAYLOAD
        max_tokens = min(optimal_tokens, OLLAMA_MAX_TOKENS, 160)

        payload = {
            "prompt": prompt,
            "context": contexto_final,
            "model": OLLAMA_MODEL,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        logger.info(f"Enviando a Ollama (estrategia: {strategy})...")
        
        # 4. LLAMAR A OLLAMA
        php_response = requests.post(
            PHP_API_URL,
            json=payload,
            timeout=OLLAMA_TIMEOUT,
            headers={'Content-Type': 'application/json; charset=utf-8'}
        )
        
        if php_response.status_code != 200:
            logger.error(f"âŒ Error HTTP {php_response.status_code}")
            return jsonify({"error": "Error en el servicio"}), 500
        
        try:
            php_data = php_response.json()
        except json.JSONDecodeError:
            logger.error("Respuesta no es JSON valido")
            return jsonify({"error": "Error en respuesta del servicio"}), 500
        
        if not php_data.get('success'):
            error_msg = php_data.get('error', 'Error desconocido')
            logger.error(f"Error desde PHP: {error_msg}")
            return jsonify({"error": error_msg}), 500
        
        response_text = php_data.get('data', {}).get('response', '')
        
        if not response_text:
            return jsonify({"error": "No se recibió respuesta"}), 500

        # 5. POST-PROCESAMIENTO PARA RESPUESTAS MÁS AMIGABLES
        response_text = response_text.strip()
        
        # Limpiar frases muy formales o roboticas
        formal_replacements = {
            "En conclusión,": "",
            "Por lo tanto,": "Entonces,",
            "Es importante destacar que": "",
            "Cabe mencionar que": "",
            "Asimismo,": "Tambien,",
            "No obstante,": "Pero,",
        }
        
        for formal, friendly in formal_replacements.items():
            response_text = response_text.replace(formal, friendly)
        
        # Limitar a 4 oraciones mÃ¡ximo
        sentences = [s.strip() for s in response_text.replace('!', '.').replace('?', '.').split('.') if s.strip()]
        if len(sentences) > 4:
            response_text = '. '.join(sentences[:4]) + '.'
        
        # Asegurar que termina con puntuaciÃ³n
        if response_text and response_text[-1] not in ['.', '!', '?']:
            response_text += '.'
        
        logger.info("=" * 60)
        logger.info(f"RESPUESTA:")
        logger.info(f"   Estrategia: {strategy}")
        logger.info(f"   Longitud: {len(response_text)} chars")
        logger.info(f"   Oraciones: {len(sentences)}")
        logger.info(f"   Fuentes: {sources if sources else 'Conocimiento general'}")
        logger.info("=" * 60)
        
        # 6. DEVOLVER RESPUESTA
        base_payload = {
            "response": response_text,
            "strategy": strategy,
            "sources": sources if sources else [],
            "used_docs": len(sources) > 0,
            "model": OLLAMA_MODEL
        }

        cache_chat_response(cache_key, base_payload)
        return jsonify({**base_payload, "cached": False})
        
    except requests.exceptions.Timeout:
        logger.error("Timeout")
        return jsonify({"error": "El servicio tardó demasiado"}), 504
        
    except requests.exceptions.ConnectionError:
        logger.error("Error de conexión")
        return jsonify({"error": "No se pudo conectar con el servicio"}), 503
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({"error": "Error procesando la pregunta"}), 500
    
# ============ TTS (Text-to-Speech) ============
async def generate_speech_async(text, voice_name):
    """Generar audio con Edge TTS"""
    try:
        communicate = edge_tts.Communicate(text, voice_name)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
            tmp_filename = tmp_file.name
        
        await communicate.save(tmp_filename)
        
        with open(tmp_filename, 'rb') as audio_file:
            audio_data = audio_file.read()
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
        
        try:
            os.unlink(tmp_filename)
        except:
            pass
        
        return audio_base64
    except Exception as e:
        logger.error(f"Error generando audio: {e}")
        raise e

@app.route("/tts", methods=["POST"])
def text_to_speech():
    """Endpoint para generar audio"""
    data = request.get_json()
    text = data.get("text", "")
    voice = data.get("voice", "gonzalo")
    
    if not text:
        return jsonify({"error": "No text provided"}), 400
    
    try:
        voice_name = EDGE_VOICES_ES.get(voice, EDGE_VOICES_ES['gonzalo'])
        audio_base64 = run_async(generate_speech_async(text, voice_name))
        
        return jsonify({
            "audio": f"data:audio/mpeg;base64,{audio_base64}",
            "voice": voice_name
        })
    except Exception as e:
        logger.error(f"Error en TTS: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/voices", methods=["GET"])
def get_voices():
    """Obtener voces disponibles"""
    voices_list = []
    for key, voice_id in EDGE_VOICES_ES.items():
        parts = voice_id.split('-')
        voices_list.append({
            "id": key,
            "name": parts[2].replace('Neural', ''),
            "voice_id": voice_id,
            "locale": f"{parts[0]}-{parts[1]}"
        })
    
    return jsonify({"voices": voices_list, "enabled": True})




@app.route("/rag/stats", methods=["GET"])
def rag_stats():
    """Obtener estadísticas del RAG"""
    if not rag:
        return jsonify({
            "error": "RAG no disponible",
            "status": "disabled"
        }), 503
    
    try:
        stats = rag.get_stats()
        return jsonify({
            "success": True,
            "data": stats
        })
    except Exception as e:
        return jsonify({
            "error": str(e),
            "status": "error"
        }), 500

@app.route("/rag/search-test", methods=["POST"])
def rag_search_test():
    """Probar busqueda en RAG"""
    if not rag:
        return jsonify({"error": "RAG no disponible"}), 503
    
    data = request.get_json()
    query = data.get("query", "")
    
    if not query:
        return jsonify({"error": "Query vacío"}), 400
    
    try:
        context, sources = rag.search(query, n_results=3)
        return jsonify({
            "query": query,
            "context": context,
            "sources": sources,
            "context_length": len(context)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route("/rag/diagnostics", methods=["GET"])
def rag_diagnostics():
    """DiagnÃ³stico completo del RAG"""
    if not rag:
        return jsonify({
            "status": "disabled",
            "error": "RAG no inicializado"
        }), 503
    
    try:
        # Obtener estadÃ­sticas
        stats = rag.get_stats()
        
        # Verificar archivos en disco
        docs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs"))
        files_on_disk = []
        
        if os.path.exists(docs_path):
            for filename in os.listdir(docs_path):
                if filename.endswith('.txt'):
                    filepath = os.path.join(docs_path, filename)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    files_on_disk.append({
                        "filename": filename,
                        "size": len(content),
                        "lines": len(content.split('\n')),
                        "preview": content[:200]
                    })
        
        # Hacer bÃºsqueda de prueba
        test_queries = [
            "¿Que es la suma?",
            "¿Cuales son los estados de la materia?",
            "¿Que es la familia?",
            "Hello, how are you?",
            "¿Que es un sustantivo?"
        ]
        
        test_results = []
        for query in test_queries:
            context, sources = rag.search(query, n_results=3)
            test_results.append({
                "query": query,
                "found_context": len(context) > 0,
                "context_length": len(context),
                "sources": sources,
                "preview": context[:150] if context else "No encontrado"
            })
        
        return jsonify({
            "status": "active",
            "rag_stats": stats,
            "docs_path": docs_path,
            "files_on_disk": files_on_disk,
            "test_searches": test_results
        })
        
    except Exception as e:
        import traceback
        return jsonify({
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500

@app.route("/rag/reindex", methods=["POST"])
def rag_reindex():
    """Forzar reindexacion manual"""
    global rag
    
    try:
        logger.info("Reindexacion manual solicitada...")
        
        # Eliminar Ã­ndice actual
        if rag:
            try:
                rag.client.delete_collection("docs_educativos")
                logger.info("Indice anterior eliminado")
            except:
                pass
        
        # Determinar ruta de docs
        if IS_SERVER:
            docs_path = "/app/docs"
        else:
            current_file = os.path.abspath(__file__)
            app_dir = os.path.dirname(current_file)
            project_root = os.path.dirname(app_dir)
            docs_path = os.path.join(project_root, "docs")
        
        docs_path = os.path.abspath(docs_path)
        
        # Reinicializar RAG
        from rag_system import RAGSystem
        rag = RAGSystem(docs_dir=docs_path)
        
        stats = rag.get_stats()
        
        return jsonify({
            "success": True,
            "message": "Reindexacion completada",
            "stats": stats
        })
        
    except Exception as e:
        logger.error(f"Error en reindexacion: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============ INICIAR SERVIDOR ============
if __name__ == "__main__":
    port = int(os.getenv('FLASK_PORT', 5000))
    
    print("=" * 60)
    print("ASISTENTE EDUCATIVO AVAS-2")
    print("=" * 60)
    print(f"Sistema iniciado")
    print(f"Accede en: {PUBLIC_URL if IS_SERVER else f'http://localhost:{port}'}")
    print(f"RAG: {'Activo' if rag else 'No disponible'}")
    print(f"Modelo: {OLLAMA_MODEL}")
    print("=" * 60)
    
    app.run(
        debug=False,
        host='0.0.0.0',
        port=port,
        threaded=True
    )
