"""Buscador de documentos (RAG). Los documentos se cargan con d7.py."""
import chromadb
from chromadb.utils import embedding_functions

UMBRAL = 0.75  # distancia máxima aceptable; más lejos = "no sé"

_embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="paraphrase-multilingual-MiniLM-L12-v2"
)
_coleccion = chromadb.PersistentClient(path="./chroma_db").get_or_create_collection(
    name="faq_buses_multi", embedding_function=_embedder, metadata={"hnsw:space": "cosine"}
)
assert _coleccion.count() > 0, "Archivador vacío: corre primero python d7.py"


def buscar_documentos(consulta: str, k: int = 2) -> dict:
    r = _coleccion.query(query_texts=[consulta], n_results=k)
    resultados = [
        {"titulo": m["titulo"], "texto": d, "distancia": round(dist, 3)}
        for d, m, dist in zip(r["documents"][0], r["metadatas"][0], r["distances"][0])
        if dist <= UMBRAL  # guardrail: descartar lo que no se parece
    ]
    if not resultados:
        return {"encontrado": False,
                "mensaje": "No hay información oficial sobre esto en los documentos."}
    return {"encontrado": True, "documentos": resultados}