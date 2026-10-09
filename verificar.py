"""Verificación completa antes del hackathon.
Uso: python verificar.py
"""
import importlib
import os
import subprocess
import time
from pathlib import Path

resultados = []


def check(nombre, funcion):
    try:
        detalle = funcion()
        resultados.append((True, nombre, detalle or ""))
        print(f"[ OK ] {nombre}  {detalle or ''}")
    except Exception as e:
        resultados.append((False, nombre, str(e)))
        print(f"[FALLA] {nombre}  ->  {e}")


# 1) Paquetes
def paquetes():
    faltan = []
    for p in ["openai", "dotenv", "fastapi", "uvicorn", "pydantic", "chromadb", "sentence_transformers", "pytest"]:
        try:
            importlib.import_module(p)
        except ImportError:
            faltan.append(p)
    if faltan:
        raise RuntimeError(f"faltan: {', '.join(faltan)}  (pip install ...)")
    return "todos instalados"


# 2) .env
def env():
    from dotenv import load_dotenv
    load_dotenv()
    key = os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("no hay LLM_API_KEY ni GEMINI_API_KEY en .env")
    return (f"key=...{key[-4:]}  modelo={os.getenv('LLM_MODEL', '(gemini por defecto)')}  "
            f"dominio={os.getenv('DOMINIO', 'dominio_salud')}  bd={os.getenv('AGENTE_DB', 'agente.db')}")


# 3) LLM responde
def llm_responde():
    from llm import llamar
    t = time.time()
    r = llamar(messages=[{"role": "user", "content": "Responde solo: OK"}])
    return f"respondió '{(r.choices[0].message.content or '').strip()[:20]}' en {time.time() - t:.1f} s"


# 4) LLM usa herramientas
def llm_herramientas():
    from llm import llamar
    from motor import tool
    r = llamar(messages=[{"role": "user", "content": "¿Qué hora es? Usa la herramienta."}],
               tools=[tool("hora_actual", "Devuelve la hora actual.")])
    if not r.choices[0].message.tool_calls:
        raise RuntimeError("el modelo NO pidió la herramienta: prueba otro LLM_MODEL")
    return "tool calling funciona"


# 5) Dominio
def dominio():
    from dotenv import load_dotenv
    load_dotenv()
    d = importlib.import_module(os.getenv("DOMINIO", "dominio_salud"))
    return f"{d.NOMBRE}: {len(d.TOOLS)} herramientas"


# 6) RAG cargado y preciso
def rag_ok():
    from dotenv import load_dotenv
    load_dotenv()
    import rag
    d = importlib.import_module(os.getenv("DOMINIO", "dominio_salud"))
    buscar = rag.buscador(d.COLECCION)
    pruebas = getattr(d, "PRUEBAS_RAG", [])
    aciertos = 0
    for pregunta, esperado in pruebas:
        r = buscar(pregunta)
        if not r.get("encontrado") and "vacío" in r.get("mensaje", ""):
            raise RuntimeError(f"archivador vacío: python cargar_documentos.py {d.__name__}")
        aciertos += r.get("encontrado") and r["documentos"][0]["id"] == esperado
    if pruebas and aciertos < len(pruebas):
        raise RuntimeError(f"precisión {aciertos}/{len(pruebas)}: revisa DOCUMENTOS")
    return f"precisión {aciertos}/{len(pruebas)}"


# 7) Archivos
def archivos():
    necesarios = ["llm.py", "motor.py", "memoria.py", "seguridad.py", "escalamiento.py", "continuidad.py",
                  "metricas.py", "rag.py", "api.py", "voz.html", "whatsapp.html", "panel.html", ".env"]
    faltan = [f for f in necesarios if not Path(f).exists()]
    if faltan:
        raise RuntimeError(f"faltan: {', '.join(faltan)}")
    return f"{len(necesarios)} archivos presentes"


# 8) Tests
def tests():
    r = subprocess.run(["pytest", "-q"], capture_output=True, text=True)
    ultima = (r.stdout.strip().splitlines() or ["sin salida"])[-1]
    if r.returncode != 0:
        raise RuntimeError(ultima)
    return ultima


# 9) Git
def git():
    r = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    cambios = [l for l in r.stdout.splitlines() if l.strip()]
    if any(".env" in l and ".env.example" not in l for l in cambios):
        raise RuntimeError("¡.env aparece en git! Revisa el .gitignore")
    return "todo subido" if not cambios else f"{len(cambios)} cambios sin subir (haz commit y push)"


print("\n=== VERIFICACIÓN DEL AGENTE ===\n")
for nombre, f in [("Paquetes", paquetes), (".env", env), ("Archivos", archivos), ("Dominio", dominio),
                  ("LLM responde", llm_responde), ("LLM usa herramientas", llm_herramientas),
                  ("RAG", rag_ok), ("Tests", tests), ("Git", git)]:
    check(nombre, f)

fallas = [r for r in resultados if not r[0]]
print("\n" + ("TODO LISTO" if not fallas else f"{len(fallas)} FALLA(S): corrige lo marcado y vuelve a correr"))