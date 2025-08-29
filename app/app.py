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
from urllib.parse import urljoin, urlparse
import re
import time
# Desactivar warnings de SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
CORS(app)

OLLAMA_API_URL = "http://localhost:11434/api/generate"
SED_NARINO_URL = "https://sed.narino.gov.co/"

# Voces de Microsoft Edge
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

# Cache para almacenar contenido scrapeado
SCRAPED_CACHE = {}
CACHE_TIMEOUT = 3600  # 1 hora en segundos

# Crear un loop de asyncio en un thread separado
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

def scrape_sed_narino():
    """Scraping completo de SED Nariño con múltiples secciones"""
    try:
        print(f"🌐 Scrapeando SED Nariño profundamente...")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # URLs importantes de SED Nariño (basado en estructura típica)
        urls_importantes = [
            SED_NARINO_URL,  # Página principal
            f"{SED_NARINO_URL}noticias",
            f"{SED_NARINO_URL}documentos",
            f"{SED_NARINO_URL}normatividad",
            f"{SED_NARINO_URL}programas",
            f"{SED_NARINO_URL}instituciones",
            f"{SED_NARINO_URL}contacto",
        ]
        
        info_completa = {
            'titulo': '',
            'noticias': [],
            'documentos': [],
            'programas_educativos': [],
            'normatividad': [],
            'contactos': [],
            'enlaces_importantes': [],
            'texto_relevante': ''
        }
        
        for url in urls_importantes:
            try:
                print(f"📄 Scrapeando: {url}")
                response = requests.get(url, headers=headers, verify=False, timeout=15)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'lxml')
                
                # Extraer información según el tipo de página
                if url.endswith('/noticias') or 'noticia' in url:
                    info_completa['noticias'].extend(extraer_noticias(soup))
                elif 'documento' in url or 'normatividad' in url:
                    info_completa['documentos'].extend(extraer_documentos(soup))
                elif 'programa' in url:
                    info_completa['programas_educativos'].extend(extraer_programas(soup))
                elif 'contacto' in url:
                    info_completa['contactos'].extend(extraer_contactos(soup))
                else:
                    # Página principal o genérica
                    if not info_completa['titulo']:
                        info_completa['titulo'] = soup.find('title').get_text().strip() if soup.find('title') else ''
                    
                    info_completa['enlaces_importantes'].extend(extraer_enlaces_importantes(soup))
                    info_completa['texto_relevante'] += extraer_texto_relevante(soup)
                    
            except Exception as e:
                print(f"⚠️ Error scrapeando {url}: {str(e)}")
                continue
        
        # Procesar documentos PDF y Word (si existen)
        info_completa['documentos'].extend(buscar_documentos_adjuntos(soup))
        
        # Guardar en cache
        SCRAPED_CACHE['sed_narino'] = {
            'data': info_completa,
            'timestamp': time.time()
        }
        
        print(f"✅ Scraping completo exitoso. Noticias: {len(info_completa['noticias'])}, Documentos: {len(info_completa['documentos'])}")
        return info_completa
        
    except Exception as e:
        print(f"❌ Error en scraping completo: {str(e)}")
        return {'error': str(e)}

# Funciones auxiliares para extracción específica
def extraer_noticias(soup):
    """Extraer noticias estructuradas"""
    noticias = []
    try:
        # Buscar en múltiples estructuras comunes de noticias
        selectores = [
            'article.noticia', 'div.noticia', '.news-item', '.post',
            '[class*="noticia"]', '[class*="news"]', '[class*="post"]'
        ]
        
        for selector in selectores:
            elementos = soup.select(selector)
            for elem in elementos[:10]:  # Limitar a 10 noticias por sección
                try:
                    titulo = elem.find(['h2', 'h3', 'h4', 'h5']).get_text().strip() if elem.find(['h2', 'h3', 'h4', 'h5']) else ''
                    fecha = elem.find(['time', '.fecha', '[class*="date"]'])
                    fecha_texto = fecha.get_text().strip() if fecha else ''
                    contenido = elem.get_text().strip()[:1000]  # Primeros 1000 caracteres
                    
                    if titulo and contenido:
                        noticias.append({
                            'titulo': titulo,
                            'fecha': fecha_texto,
                            'contenido': contenido,
                            'url': obtener_url_noticia(elem)
                        })
                except:
                    continue
    except Exception as e:
        print(f"Error extrayendo noticias: {e}")
    
    return noticias

def extraer_documentos(soup):
    """Extraer documentos y normatividad"""
    documentos = []
    try:
        # Buscar enlaces a documentos
        for enlace in soup.find_all('a', href=True):
            href = enlace['href']
            texto = enlace.get_text().strip()
            
            # Filtrar documentos importantes
            if (href.endswith(('.pdf', '.doc', '.docx', '.xlsx')) or 
                'documento' in href.lower() or 'normatividad' in href.lower()):
                
                if href.startswith('/'):
                    href = urljoin(SED_NARINO_URL, href)
                
                documentos.append({
                    'titulo': texto if texto else href.split('/')[-1],
                    'url': href,
                    'tipo': href.split('.')[-1].upper() if '.' in href else 'LINK'
                })
    except Exception as e:
        print(f"Error extrayendo documentos: {e}")
    
    return documentos

def extraer_programas(soup):
    """Extraer programas educativos"""
    programas = []
    try:
        # Buscar programas educativos (estructura común)
        selectores = ['.programa', '.project', '.service', '[class*="programa"]']
        
        for selector in selectores:
            elementos = soup.select(selector)
            for elem in elementos:
                try:
                    titulo = elem.find(['h3', 'h4', 'h5']).get_text().strip() if elem.find(['h3', 'h4', 'h5']) else ''
                    descripcion = elem.get_text().strip()[:500]
                    
                    if titulo:
                        programas.append({
                            'nombre': titulo,
                            'descripcion': descripcion
                        })
                except:
                    continue
    except Exception as e:
        print(f"Error extrayendo programas: {e}")
    
    return programas

def extraer_contactos(soup):
    """Extraer información de contacto"""
    contactos = []
    try:
        # Buscar información de contacto
        selectores = [
            '.contacto', '.address', '.phone', '.email',
            '[class*="contact"]', '[class*="direccion"]'
        ]
        
        for selector in selectores:
            elementos = soup.select(selector)
            for elem in elementos:
                texto = elem.get_text().strip()
                if texto and len(texto) > 10:
                    contactos.append(texto)
    except Exception as e:
        print(f"Error extrayendo contactos: {e}")
    
    return contactos

def extraer_enlaces_importantes(soup):
    """Extraer enlaces importantes"""
    enlaces = []
    try:
        palabras_clave = [
            'educativo', 'programa', 'proyecto', 'noticia', 'documento',
            'normatividad', 'contacto', 'sed', 'nariño', 'secretaría'
        ]
        
        for enlace in soup.find_all('a', href=True):
            texto = enlace.get_text().strip()
            href = enlace['href']
            
            if texto and len(texto) > 3 and len(texto) < 100:
                if href.startswith('/'):
                    href = urljoin(SED_NARINO_URL, href)
                
                # Filtrar por palabras clave
                if any(palabra in texto.lower() for palabra in palabras_clave) or any(palabra in href.lower() for palabra in palabras_clave):
                    enlaces.append(f"{texto}: {href}")
    except Exception as e:
        print(f"Error extrayendo enlaces: {e}")
    
    return enlaces

def extraer_texto_relevante(soup):
    """Extraer texto relevante"""
    texto_relevante = ""
    try:
        # Buscar en secciones con contenido importante
        selectores = [
            'main', 'article', 'section',
            '.content', '.main-content', '.post-content',
            '[class*="content"]', '[class*="text"]'
        ]
        
        for selector in selectores:
            elementos = soup.select(selector)
            for elem in elementos:
                texto = elem.get_text().strip()
                if len(texto) > 100:
                    texto_relevante += texto + "\n\n"
    except Exception as e:
        print(f"Error extrayendo texto: {e}")
    
    return texto_relevante[:5000]  # Limitar a 5000 caracteres

def buscar_documentos_adjuntos(soup):
    """Buscar documentos adjuntos en la página"""
    documentos = []
    try:
        for enlace in soup.find_all('a', href=True):
            href = enlace['href']
            if href.endswith(('.pdf', '.doc', '.docx')):
                if href.startswith('/'):
                    href = urljoin(SED_NARINO_URL, href)
                
                documentos.append({
                    'titulo': enlace.get_text().strip() or href.split('/')[-1],
                    'url': href,
                    'tipo': href.split('.')[-1].upper()
                })
    except Exception as e:
        print(f"Error buscando documentos: {e}")
    
    return documentos

def obtener_url_noticia(elemento):
    """Obtener URL completa de una noticia"""
    try:
        enlace = elemento.find('a', href=True)
        if enlace:
            href = enlace['href']
            if href.startswith('/'):
                return urljoin(SED_NARINO_URL, href)
            return href
    except:
        pass
    return ""
    """Obtener información de la página SED Nariño"""
    try:
        print(f"🌐 Scrapeando: {SED_NARINO_URL}")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(SED_NARINO_URL, headers=headers, verify=False, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'lxml')
        
        # Extraer información importante
        info = {
            'titulo': soup.find('title').get_text().strip() if soup.find('title') else '',
            'noticias': [],
            'enlaces_importantes': [],
            'texto_relevante': ''
        }
        
        # Extraer noticias (ajusta según la estructura real de la página)
        noticias = soup.find_all(['article', 'div'], class_=re.compile(r'noticia|news|post', re.I))
        for noticia in noticias[:5]:  # Limitar a 5 noticias
            try:
                titulo = noticia.find(['h2', 'h3', 'h4']).get_text().strip() if noticia.find(['h2', 'h3', 'h4']) else ''
                contenido = noticia.get_text().strip()[:500]  # Primeros 500 caracteres
                if titulo and contenido:
                    info['noticias'].append(f"{titulo}: {contenido}")
            except:
                continue
        
        # Extraer enlaces importantes
        for enlace in soup.find_all('a', href=True)[:10]:
            texto = enlace.get_text().strip()
            href = enlace['href']
            if texto and len(texto) > 3 and len(texto) < 100:
                if href.startswith('/'):
                    href = urljoin(SED_NARINO_URL, href)
                if 'sed.narino.gov.co' in href:
                    info['enlaces_importantes'].append(f"{texto}: {href}")
        
        # Extraer texto general relevante
        textos = []
        for elemento in soup.find_all(['p', 'div'], class_=re.compile(r'content|text|description', re.I)):
            texto = elemento.get_text().strip()
            if len(texto) > 50 and len(texto) < 1000:
                textos.append(texto)
        
        info['texto_relevante'] = ' '.join(textos[:3])  # Primeros 3 párrafos
        
        # Guardar en cache
        SCRAPED_CACHE['sed_narino'] = {
            'data': info,
            'timestamp': time.time()
        }
        
        print(f"✅ Scraping exitoso. Noticias: {len(info['noticias'])}")
        return info
        
    except Exception as e:
        print(f"❌ Error en scraping: {str(e)}")
        return {'error': str(e)}

def get_sed_narino_info():
    """Obtener información de SED Nariño con cache"""
    cached = SCRAPED_CACHE.get('sed_narino')
    
    if cached and (time.time() - cached['timestamp']) < CACHE_TIMEOUT:
        print("📦 Usando información en cache")
        return cached['data']
    
    return scrape_sed_narino()

def formatear_informacion_completa(info):
    """Formatear la información para el prompt de manera legible"""
    texto = ""
    
    # 1. Formatear NOTICIAS
    if info.get('noticias'):
        texto += "📰 ÚLTIMAS NOTICIAS:\n"
        for i, noticia in enumerate(info['noticias'][:3], 1):
            texto += f"{i}. {noticia['titulo']}"
            if noticia.get('fecha'):
                texto += f" ({noticia['fecha']})"
            texto += f": {noticia['contenido'][:200]}...\n"
        texto += "\n"
    
    # 2. Formatear DOCUMENTOS
    if info.get('documentos'):
        texto += "📄 DOCUMENTOS IMPORTANTES:\n"
        for i, doc in enumerate(info['documentos'][:5], 1):
            texto += f"{i}. {doc['titulo']} ({doc['tipo']})\n"
        texto += "\n"
    
    # 3. Formatear PROGRAMAS
    if info.get('programas_educativos'):
        texto += "🎓 PROGRAMAS EDUCATIVOS:\n"
        for i, programa in enumerate(info['programas_educativos'][:3], 1):
            texto += f"{i}. {programa['nombre']}: {programa['descripcion'][:100]}...\n"
        texto += "\n"
    
    # 4. Formatear CONTACTOS
    if info.get('contactos'):
        texto += "📞 INFORMACIÓN DE CONTACTO:\n"
        for contacto in info['contactos'][:3]:
            texto += f"- {contacto}\n"
        texto += "\n"
    
    # 5. Información general
    if info.get('texto_relevante'):
        texto += f"📋 INFORMACIÓN GENERAL: {info['texto_relevante'][:1000]}...\n"
    
    return texto

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        return '', 204

    data = request.get_json()
    prompt = data.get("prompt", "")

    if not prompt:
        return jsonify({"error": "No prompt provided"}), 400

    try:
        # Obtener información en tiempo real de SED Nariño
        sed_info = get_sed_narino_info()
        
        # Construir contexto con la información obtenida
        contexto_sed = ""
        if 'error' not in sed_info:
            contexto_sed = f"""
            INFORMACIÓN COMPLETA SECRETARÍA DE EDUCACIÓN DE NARIÑO:

{formatear_informacion_completa(sed_info)}
"""

        else:
            contexto_sed = "⚠️ No se pudo acceder a la información oficial en este momento."

        # Preparar prompt con contexto
        prompt_final = f"""
{contexto_sed}

POR FAVOR RESPONDE BASÁNDOTE EN LA INFORMACIÓN OFICIAL PROPORCIONADA.

PREGUNTA DEL USUARIO: {prompt}

INSTRUCCIONES:
- Responde específicamente sobre educación en Nariño
- Si la información no está en el contexto, dilo claramente
- Sé preciso y utiliza información oficial
- Mantén un tono profesional y educativo
"""
        
        # Obtener respuesta de Ollama
        payload = {
            "model": "llama3",
            "prompt": prompt_final,
            "stream": False
        }
        
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=120)
        
        if response.status_code != 200:
            return jsonify({"error": "Ollama API request failed", "details": response.text}), 500

        ollama_data = response.json()
        response_text = ollama_data.get("response", "")
        
        return jsonify({
            "response": response_text,
            "context_used": True,
            "source": "https://sed.narino.gov.co/"
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/scrape/refresh", methods=["POST"])
def refresh_scrape():
    """Forzar actualización del scraping"""
    SCRAPED_CACHE.clear()
    result = scrape_sed_narino()
    return jsonify({
        "success": 'error' not in result,
        "message": "Información actualizada" if 'error' not in result else "Error al actualizar"
    })

@app.route("/scrape/status", methods=["GET"])
def scrape_status():
    """Obtener estado del scraping"""
    cached = SCRAPED_CACHE.get('sed_narino')
    return jsonify({
        "cached": cached is not None,
        "age_seconds": time.time() - cached['timestamp'] if cached else 0,
        "source": SED_NARINO_URL
    })

async def generate_speech_async(text, voice_name):
    """Generar audio de forma asíncrona"""
    try:
        # Crear el comunicador de edge-tts
        communicate = edge_tts.Communicate(text, voice_name)
        
        # Crear archivo temporal
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
            tmp_filename = tmp_file.name
        
        # Guardar el audio
        await communicate.save(tmp_filename)
        
        # Leer el archivo y convertir a base64
        with open(tmp_filename, 'rb') as audio_file:
            audio_data = audio_file.read()
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
        
        # Eliminar archivo temporal
        try:
            os.unlink(tmp_filename)
        except:
            pass
        
        return audio_base64
    except Exception as e:
        print(f"Error generando audio: {e}")
        raise e

@app.route("/tts", methods=["POST"])
def text_to_speech():
    """Endpoint síncrono para generar audio con Edge TTS"""
    data = request.get_json()
    text = data.get("text", "")
    voice = data.get("voice", "helena")
    
    if not text:
        return jsonify({"error": "No text provided"}), 400
    
    try:
        # Obtener el nombre completo de la voz
        voice_name = EDGE_VOICES_ES.get(voice, EDGE_VOICES_ES['helena'])
        
        print(f"Generando audio con voz: {voice_name}")
        print(f"Texto: {text[:50]}...")
        
        # Ejecutar la generación de audio de forma asíncrona
        audio_base64 = run_async(generate_speech_async(text, voice_name))
        
        return jsonify({
            "audio": f"data:audio/mpeg;base64,{audio_base64}",
            "voice": voice_name
        })
        
    except Exception as e:
        print(f"Error en TTS: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/voices", methods=["GET"])
def get_voices():
    """Obtener lista de voces disponibles"""
    try:
        # Devolver las voces preconfiguradas
        voices_list = []
        for key, voice_id in EDGE_VOICES_ES.items():
            # Extraer información de la voz
            parts = voice_id.split('-')
            locale = f"{parts[0]}-{parts[1]}"
            name = parts[2].replace('Neural', '')
            
            country_map = {
                'es-ES': 'España',
                'es-MX': 'México',
                'es-AR': 'Argentina',
                'es-CO': 'Colombia',
                'es-CL': 'Chile'
            }
            
            gender_map = {
                'Helena': 'Femenino',
                'Alvaro': 'Masculino',
                'Elvira': 'Femenino',
                'Dalia': 'Femenino',
                'Jorge': 'Masculino',
                'Larissa': 'Femenino',
                'Elena': 'Femenino',
                'Tomas': 'Masculino',
                'Salome': 'Femenino',
                'Gonzalo': 'Masculino'
            }
            
            voices_list.append({
                "id": key,
                "name": name,
                "voice_id": voice_id,
                "locale": locale,
                "country": country_map.get(locale, locale),
                "gender": gender_map.get(name, 'Desconocido')
            })
        
        return jsonify({
            "voices": voices_list,
            "presets": EDGE_VOICES_ES,
            "enabled": True
        })
        
    except Exception as e:
        print(f"Error obteniendo voces: {e}")
        return jsonify({
            "voices": [],
            "presets": EDGE_VOICES_ES,
            "enabled": False,
            "error": str(e)
        })

@app.route("/test", methods=["GET"])
def test_edge_tts():
    """Endpoint de prueba para verificar Edge TTS"""
    try:
        # Prueba simple
        test_text = "Hola, esta es una prueba de Edge TTS"
        audio_base64 = run_async(generate_speech_async(test_text, 'es-ES-HelenaNeural'))
        
        return jsonify({
            "status": "success",
            "message": "Edge TTS funcionando correctamente",
            "audio_length": len(audio_base64)
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        })

if __name__ == "__main__":
    print("=" * 60)
    print("🎙️ Servidor con Edge TTS (Voces Microsoft) iniciado")
    print("=" * 60)
    print("✅ Voces naturales de Microsoft disponibles GRATIS")
    print("\n📢 Voces disponibles:")
    for key, value in EDGE_VOICES_ES.items():
        print(f"   - {key}: {value}")
    print("\n🔧 Endpoints disponibles:")
    print("   - GET  /         : Interfaz web")
    print("   - POST /chat     : Chat con Llama3")
    print("   - POST /tts      : Generar audio")
    print("   - GET  /voices   : Lista de voces")
    print("   - GET  /test     : Probar Edge TTS")
    print("\n🌐 Abre en tu navegador: http://localhost:5000")
    print("=" * 60)
    
    # Verificar Edge TTS
    try:
        import edge_tts
        print("✅ Edge TTS instalado correctamente")
    except ImportError:
        print("❌ Edge TTS no está instalado")
        print("   Ejecuta: pip install edge-tts")
    
    app.run(debug=False, host='0.0.0.0', port=5000, threaded=True)