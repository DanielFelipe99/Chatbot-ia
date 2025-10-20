# app/rag_system.py
import chromadb
from chromadb.config import Settings
import os
import glob
from sentence_transformers import SentenceTransformer
import logging
import re
import hashlib
import json
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
logger = logging.getLogger(__name__)

class RAGSystem:
    def __init__(self, docs_dir="../docs"):
        self.docs_dir = docs_dir
        
        abs_path = os.path.abspath(docs_dir)
        logger.info(f"Buscando documentos en: {abs_path}")
        
        if not os.path.exists(abs_path):
            logger.error(f"La carpeta {abs_path} no existe!")
            raise FileNotFoundError(f"No se encuentra la carpeta: {abs_path}")
        
        txt_files = glob.glob(os.path.join(abs_path, "*.txt"))
        logger.info(f"Archivos TXT encontrados: {[os.path.basename(f) for f in txt_files]}")
        
        if not txt_files:
            logger.warning("No se encontraron archivos TXT en docs/")
        
        logger.info("Cargando modelo de embeddings...")
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
        logger.info("Modelo de embeddings cargado")
        
        db_path = os.path.abspath("./chroma_db")
        os.makedirs(db_path, exist_ok=True)
        
        self.client = chromadb.PersistentClient(
            path=db_path,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Verificar si los archivos cambiaron
        needs_reindex = self._check_files_changed()
        
        if needs_reindex:
            logger.info("Archivos modificados detectados, reindexando...")
            try:
                self.client.delete_collection("docs_educativos")
            except:
                pass
            
            self.collection = self.client.create_collection("docs_educativos")
            self.index_documents()
            
            # Guardar hash de los archivos actuales
            self._save_files_hash()
        else:
            logger.info("Usando índice existente (archivos sin cambios)")
            self.collection = self.client.get_collection("docs_educativos")
            logger.info(f"Chunks en base de datos: {self.collection.count()}")

        self.query_cache = {}
        self.result_cache = {}
    
    @lru_cache(maxsize=100)
    def _get_embedding_cached(self, text):
        """Embeddings con caché para queries repetidas"""
        return tuple(self.embedder.encode(text).tolist())
    
    def search_forced1(self, query, n_results=2):
        logger.info(f"Buscando: '{query}'")
        
        if self.collection.count() == 0:
            return "", [], 999
        
        # Usar cachÃ© de embeddings
        query_lower = query.lower().strip()
        if query_lower in self.query_cache:
            logger.info("Usando embedding cacheado")
            query_embedding = self.query_cache[query_lower]
        else:
            query_embedding = list(self._get_embedding_cached(query))
            self.query_cache[query_lower] = query_embedding

        with ThreadPoolExecutor(max_workers=2) as executor:
            future = executor.submit(
                self.collection.query,
                query_embeddings=[query_embedding],
                n_results=3
            )
            results = future.result(timeout=2)

    def _get_files_hash(self):
        """Calcular hash de todos los archivos .txt"""
        abs_docs_dir = os.path.abspath(self.docs_dir)
        files_data = {}
        
        for filepath in glob.glob(os.path.join(abs_docs_dir, "*.txt")):
            filename = os.path.basename(filepath)
            
            # Hash del contenido + fecha de modificaciÃ³n
            with open(filepath, 'rb') as f:
                content_hash = hashlib.md5(f.read()).hexdigest()
            
            mod_time = os.path.getmtime(filepath)
            
            files_data[filename] = {
                'hash': content_hash,
                'modified': mod_time,
                'size': os.path.getsize(filepath)
            }
        
        return files_data

    def _save_files_hash(self):
        """Guardar hash de archivos para comparación futura"""
        files_data = self._get_files_hash()
        hash_file = os.path.join(os.path.abspath("./chroma_db"), "files_hash.json")
        
        with open(hash_file, 'w', encoding='utf-8') as f:
            json.dump(files_data, f, indent=2)
        
        logger.info("âœ… Hash de archivos guardado")

    def _check_files_changed(self):
        """Verificar si los archivos cambiaron desde la última indexación"""
        hash_file = os.path.join(os.path.abspath("./chroma_db"), "files_hash.json")
        
        # Si no existe el hash, necesita indexar
        if not os.path.exists(hash_file):
            logger.info("No existe hash previo, necesita indexar")
            return True
        
        # Leer hash anterior
        try:
            with open(hash_file, 'r', encoding='utf-8') as f:
                old_hash = json.load(f)
        except:
            logger.warning("Error leyendo hash anterior")
            return True
        
        # Comparar con hash actual
        current_hash = self._get_files_hash()
        
        # Verificar si hay archivos nuevos o eliminados
        old_files = set(old_hash.keys())
        current_files = set(current_hash.keys())
        
        if old_files != current_files:
            logger.info(f"Cambio en archivos: {old_files} vs {current_files}")
            return True
        
        # Verificar si algÃºn archivo cambiÃ³
        for filename, data in current_hash.items():
            if filename not in old_hash:
                logger.info(f"Archivo nuevo: {filename}")
                return True
            
            if data['hash'] != old_hash[filename]['hash']:
                logger.info(f"Archivo modificado: {filename}")
                return True
            
            if data['size'] != old_hash[filename]['size']:
                logger.info(f"Tamaño cambió: {filename}")
                return True

        logger.info("✔️ Sin cambios en archivos")
        return False
    
    def _check_reindex_needed(self):
        """Verificar si necesita reindexar comparando fechas de modificación"""
        try:
            collection = self.client.get_collection("docs_educativos")
            stored_count = collection.count()
            
            # Si no hay datos, reindexar
            if stored_count == 0:
                logger.info("Base de datos vaci­a, se necesita indexar")
                return True
            
            # Contar archivos actuales
            abs_docs_dir = os.path.abspath(self.docs_dir)
            current_files = glob.glob(os.path.join(abs_docs_dir, "*.txt"))
            
            # Si cambiÃ³ el nÃºmero de archivos, reindexar
            if len(current_files) == 0:
                logger.warning("No hay archivos TXT")
                return False
            
            logger.info(f"indice existente con {stored_count} chunks")
            return False
            
        except Exception as e:
            logger.info(f"No existe i­ndice previo: {e}")
            return True
    
    def index_documents(self):
        """Indexar documentos TXT con chunks optimizados"""
        doc_count = 0
        chunk_count = 0
        
        abs_docs_dir = os.path.abspath(self.docs_dir)
        pattern = os.path.join(abs_docs_dir, "*.txt")
        
        logger.info(f"Buscando archivos con patron: {pattern}")
        
        for filepath in glob.glob(pattern):
            doc_count += 1
            filename = os.path.basename(filepath)
            logger.info(f"Indexando: {filename}")
            
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                # Limpiar contenido
                content = self._clean_text(content)

                logger.info(f"   - Tamaño: {len(content)} caracteres")
                logger.info(f"   - Preview: {content[:100]}...")
                
                # CHUNKS MÁS GRANDES para mejor contexto
                chunk_size = 600  # Aumentado de 400
                overlap = 150     # Aumentado de 100
                
                chunks = self._create_smart_chunks(content, chunk_size, overlap)
                
                logger.info(f"   - Dividido en {len(chunks)} chunks")
                
                # Indexar cada chunk
                materia = self.detect_subject(filename)
                
                for i, chunk in enumerate(chunks):
                    chunk_count += 1
                    
                    # Generar embedding
                    embedding = self.embedder.encode(chunk).tolist()
                    
                    # AÃ±adir a ChromaDB
                    self.collection.add(
                        embeddings=[embedding],
                        documents=[chunk],
                        metadatas=[{
                            "source": filename,
                            "chunk_id": i,
                            "subject": materia,
                            "chunk_size": len(chunk),
                            "total_chunks": len(chunks)
                        }],
                        ids=[f"{filename}_{i}"]
                    )
                    
            except Exception as e:
                logger.error(f"Error indexando {filename}: {e}")

        logger.info(f"✔️ Indexación completa: {doc_count} documentos, {chunk_count} chunks")

        # Verificar indexación
        total = self.collection.count()
        logger.info(f"Total en base de datos: {total} chunks")
        
        if total == 0:
            logger.error("✔️ No se indexó ningun chunk!")
    
    def _clean_text(self, text):
        """Limpiar y normalizar texto para mejores embeddings"""
        # Eliminar formato de preguntas/respuestas que confunde
        text = re.sub(r'Pregunta:\s*', '', text)
        text = re.sub(r'Respuesta:\s*', '', text)
        text = re.sub(r'Ejemplo:\s*', 'Por ejemplo: ', text)
        
        # Eliminar mÃºltiples espacios
        text = re.sub(r'\s+', ' ', text)
        
        # Eliminar saltos de lÃ­nea excesivos
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()

    def _create_smart_chunks(self, text, chunk_size, overlap):
        """Crear chunks con contexto de título"""
        chunks = []
        
        # Detectar secciones con títulos (TODO EN MAYÚSCULAS o con #)
        sections = re.split(r'\n(?=[A-ZÁÉÍÓÚ\s]{3,}|#)', text)
        
        for section in sections:
            section = section.strip()
            if not section or len(section) < 50:
                continue
            
            # Extraer tÃ­tulo si existe
            lines = section.split('\n')
            title = ""
            content = section
            
            if lines[0].isupper() or lines[0].startswith('#'):
                title = lines[0].replace('#', '').strip()
                content = '\n'.join(lines[1:]).strip()
            
            # Dividir en oraciones
            sentences = re.split(r'(?<=[.!?])\s+', content)
            
            current_chunk = f"{title}\n" if title else ""
            
            for sentence in sentences:
                if len(current_chunk) + len(sentence) < chunk_size:
                    current_chunk += sentence + " "
                else:
                    if current_chunk.strip():
                        chunks.append(current_chunk.strip())
                    
                    # Mantener tÃ­tulo en cada chunk
                    words = current_chunk.split()
                    overlap_words = words[-overlap//5:] if len(words) > overlap//5 else []
                    current_chunk = f"{title}\n" if title else ""
                    current_chunk += " ".join(overlap_words) + " " + sentence + " "
            
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
        
        return chunks
        
    def detect_subject(self, filename):
        """Detectar materia basado en el nombre del archivo"""
        filename_lower = filename.lower()
        
        # Mapeo mÃ¡s especÃ­fico
        if 'natural' in filename_lower or 'ciencias_naturales' in filename_lower:
            return 'ciencias_naturales'
        elif 'social' in filename_lower or 'ciencias_sociales' in filename_lower:
            return 'ciencias_sociales'
        elif 'matematica' in filename_lower or 'matemÃ¡tica' in filename_lower:
            return 'matematicas'
        elif 'espanol' in filename_lower or 'espaÃ±ol' in filename_lower or 'lengua' in filename_lower:
            return 'espanol'
        elif 'ingles' in filename_lower or 'inglÃ©s' in filename_lower or 'english' in filename_lower:
            return 'ingles'

        logger.warning(f"✔️ No se detecto materia para: {filename}")
        return 'general'
    
    def search_forced(self, query, n_results=3):
        """Búsqueda con penalización a contenido genérico"""
        logger.info(f"🔍 Buscando: '{query}'")
        
        if self.collection.count() == 0:
            return "", [], 999

        # Detectar si es saludo genérico
        generic_greetings = ['hola', 'buenos dias', 'buenas tardes', 'como estas', 'hey', 'hi']
        is_greeting = any(greeting in query.lower() for greeting in generic_greetings)
        
        if is_greeting:
            logger.info("🔍 Detectado saludo genérico - Saltando búsqueda de docs")
            return "", [], 999
        
        query_clean = query.strip()
        if len(query_clean) < 4 or len(query_clean.split()) == 1:
            logger.info("Consulta muy corta, omitiendo búsqueda RAG")
            return "", [], 999

        cache_key = query_clean.lower()
        if cache_key in self.result_cache:
            logger.info("✔️ Usando resultado cacheado")
            return self.result_cache[cache_key]

        query_embedding = self.embedder.encode(query_clean).tolist()
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=max(3, n_results),
            include=['documents', 'metadatas', 'distances']
        )
        
        if not results['documents'][0]:
            return "", [], 999
        
        context_parts = []
        sources = set()
        distances = []
        
        logger.info(f"Top 5 resultados:")
        
        # Analizar y filtrar resultados
        for i, (doc, metadata, distance) in enumerate(zip(
            results['documents'][0][:4],
            results['metadatas'][0][:4],
            results['distances'][0][:4]
        )):
            # PENALIZAR CONTENIDO MUY GENERICO
            generic_words = ['importante', 'necesario', 'vital', 'permite', 'todos', 'seres']
            generic_count = sum(1 for word in generic_words if word in doc.lower())
            
            # Si tiene muchas palabras genericas, penalizar
            penalty = generic_count * 0.05
            adjusted_distance = distance + penalty
            
            logger.info(f"   {i+1}. Dist: {distance:.3f} (ajustada: {adjusted_distance:.3f}) | {metadata['source']:<20} | {doc[:60]}...")
            
            distances.append(adjusted_distance)
        
        # Usar distancias ajustadas para seleccion
        best_items = sorted(
            zip(results['documents'][0], results['metadatas'][0], distances),
            key=lambda x: x[2]
        )
        
        for doc, metadata, distance in best_items[:4]:
            # UMBRAL MAS ESTRICTO
            threshold = 0.95
            
            if distance < threshold:
                context_parts.append(doc)
                sources.add(metadata['source'])
                logger.info(f"SELECCIONADO (dist ajustada: {distance:.3f}) - {metadata['source']}")
            
            if len(context_parts) >= 2:
                break
        
        best_distance = min(distances) if distances else 999
        
        # UMBRAL ESTRICTO - No usar docs si distancia > 0.9
        if best_distance > 0.9:
            logger.warning(f"Mejor distancia muy alta ({best_distance:.3f}), usando modelo")
            return "", [], best_distance
        
        if not context_parts:
            logger.info("Sin contexto suficientemente relevante")
            return "", [], 999
        
        context = "\n\n".join(context_parts)[:600]
        sources_list = list(sources)
        
        logger.info(f"Contexto final: {len(context)} chars de {sources_list}")
        
        final_result = (context, sources_list, best_distance)
        self.result_cache[cache_key] = final_result
        return final_result

    def search(self, query, n_results=3):
        """Buscar chunks relevantes con filtrado inteligente"""
        logger.info(f"Buscando: '{query}'")
        
        if self.collection.count() == 0:
            logger.error("La coleccion esta¡ vaci­a!")
            return "", [], 999
        
        # Generar embedding de la consulta
        query_embedding = self.embedder.encode(query).tolist()
        
        # Buscar en ChromaDB con mÃ¡s resultados
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=5,  # Buscar 5 para filtrar
            include=['documents', 'metadatas', 'distances']
        )
        
        if not results['documents'][0]:
            logger.warning("No se encontraron resultados")
            return "", [], 999
        
        context_parts = []
        sources = set()
        distances = []
        
        logger.info("Resultados de busqueda RAG:")
        
        for doc, metadata, distance in zip(
            results['documents'][0], 
            results['metadatas'][0],
            results['distances'][0]
        ):
            distances.append(distance)

            if distance < best_distance:
                best_distance = distance
            
            # UMBRAL MAS PERMISIVO: 1.5 en lugar de 1.0
            threshold = 1.5  # AUMENTADO para ser mÃ¡s permisivo
            
            if distance < threshold:
                context_parts.append(doc)
                sources.add(metadata['source'])
                logger.info(f"ACEPTADO (dist: {distance:.3f}) - {metadata['source']}")
            else:
                logger.info(f"Rechazado (dist: {distance:.3f}) - {metadata['source']}")
            
            if len(context_parts) >= 3:
                break
        
        logger.info(f" Mejor distancia encontrada: {best_distance:.3f}")
        
        # Si la mejor distancia es razonable pero no paso el filtro, usar el mejor
        if not context_parts and best_distance < 2.0:
            logger.warning(f"Usando mejor resultado disponible (dist: {best_distance:.3f})")
            context_parts.append(results['documents'][0][0])
            sources.add(results['metadatas'][0][0]['source'])
        
        if not context_parts:
            logger.warning("Sin resultados suficientemente relevantes")
            return "", []
        
        context = "\n\n".join(context_parts)[:2500]
        sources_list = list(sources)
        
        logger.info(f"Contexto final: {len(context)} chars de {len(context_parts)} chunks")
        logger.info(f"Fuentes utilizadas: {sources_list}")
        context, sources, distance = self.search(query, n_results)
        return context, sources, distance
    
      
    

    
    def get_stats(self):
        """Obtener estadi­sticas del sistema RAG"""
        try:
            total_chunks = self.collection.count()
            
            # Contar por materia
            all_metadata = self.collection.get(include=['metadatas'])
            subjects = {}
            
            for metadata in all_metadata['metadatas']:
                subject = metadata.get('subject', 'unknown')
                subjects[subject] = subjects.get(subject, 0) + 1
            
            return {
                'total_chunks': total_chunks,
                'subjects': subjects,
                'status': 'active' if total_chunks > 0 else 'empty'
            }
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas: {e}")
            return {'status': 'error', 'error': str(e)}
