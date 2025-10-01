# app/rag_system.py
import chromadb
from chromadb.config import Settings
import os
import glob
from sentence_transformers import SentenceTransformer
import logging

logger = logging.getLogger(__name__)

class RAGSystem:
    def __init__(self, docs_dir="../docs"):
        self.docs_dir = docs_dir
        
        # Verificar que la carpeta existe
        abs_path = os.path.abspath(docs_dir)
        logger.info(f"📁 Buscando documentos en: {abs_path}")
        
        if not os.path.exists(abs_path):
            logger.error(f"❌ La carpeta {abs_path} no existe!")
            raise FileNotFoundError(f"No se encuentra la carpeta: {abs_path}")
        
        # Listar archivos encontrados
        txt_files = glob.glob(os.path.join(abs_path, "*.txt"))
        logger.info(f"📄 Archivos TXT encontrados: {[os.path.basename(f) for f in txt_files]}")
        
        if not txt_files:
            logger.warning("⚠️ No se encontraron archivos TXT en docs/")
        
        # Modelo de embeddings
        logger.info("Cargando modelo de embeddings...")
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
        
        # ChromaDB - usar ruta absoluta para la BD
        db_path = os.path.abspath("./chroma_db")
        self.client = chromadb.PersistentClient(
            path=db_path,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Forzar reindexación (para debug)
        try:
            self.client.delete_collection("docs_educativos")
            logger.info("🗑️ Colección anterior eliminada")
        except:
            pass
        
        # Crear nueva colección e indexar
        logger.info("📚 Creando nueva colección e indexando...")
        self.collection = self.client.create_collection("docs_educativos")
        self.index_documents()
    
    def index_documents(self):
        """Indexar documentos TXT"""
        doc_count = 0
        chunk_count = 0
        
        # Usar ruta absoluta
        abs_docs_dir = os.path.abspath(self.docs_dir)
        pattern = os.path.join(abs_docs_dir, "*.txt")
        
        logger.info(f"🔍 Buscando archivos con patrón: {pattern}")
        
        for filepath in glob.glob(pattern):
            doc_count += 1
            filename = os.path.basename(filepath)
            logger.info(f"📖 Indexando: {filename}")
            
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                # Log del contenido
                logger.info(f"   - Tamaño: {len(content)} caracteres")
                logger.info(f"   - Primeros 100 chars: {content[:100]}...")
                
                # Dividir en chunks más pequeños para mejor búsqueda
                chunk_size = 400  # Reducido para mejor precisión
                overlap = 100
                chunks = []
                
                for i in range(0, len(content), chunk_size - overlap):
                    chunk = content[i:i + chunk_size]
                    if len(chunk.strip()) > 50:
                        chunks.append(chunk)
                
                logger.info(f"   - Dividido en {len(chunks)} chunks")
                
                # Indexar cada chunk
                for i, chunk in enumerate(chunks):
                    chunk_count += 1
                    
                    # Generar embedding
                    embedding = self.embedder.encode(chunk).tolist()
                    
                    # Determinar materia del archivo
                    materia = self.detect_subject(filename)
                    
                    # Añadir a ChromaDB
                    self.collection.add(
                        embeddings=[embedding],
                        documents=[chunk],
                        metadatas=[{
                            "source": filename,
                            "chunk_id": i,
                            "subject": materia,
                            "chunk_size": len(chunk)
                        }],
                        ids=[f"{filename}_{i}"]
                    )
                    
            except Exception as e:
                logger.error(f"❌ Error indexando {filename}: {e}")
        
        logger.info(f"✅ Indexación completa: {doc_count} documentos, {chunk_count} chunks")
        
        # Verificar que se indexó correctamente
        total = self.collection.count()
        logger.info(f"📊 Total en base de datos: {total} chunks")
    
    def detect_subject(self, filename):
        """Detectar materia basado en el nombre del archivo"""
        filename_lower = filename.lower()
        if 'natural' in filename_lower or 'ciencia' in filename_lower:
            return 'ciencias_naturales'
        elif 'social' in filename_lower:
            return 'ciencias_sociales'
        elif 'mate' in filename_lower:
            return 'matematicas'
        elif 'espa' in filename_lower:
            return 'espanol'
        elif 'ingl' in filename_lower:
            return 'ingles'
        return 'general'
    
    def search(self, query, n_results=3):
        """Buscar chunks relevantes"""
        logger.info(f"🔎 Buscando: '{query}'")
        
        # Verificar que hay contenido
        if self.collection.count() == 0:
            logger.error("❌ La colección está vacía!")
            return "No hay documentos indexados", []
        
        # Generar embedding de la consulta
        query_embedding = self.embedder.encode(query).tolist()
        
        # Buscar en ChromaDB
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results
        )
        
        logger.info(f"📊 Resultados encontrados: {len(results['documents'][0])}")
        
        if not results['documents'][0]:
            logger.warning("⚠️ No se encontraron resultados relevantes")
            return "No se encontró información relevante para tu pregunta", []
        
        # Combinar resultados
        context_parts = []
        sources = set()
        
        for doc, metadata in zip(results['documents'][0], results['metadatas'][0]):
            #ver respuesta
            logger.info(f"   - Chunk de {metadata['source']}: {doc[:100]}...")
            context_parts.append(doc)
            sources.add(metadata['source'])
        
        context = "\n\n---\n\n".join(context_parts)
        
        logger.info(f"✅ Contexto generado: {len(context)} caracteres de {sources}")
        
        return context, list(sources)