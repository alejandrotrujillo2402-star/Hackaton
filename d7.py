"""RAG parte 1: guardar documentos y buscar por significado (versión multilingüe).
No usa el LLM -> no gasta cuota de Gemini.
Instalar (solo CPU, más liviano):
  pip install torch --index-url https://download.pytorch.org/whl/cpu
  pip install sentence-transformers chromadb
"""
import chromadb
from chromadb.utils import embedding_functions

# ---------- 1) Documentos ----------
DOCUMENTOS = [
    ("tarifas", "Tarifas", "El pasaje urbano cuesta 3.200 pesos. Estudiantes con carné vigente pagan 2.500. "
     "Adultos mayores de 62 años pagan 2.000 presentando la cédula."),
    ("tarjeta", "Tarjeta de transporte", "La tarjeta se compra en la Terminal y en puntos autorizados por 5.000 pesos. "
     "Se recarga en tiendas, cajeros y por la app. Si se pierde, se bloquea llamando a la línea 01 8000."),
    ("objetos", "Objetos olvidados", "Los objetos olvidados en los buses se guardan 30 días en la oficina de la Terminal, "
     "segundo piso. Para reclamarlos hay que describir el objeto, la ruta y la hora aproximada."),
    ("mascotas", "Mascotas", "Se permiten mascotas pequeñas dentro de guacal o bolso cerrado. "
     "Los perros guía pueden viajar sin restricción. Mascotas grandes sin guacal no pueden abordar."),
    ("pqr", "Peticiones, quejas y reclamos", "Las PQR se radican en la web, en la app o en la Terminal. "
     "La empresa responde máximo en 15 días hábiles. Cada PQR recibe un número de radicado."),
    ("horarios", "Horarios de servicio", "El servicio urbano opera de 5:00 a.m. a 10:00 p.m. de lunes a sábado, "
     "y de 6:00 a.m. a 9:00 p.m. domingos y festivos."),
    ("accesibilidad", "Accesibilidad", "Los buses articulados tienen rampa para sillas de ruedas y "
     "sillas preferenciales para embarazadas, adultos mayores y personas con discapacidad."),
]

# ---------- 2) Modelo multilingüe + distancia coseno ----------
embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="paraphrase-multilingual-MiniLM-L12-v2"  # entiende español
)
cliente = chromadb.PersistentClient(path="./chroma_db")
coleccion = cliente.get_or_create_collection(
    name="faq_buses_multi",              # colección nueva (la vieja usaba otro modelo)
    embedding_function=embedder,
    metadata={"hnsw:space": "cosine"},   # coseno: estándar para significado
)

coleccion.upsert(
    ids=[d[0] for d in DOCUMENTOS],
    documents=[f"{d[1]}: {d[2]}" for d in DOCUMENTOS],  # título dentro del texto
    metadatas=[{"titulo": d[1]} for d in DOCUMENTOS],
)
print(f"📚 {coleccion.count()} documentos en el archivador\n")


# ---------- 3) Búsqueda ----------
def buscar(pregunta: str, k: int = 2) -> list[dict]:
    r = coleccion.query(query_texts=[pregunta], n_results=k)
    return [
        {"id": i, "titulo": m["titulo"], "texto": d, "distancia": round(dist, 3)}
        for i, d, m, dist in zip(r["ids"][0], r["documents"][0], r["metadatas"][0], r["distances"][0])
    ]


# ---------- 4) Evaluación automática ----------
if __name__ == "__main__":
    PRUEBAS = [  # (pregunta, id esperado)
        ("Dejé mi maleta en el bus, ¿qué hago?", "objetos"),
        ("¿Puedo subir con mi perro?", "mascotas"),
        ("¿Cuánto me cuesta si soy universitario?", "tarifas"),
        ("Quiero poner una queja", "pqr"),
        ("¿A qué hora pasa el último bus un domingo?", "horarios"),
    ]
    aciertos = 0
    for pregunta, esperado in PRUEBAS:
        res = buscar(pregunta)
        ok = res[0]["id"] == esperado
        aciertos += ok
        print(f"{'✅' if ok else '❌'} {pregunta}")
        for r in res:
            print(f"     [{r['distancia']}] {r['titulo']}")
    print(f"\n🎯 Precisión: {aciertos}/{len(PRUEBAS)} = {aciertos / len(PRUEBAS):.0%}")