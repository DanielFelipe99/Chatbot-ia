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
from typing import Optional

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Desactivar warnings de SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
CORS(app)

OLLAMA_API_URL = "http://localhost:11434/api/generate"
AVAS2_URL = "https://investic.narino.gov.co/avas-2/"

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
CACHE_TIMEOUT = 3600  # 1 hora

# Claves de materias y palabras clave
SUBJECT_KEYWORDS = {
    'ciencias_naturales': [
        'ciencias naturales', 'naturales', 'ciencia', 'biologia', 'biología',
        'seres vivos', 'ecosistema', 'ciclo del agua', 'agua', 'sol'
    ],
    'ciencias_sociales': [
        'ciencias sociales', 'sociales', 'historia', 'geografía', 'democracia',
        'cultura', 'sociedad'
    ],
    'matematicas': [
        'matemáticas', 'matematicas', 'aritmética', 'aritmetica', 'álgebra', 'algebra',
        'geometría', 'geometria', 'estadística', 'estadistica', 'cálculo', 'calculo'
    ],
    'espanol': [
        'español', 'espanol', 'gramática', 'gramatica', 'literatura', 'lectura',
        'comprensión lectora', 'comprension lectora', 'escritura', 'ortografía', 'ortografia'
    ],
    'ingles': [
        'inglés', 'ingles', 'grammar', 'vocabulary', 'reading', 'writing', 'speaking'
    ]
}

# Tarjetas clave dentro de cada módulo
CARD_KEYWORDS = {
    'mi_curso': ['mi curso', 'mi aula', 'mi clase'],
    'temas': ['temas', 'contenidos', 'contenido', 'unidades', 'lecciones'],
    'anuncios': ['anuncios', 'novedades'],
    'tareas': ['tareas', 'actividades', 'evaluaciones'],
    'comunicate': ['comunicate', 'comunícate', 'contacto', 'foro'],
    'aprueba': ['aprueba', 'aprobación', 'aprobacion'],
    'puntuacion': ['puntuación', 'puntuacion', 'puntaje'],
    'investiga': ['investiga', 'investigación', 'investigacion']
}

# Overrides manuales de tarjetas por materia (URLs conocidas/proporcionadas)
SUBJECT_CARD_OVERRIDES = {
    'ciencias_naturales': {
        'mi_curso': 'https://testsed.narino.gov.co/Naturales/sistema/descripcion.php'
        # 'temas': 'URL_SI_EXISTE'  # Podemos añadirla cuando esté disponible
    }
}

# Información estructurada actualizada basada en el HTML real
AVAS2_REAL_INFO = {
    "titulo": "AVAS-2 - Ambientes Virtuales de Aprendizaje",
    "plataforma": "Investic - Secretaría de Educación de Nariño",
    "url_base": "https://investic.narino.gov.co/avas-2/",
    "asignaturas": {
        "ciencias_naturales": {
            "nombre": "Ciencias Naturales",
            "url": "https://investic.narino.gov.co/avas-2/ava-ciencias-naturales/",
            "descripcion": "Ambiente virtual para el aprendizaje de ciencias naturales",
            "imagen": "ciencias-naturales.png",
            "temas_posibles": ["Seres de mi entorno", "Seres vivos e inertes", "Adaptacion de los seres vivos", "ciclo de la vida", "Tipos de animales",
                      "Necesidades de los seres vivos","Manejo del agua","Ciclo del agua","El sol como fuente de energia, luz y calor",
                      "El sol en nuestro entorno","Guardianes del agua"]
        },
        "ciencias_sociales": {
            "nombre": "Ciencias Sociales",
            "url": "https://investic.narino.gov.co/avas-2/ava-ciencias-sociales/",
            "descripcion": "Ambiente virtual para el aprendizaje de ciencias sociales",
            "imagen": "ChatGPT-Image-22-ago-2025-10_35_16.png",
            "temas_posibles": ["Identidad Cultural", "Cultura","Diversidad","Tipos de agresiones","El conflicto", "Organizaciones sociales", 
                        "La familia, escuela, el barrio","La convivencia", "Manual de convivencia","Derechos y deberes","Sociedad"]
        },
        "matematicas": {
            "nombre": "Matemáticas",
            "url": "https://investic.narino.gov.co/avas-2/ava-matematicas/",
            "descripcion": "Ambiente virtual para el aprendizaje de matemáticas",
            "imagen": "ChatGPT-Image-22-ago-2025-10_41_12.png",
            "temas_posibles": ["Aprende matematicas cuidando el ambiente", "Aprende matematicas administrando una tienda"]
        },
        "espanol": {
            "nombre": "Español",
            "url": "https://investic.narino.gov.co/avas-2/ava-espanol/",
            "descripcion": "Ambiente virtual para el aprendizaje de español",
            "imagen": "ChatGPT-Image-22-ago-2025-10_59_35.png",
            "temas_posibles": ["Los textos", "La narracion", "La anecdota", "La receta", "Elaboracion de textos informativos",
                        "Literatura", "La fabula, el cuento y poemas", "Los mitos y leyendas", "Las coplas, retahila y cancion","El periodico",
                        "La noticia","El telefono" , "La carta", "medios de comunicacion"]
        },
        "ingles": {
            "nombre": "Inglés",
            "url": "https://investic.narino.gov.co/avas-2/ava-ingles/",
            "descripcion": "Ambiente virtual para el aprendizaje de inglés",
            "imagen": "ChatGPT-Image-22-ago-2025-11_15_17.png",
            "temas_posibles": ["Whats your name?", "The alphabet", "Greetings", "The colors", "The family", "The numbers", "Domestic and wild animals",
                    "The body","Objects of my house","School supplies","Geometric figures","Fruits and vegetables"]
        }
    },
    "otros_recursos": {
        "ovas": "https://investic.narino.gov.co/ovas-3/",
        "agau": "https://agauregional2.talentum.edu.co/",
        "mundo_3d": "https://si.aulasregionalfase2.com/menu",
        "colcha_tesoros": "https://colchadetesoros.narino.gov.co/",
        "aulas_steam": "https://steam.narino.gov.co/"
    }
}

# Crear loop de asyncio
loop = None
thread = None

# Directorio de documentos locales (transcripciones, guías, etc.)
BASE_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = str(BASE_DIR / 'docs')
DOCS_CACHE = {
    'timestamp': 0,
    'docs': []  # lista de {path, text, subject}
}

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

def scrape_avas2_real():
    """Scraping real basado en la estructura HTML actual de AVAS-2"""
    try:
        logger.info("🌐 Scrapeando AVAS-2 con selectores específicos...")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.9',
        }
        
        response = requests.get(AVAS2_URL, headers=headers, verify=False, timeout=20)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extraer información real de la página
        info = {
            'titulo': 'AVAS-2 - Ambientes Virtuales de Aprendizaje',
            'asignaturas': [],
            'navegacion': [],
            'descripcion': '',
            'estructura_real': {}
        }
        
        # Buscar el título real
        title_elem = soup.find('title')
        if title_elem:
            info['titulo'] = title_elem.get_text().strip()
        
        # Extraer las asignaturas desde los módulos Divi (et_pb_blurb)
        blurbs = soup.find_all('div', class_='et_pb_blurb')
        for blurb in blurbs:
            header = blurb.find('h4', class_='et_pb_module_header')
            if header:
                link = header.find('a')
                if link:
                    asignatura = {
                        'nombre': link.get_text().strip(),
                        'url': link.get('href', ''),
                        'descripcion': ''
                    }
                    
                    # Buscar descripción
                    desc_div = blurb.find('div', class_='et_pb_blurb_description')
                    if desc_div:
                        desc_text = desc_div.get_text().strip()
                        # Filtrar el texto placeholder
                        if not desc_text.startswith("Your content goes here"):
                            asignatura['descripcion'] = desc_text
                    
                    # Buscar imagen
                    img = blurb.find('img')
                    if img:
                        asignatura['imagen'] = img.get('src', '')
                        asignatura['imagen_alt'] = img.get('alt', '')
                    
                    info['asignaturas'].append(asignatura)
        
        # Extraer menú de navegación
        nav_menu = soup.find('ul', class_='et-menu')
        if nav_menu:
            for item in nav_menu.find_all('a'):
                nav_text = item.get_text().strip()
                nav_href = item.get('href', '')
                if nav_text and nav_href:
                    info['navegacion'].append({
                        'texto': nav_text,
                        'url': nav_href
                    })
        
        # Extraer breadcrumbs si existen
        breadcrumbs = soup.find('div', class_='lwp-breadcrumbs')
        if breadcrumbs:
            info['breadcrumbs'] = breadcrumbs.get_text().strip()
        
        # Guardar en cache
        SCRAPED_CACHE['avas2'] = {
            'data': info,
            'timestamp': time.time()
        }
        
        logger.info(f"✅ Scraping exitoso. Asignaturas encontradas: {len(info['asignaturas'])}")
        return info
        
    except Exception as e:
        logger.error(f"❌ Error en scraping: {str(e)}")
        # Devolver información estructurada como respaldo
        return {
            'error': str(e),
            'fallback_data': AVAS2_REAL_INFO
        }

def normalize_text(text):
    if not text:
        return ''
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()

def fetch_soup(url: str, headers: Optional[dict] = None):
    try:
        default_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.9',
        }
        if headers:
            default_headers.update(headers)
        resp = requests.get(url, headers=default_headers, verify=False, timeout=20)
        resp.raise_for_status()
        return BeautifulSoup(resp.content, 'html.parser'), resp.url
    except Exception as e:
        logger.error(f"Error obteniendo URL {url}: {e}")
        return None, url

def extract_readable_text(soup: BeautifulSoup) -> str:
    if soup is None:
        return ''
    # Preferir contenedores de contenido comunes (WordPress/Divi)
    selectors = [
        'article', '.entry-content', 'main', '.et_pb_section', '.et_pb_text', '.container', '#content'
    ]
    texts = []
    nodes = []
    for sel in selectors:
        nodes = soup.select(sel)
        if nodes:
            break
    if not nodes:
        nodes = [soup.body or soup]
    for node in nodes:
        for el in node.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'li']):
            t = el.get_text(separator=' ', strip=True)
            if t:
                texts.append(t)
    content = '\n'.join(texts)
    # Reducir ruido
    content = re.sub(r"\n{2,}", "\n", content)
    return content.strip()

def guess_subject_from_path(path_str: str) -> str:
    p = normalize_text(path_str)
    if 'social' in p:
        return 'ciencias_sociales'
    if 'natural' in p or 'ciencia' in p:
        return 'ciencias_naturales'
    if 'mate' in p:
        return 'matematicas'
    if 'espan' in p or 'españ' in p:
        return 'espanol'
    if 'ingl' in p:
        return 'ingles'
    return 'ciencias_naturales'

def load_documents() -> list:
    """Cargar documentos desde docs/ (pdf, txt, md) y cachearlos"""
    docs: list[dict] = []
    try:
        os.makedirs(DOCS_DIR, exist_ok=True)
        patterns = [
            os.path.join(DOCS_DIR, '*.pdf'),
            os.path.join(DOCS_DIR, '*.txt'),
            os.path.join(DOCS_DIR, '*.md'),
        ]
        files = []
        for pat in patterns:
            files.extend(glob.glob(pat))
        for path in files:
            text = ''
            if path.lower().endswith('.pdf'):
                try:
                    import pdfplumber
                    with pdfplumber.open(path) as pdf:
                        pages = [page.extract_text() or '' for page in pdf.pages]
                        text = '\n'.join(pages)
                except Exception as e:
                    logger.warning(f"No se pudo leer PDF {path}: {e}")
                    continue
            else:
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        text = f.read()
                except Exception as e:
                    logger.warning(f"No se pudo leer archivo {path}: {e}")
                    continue
            text = re.sub(r"\s+", " ", text).strip()
            if not text:
                continue
            docs.append({
                'path': path,
                'text': text,
                'subject': guess_subject_from_path(path)
            })
        DOCS_CACHE['docs'] = docs
        DOCS_CACHE['timestamp'] = time.time()
        logger.info(f"📚 Documentos cargados: {len(docs)}")
    except Exception as e:
        logger.error(f"Error cargando documentos: {e}")
    return docs

def ensure_docs_loaded():
    if not DOCS_CACHE['docs'] or (time.time() - DOCS_CACHE['timestamp']) > CACHE_TIMEOUT:
        load_documents()

def extract_snippets(text: str, query: str, max_chars: int = 1200) -> str:
    q_words = [w for w in normalize_text(query).split() if len(w) > 2]
    # Dividir por puntos o saltos de línea para intentar mantener coherencia
    parts = re.split(r"(?<=[\.!?])\s+|\n+", text)
    selected = []
    score = 0
    for p in parts:
        pn = normalize_text(p)
        hits = sum(1 for w in q_words if w in pn)
        if hits:
            selected.append(p.strip())
            score += hits
        if len(' '.join(selected)) >= max_chars:
            break
    if not selected:
        return text[:max_chars]
    return ' '.join(selected)[:max_chars]

def search_docs(query: str, subject: Optional[str] = None, limit: int = 2) -> list:
    ensure_docs_loaded()
    docs = DOCS_CACHE['docs']
    if subject:
        docs = [d for d in docs if d.get('subject') == subject]
    scored = []
    qn = normalize_text(query)
    for d in docs:
        tn = normalize_text(d['text'])
        # Puntuación simple por presencia de palabras clave
        hits = sum(1 for w in set(qn.split()) if len(w) > 3 and w in tn)
        subj_bonus = 3 if subject and d.get('subject') == subject else 0
        scored.append((hits + subj_bonus, d))
    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for sc, d in scored[:limit]:
        if sc <= 0:
            continue
        snippet = extract_snippets(d['text'], query)
        results.append({
            'path': d['path'],
            'subject': d.get('subject'),
            'snippet': snippet
        })
    return results

def find_modules_on_main(main_url: str) -> dict:
    soup, final_url = fetch_soup(main_url)
    modules: dict[str, str] = {}
    if soup is None:
        return modules
    # Buscar anclas que contengan los nombres de las asignaturas
    subject_names = {
        'ciencias_naturales': ['ciencias naturales'],
        'ciencias_sociales': ['ciencias sociales'],
        'matematicas': ['matemáticas', 'matematicas'],
        'espanol': ['español', 'espanol'],
        'ingles': ['inglés', 'ingles']
    }
    for a in soup.find_all('a'):
        text = normalize_text(a.get_text())
        href = a.get('href')
        if not href:
            continue
        for key, name_list in subject_names.items():
            if any(name in text for name in name_list) or (f"ava-{key.replace('_', '-')}") in normalize_text(href):
                modules[key] = urljoin(final_url, href)
    # Fallback a datos conocidos si algo falta
    for key, asig in AVAS2_REAL_INFO['asignaturas'].items():
        if key not in modules and asig.get('url'):
            modules[key] = asig['url']
    return modules

def find_cards_in_module(module_url: str) -> dict:
    soup, final_url = fetch_soup(module_url)
    cards: dict[str, str] = {}
    if soup is None:
        return cards
    # Buscar tarjetas por texto del enlace
    for a in soup.find_all('a'):
        text = normalize_text(a.get_text())
        href = a.get('href')
        if not href:
            continue
        for card_key, variants in CARD_KEYWORDS.items():
            if any(v in text for v in variants):
                cards[card_key] = urljoin(final_url, href)
    return cards

def scrape_subject(subject_key: str) -> dict:
    logger.info(f"🔎 Scrapeando materia: {subject_key}")
    modules = find_modules_on_main(AVAS2_URL)
    module_url = modules.get(subject_key)
    if not module_url:
        logger.warning(f"No se encontró URL del módulo para {subject_key}")
        return {}
    cards = find_cards_in_module(module_url)
    # Aplicar overrides manuales
    if subject_key in SUBJECT_CARD_OVERRIDES:
        cards.update(SUBJECT_CARD_OVERRIDES[subject_key])
    subject_data: dict = {
        'subject': subject_key,
        'module_url': module_url,
        'cards': cards,
        'content': {}
    }
    # Solo priorizar Mi curso y Temas
    for key in ['mi_curso', 'temas']:
        url = cards.get(key)
        if url:
            soup, _ = fetch_soup(url)
            text = extract_readable_text(soup)
            subject_data['content'][key] = {
                'url': url,
                'text': text[:100000]  # limitar tamaño
            }
    SCRAPED_CACHE[f'subject:{subject_key}'] = {
        'data': subject_data,
        'timestamp': time.time()
    }
    return subject_data

def get_subject_data(subject_key: str) -> dict:
    cached = SCRAPED_CACHE.get(f'subject:{subject_key}')
    if cached and (time.time() - cached['timestamp']) < CACHE_TIMEOUT:
        return cached['data']
    return scrape_subject(subject_key)

def get_avas2_info():
    """Obtener información de AVAS-2 desde caché o scraping"""
    cached = SCRAPED_CACHE.get('avas2')
    if cached and (time.time() - cached['timestamp']) < CACHE_TIMEOUT:
        logger.info("📦 Usando información AVAS-2 en cache")
        return cached['data']
    else:
        logger.info("🔄 Realizando scraping de AVAS-2...")
        return scrape_avas2_real()

def crear_contexto_avas2(info_scraping, subject_data: Optional[dict] = None, docs_snippets: Optional[list] = None):
    """Crear un contexto estructurado para el modelo"""
    contexto = """
GUÍA EDUCATIVA PARA EXPLICAR A NIÑOS
====================================
Habla con palabras sencillas y ejemplos cotidianos.
Evita mencionar nombres de plataformas o marcas.

ASIGNATURAS DISPONIBLES:
"""
    
    # Si tenemos información del scraping, usarla
    if info_scraping and 'asignaturas' in info_scraping and info_scraping['asignaturas']:
        for asig in info_scraping['asignaturas']:
            contexto += f"""
- {asig.get('nombre', 'Sin nombre')}
  URL: {asig.get('url', 'No disponible')}
  Descripción: {asig.get('descripcion', 'Ambiente virtual de aprendizaje')}
"""
    else:
        # Usar información de respaldo
        for key, asig in AVAS2_REAL_INFO['asignaturas'].items():
            contexto += f"""
- {asig['nombre']}
  URL: {asig['url']}
  Descripción: {asig['descripcion']}
  Temas posibles: {', '.join(asig['temas_posibles'])}
"""
    
    contexto += """

RECUERDA CÓMO EXPLICAR:
- Usa frases cortas y claras.
- Da uno o dos ejemplos simples.
- Puedes proponer una mini-actividad o juego.
"""
    # Inyectar información específica de la materia si está disponible
    if subject_data and subject_data.get('content'):
        contexto += """

CONTENIDOS CLAVE DE ESTA MATERIA
=================================
"""
        content = subject_data['content']
        if 'mi_curso' in content:
            contexto += f"""
- Sección: Mi curso (resumen)
{content['mi_curso'].get('text', '')[:2000]}
"""
        if 'temas' in content:
            contexto += f"""
- Sección: Temas (resumen)
{content['temas'].get('text', '')[:2000]}
"""

    # Incluir fragmentos de documentos locales si existen
    if docs_snippets:
        contexto += """

APUNTES Y TRANSCRIPCIONES
=========================
"""
        for i, sn in enumerate(docs_snippets, start=1):
            contexto += f"""
- Fuente {i} (resumen):
{sn.get('snippet', '')}
"""

    return contexto

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
        # Obtener información de AVAS-2 (general)
        info_avas2 = get_avas2_info()

        # Detectar materia a partir del prompt
        prompt_norm = normalize_text(prompt)
        detected_subject = None
        for subject_key, keywords in SUBJECT_KEYWORDS.items():
            if any(k in prompt_norm for k in keywords):
                detected_subject = subject_key
                break

        # Obtener contenido específico de la materia si aplica (prioridad: ciencias naturales)
        subject_data = None
        if detected_subject:
            subject_data = get_subject_data(detected_subject)
        elif 'ciencias' in prompt_norm:
            subject_data = get_subject_data('ciencias_naturales')

        # Recuperar fragmentos de documentos locales (si existen)
        docs_snippets = search_docs(prompt_norm, detected_subject, limit=2)

        # Crear contexto estructurado con posible contenido específico y documentos
        contexto_avas2 = crear_contexto_avas2(info_avas2, subject_data, docs_snippets)
        
        # Determinar si la pregunta necesita información específica
        palabras_clave = ['ciencias', 'matemática', 'español', 'inglés', 'sociales', 
                         'asignatura', 'materia', 'curso', 'tarea', 'actividad', 
                         'avas', 'plataforma', 'recursos']
        
        es_pregunta_educativa = any(palabra in prompt.lower() for palabra in palabras_clave)
        
        # Crear prompt optimizado
        if es_pregunta_educativa:
            prompt_final = f"""
{contexto_avas2}

INSTRUCCIONES PARA EL ASISTENTE:
================================
Eres "Profe Alex", explicas a niños y niñas de primaria.

REGLAS IMPORTANTES:
1. Responde SOLO sobre temas educativos.
2. No menciones nombres de plataformas, evita la palabra AVAS-2.
3. Si preguntan por una asignatura, proporciona:
   - Nombre exacto
   - Descripción breve de los contenidos
   - Una mini-actividad o ejemplo sencillo
4. Mantén un tono infantil, claro y motivador
5. Si no tienes información específica, dilo con amabilidad y sugiere una idea para explorar

PREGUNTA DEL USUARIO: {prompt}

RESPUESTA (Sé específico y útil):
"""
        else:
            # Para preguntas generales
            prompt_final = f"""
{contexto_avas2}

Eres "Profe Alex", un profe amable para niños y niñas.

La pregunta del usuario no parece estar relacionada con temas educativos.
Por favor, redirige amablemente la conversación hacia temas educativos y explica de forma simple qué temas puedes ayudar a aprender.

PREGUNTA DEL USUARIO: {prompt}

RESPUESTA BREVE Y AMABLE:
"""

        # Configuración mejorada para Llama3
        payload = {
            "model": "llama3",
            "prompt": prompt_final,
            "stream": False,
            "temperature": 0.7,
            "top_p": 0.9,
            "max_tokens": 700,
            "system": "Eres 'Profe Alex', un asistente que enseña a niños y niñas con lenguaje sencillo, sin mencionar plataformas ni marcas."
        }

        response = requests.post(OLLAMA_API_URL, json=payload, timeout=120)

        if response.status_code != 200:
            logger.error(f"Error en Ollama API: {response.status_code}")
            return jsonify({"error": "Error en el servicio de IA"}), 500

        ollama_data = response.json()
        response_text = ollama_data.get("response", "")
        
        # Agregar información adicional si es relevante
        metadata = {
            "response": response_text,
            "context_used": True,
            "source": AVAS2_URL,
            "asignaturas_disponibles": len(info_avas2.get('asignaturas', [])) if info_avas2 else 5,
            "subject": subject_data.get('subject') if subject_data else None,
            "subject_cards": list(subject_data.get('cards', {}).keys()) if subject_data else [],
            "docs_used": len(docs_snippets)
        }

        return jsonify(metadata)

    except Exception as e:
        logger.error(f"Error en chat endpoint: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/scrape/refresh", methods=["POST"])
def refresh_scrape():
    """Forzar actualización del scraping"""
    SCRAPED_CACHE.clear()
    result = scrape_avas2_real()
    success = 'error' not in result or (result.get('asignaturas') and len(result['asignaturas']) > 0)
    
    return jsonify({
        "success": success,
        "message": "Información actualizada correctamente" if success else "Error al actualizar",
        "asignaturas_encontradas": len(result.get('asignaturas', [])) if 'asignaturas' in result else 0
    })

@app.route("/scrape/subject/<subject>", methods=["POST"])
def refresh_subject(subject):
    """Forzar scraping de una materia específica (por ejemplo: ciencias_naturales)"""
    data = scrape_subject(subject)
    return jsonify({
        "subject": subject,
        "module_url": data.get('module_url'),
        "cards": data.get('cards', {}),
        "content_sections": list(data.get('content', {}).keys()),
        "ok": bool(data)
    })

@app.route("/scrape/data", methods=["GET"])
def get_scraped_data():
    """Obtener datos scrapeados por materia para depuración"""
    subject = request.args.get('subject', 'ciencias_naturales')
    data = get_subject_data(subject)
    # No devolver texto completo para no sobrecargar
    preview = {}
    if data and 'content' in data:
        for k, v in data['content'].items():
            preview[k] = {
                'url': v.get('url'),
                'text_preview': (v.get('text', '')[:500] + ('...' if len(v.get('text', '')) > 500 else ''))
            }
    return jsonify({
        'subject': subject,
        'module_url': data.get('module_url') if data else None,
        'cards': data.get('cards', {}) if data else {},
        'content_preview': preview
    })

@app.route("/scrape/status", methods=["GET"])
def scrape_status():
    """Obtener estado del scraping"""
    cached = SCRAPED_CACHE.get('avas2')
    if cached:
        return jsonify({
            "cached": True,
            "age_seconds": time.time() - cached['timestamp'],
            "source": AVAS2_URL,
            "asignaturas": len(cached['data'].get('asignaturas', [])),
            "last_update": time.strftime('%Y-%m-%d %H:%M:%S', 
                                        time.localtime(cached['timestamp']))
        })
    else:
        return jsonify({
            "cached": False,
            "source": AVAS2_URL
        })

# Mantener las funciones de TTS existentes
async def generate_speech_async(text, voice_name):
    """Generar audio de forma asíncrona"""
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
    """Endpoint para generar audio con Edge TTS"""
    data = request.get_json()
    text = data.get("text", "")
    voice = data.get("voice", "helena")
    
    if not text:
        return jsonify({"error": "No text provided"}), 400
    
    try:
        voice_name = EDGE_VOICES_ES.get(voice, EDGE_VOICES_ES['helena'])
        logger.info(f"Generando audio con voz: {voice_name}")
        
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
    """Obtener lista de voces disponibles"""
    voices_list = []
    for key, voice_id in EDGE_VOICES_ES.items():
        parts = voice_id.split('-')
        locale = f"{parts[0]}-{parts[1]}"
        name = parts[2].replace('Neural', '')
        
        country_map = {
            'es-ES': 'España',
            'es-MX': 'México',
            'es-AR': 'Argentina',
            'es-CO': 'Colombia'
        }
        
        voices_list.append({
            "id": key,
            "name": name,
            "voice_id": voice_id,
            "locale": locale,
            "country": country_map.get(locale, locale)
        })
    
    return jsonify({
        "voices": voices_list,
        "enabled": True
    })

if __name__ == "__main__":
    print("=" * 60)
    print("🎓 Asistente AVAS-2 con Scraping Mejorado")
    print("=" * 60)
    print("✅ Sistema iniciado correctamente")
    print("📚 Plataforma: AVAS-2 - Secretaría de Educación de Nariño")
    print("🌐 URL Base: https://investic.narino.gov.co/avas-2/")
    print("\n📖 Asignaturas disponibles:")
    for key, asig in AVAS2_REAL_INFO['asignaturas'].items():
        print(f"   - {asig['nombre']}")
    print("\n🔧 Endpoints disponibles:")
    print("   - GET  /         : Interfaz web")
    print("   - POST /chat     : Chat con Llama3")
    print("   - POST /tts      : Generar audio")
    print("   - GET  /voices   : Lista de voces")
    print("   - POST /scrape/refresh : Actualizar información")
    print("   - GET  /scrape/status  : Estado del scraping")
    print("\n🌐 Abre en tu navegador: http://localhost:5000")
    print("=" * 60)
    
    app.run(debug=False, host='0.0.0.0', port=5000, threaded=True)