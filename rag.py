"""Buscador de documentos (RAG) genérico: una colección por dominio."""
import chromadb
from chromadb.utils import embedding_functions

UMBRAL = 0.75  # distancia máxima aceptable; más lejos = "no sé"
_cliente = None
_embedder = None


def _coleccion(nombre: str):
    global _cliente, _embedder
    if _cliente is None:   # carga perezosa: el modelo solo se carga si se usa
        _embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="paraphrase-multilingual-MiniLM-L12-v2")
        _cliente = chromadb.PersistentClient(path="./chroma_db")
    return _cliente.get_or_create_collection(
        name=nombre, embedding_function=_embedder, metadata={"hnsw:space": "cosine"})


def cargar(nombre: str, documentos: list[tuple[str, str, str]]) -> int:
    """documentos: [(id, titulo, texto), ...]"""
    col = _coleccion(nombre)
    col.upsert(ids=[d[0] for d in documentos],
               documents=[f"{d[1]}: {d[2]}" for d in documentos],
               metadatas=[{"titulo": d[1]} for d in documentos])
    return col.count()


def buscador(nombre: str):
    """Devuelve la herramienta buscar_documentos atada a una colección."""
    def buscar_documentos(consulta: str, k: int = 2) -> dict:
        col = _coleccion(nombre)
        if col.count() == 0:
            return {"encontrado": False, "mensaje": f"Archivador vacío: corre cargar_documentos.py"}
        r = col.query(query_texts=[consulta], n_results=k)
        resultados = [
            {"id": i, "titulo": m["titulo"], "texto": d, "distancia": round(dist, 3)}
            for i, d, m, dist in zip(r["ids"][0], r["documents"][0], r["metadatas"][0], r["distances"][0])
            if dist <= UMBRAL
        ]
        if not resultados:
            return {"encontrado": False, "mensaje": "No hay información oficial sobre esto en los documentos."}
        return {"encontrado": True, "documentos": resultados}
    return buscar_documentos