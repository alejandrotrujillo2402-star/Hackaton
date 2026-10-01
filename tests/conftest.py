"""Configuración de tests: BD temporal, sin API key real, sin modelo de embeddings."""
import os, sys, tempfile, types

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ["AGENTE_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["GEMINI_API_KEY"] = "clave-falsa-para-tests"

# RAG falso: evita cargar el modelo de embeddings
rag_falso = types.ModuleType("rag")
rag_falso.buscar_documentos = lambda consulta, k=2: {"encontrado": False, "mensaje": "test"}
rag_falso.buscador = lambda nombre: rag_falso.buscar_documentos
sys.modules["rag"] = rag_falso