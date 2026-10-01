"""Carga los documentos de un dominio al RAG y mide la precisión.
Uso: python cargar_documentos.py dominio_salud
"""
import importlib
import sys
import rag

nombre = sys.argv[1] if len(sys.argv) > 1 else "dominio_buses"
dominio = importlib.import_module(nombre)
total = rag.cargar(dominio.COLECCION, dominio.DOCUMENTOS)
print(f"{total} documentos en la colección '{dominio.COLECCION}'\n")

pruebas = getattr(dominio, "PRUEBAS_RAG", [])
buscar = rag.buscador(dominio.COLECCION)
aciertos = 0
for pregunta, esperado in pruebas:
    r = buscar(pregunta)
    obtenido = r["documentos"][0]["id"] if r["encontrado"] else None
    aciertos += obtenido == esperado
    print(f"{'OK ' if obtenido == esperado else 'MAL'} {pregunta}  ->  {obtenido}")
if pruebas:
    print(f"\nPrecisión: {aciertos}/{len(pruebas)} = {aciertos / len(pruebas):.0%}")