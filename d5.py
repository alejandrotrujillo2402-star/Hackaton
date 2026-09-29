import json
import unicodedata
from datetime import datetime
from llm import llamar

MAX_PASOS = 6

# ---------- Datos falsos ----------
RUTAS = {
    "5": {"paradas": ["chipre", "centro", "cable", "villamaria"], "frecuencia_min": 10, "retraso_min": 20},
    "12": {"paradas": ["centro", "cable", "la enea"], "frecuencia_min": 15, "retraso_min": 0},
    "chipre-centro": {"paradas": ["chipre", "centro"], "frecuencia_min": 8, "retraso_min": 0},
    "villa-express": {"paradas": ["centro", "villamaria"], "frecuencia_min": 20, "retraso_min": 0},
}


def normalizar(texto: str) -> str:
    """'Villamaría ' -> 'villamaria'"""
    sin_tildes = unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode()
    return sin_tildes.lower().strip()


# ---------- Herramientas ----------
def buscar_rutas(origen: str, destino: str) -> dict:
    o, d = normalizar(origen), normalizar(destino)
    directas = [r for r, info in RUTAS.items() if o in info["paradas"] and d in info["paradas"]]
    return {"rutas_directas": directas} if directas else {"rutas_directas": [], "nota": "No hay ruta directa"}


def consultar_ruta(ruta: str) -> dict:
    info = RUTAS.get(normalizar(ruta))
    if info is None:
        raise ValueError(f"La ruta '{ruta}' no existe")  # se captura en el loop
    return {"ruta": ruta, **info}


def proximo_bus(ruta: str) -> dict:
    info = RUTAS.get(normalizar(ruta))
    if info is None:
        raise ValueError(f"La ruta '{ruta}' no existe")
    minuto = datetime.now().minute
    freq = info["frecuencia_min"]
    espera = (freq - minuto % freq) + info["retraso_min"]
    return {"ruta": ruta, "minutos_para_llegar": espera}


def hora_actual() -> dict:
    return {"hora": datetime.now().strftime("%H:%M")}


FUNCIONES = {
    "buscar_rutas": buscar_rutas,
    "consultar_ruta": consultar_ruta,
    "proximo_bus": proximo_bus,
    "hora_actual": hora_actual,
}


def tool(nombre, descripcion, props=None, requeridos=None):
    """Atajo para no escribir el JSON Schema completo cada vez."""
    return {
        "type": "function",
        "function": {
            "name": nombre,
            "description": descripcion,
            "parameters": {"type": "object", "properties": props or {}, "required": requeridos or []},
        },
    }


S = {"type": "string"}
TOOLS = [
    tool("buscar_rutas", "Busca rutas de bus directas entre dos barrios/paradas de Manizales.",
         {"origen": S, "destino": S}, ["origen", "destino"]),
    tool("consultar_ruta", "Paradas, frecuencia y retraso de una ruta.", {"ruta": S}, ["ruta"]),
    tool("proximo_bus", "Minutos que faltan para que pase el próximo bus de una ruta (incluye retraso).",
         {"ruta": S}, ["ruta"]),
    tool("hora_actual", "Hora actual HH:MM."),
]

SYSTEM = {"role": "system",
          "content": ("Eres un agente de buses de Manizales. Usa las herramientas las veces que necesites "
                      "antes de responder. Verifica que una ruta exista antes de consultar sus tiempos. "
                      "Si una herramienta devuelve error, explícalo al usuario. "
                      "Responde en español, breve.")}


# ---------- Loop de agente ----------
def ejecutar(tc) -> dict:
    nombre = tc.function.name
    try:
        args = json.loads(tc.function.arguments or "{}")
        if nombre not in FUNCIONES:
            raise ValueError(f"Herramienta desconocida: {nombre}")
        return FUNCIONES[nombre](**args)
    except Exception as e:  # el error vuelve al modelo, el programa no se rompe
        return {"error": str(e)}


def correr_agente(messages: list) -> tuple[str, list[str]]:
    """Loop de agente sobre un historial existente.
    Modifica `messages` (agrega herramientas y respuesta final).
    Devuelve (texto_final, lista_de_pasos)."""
    pasos = []
    for paso in range(1, MAX_PASOS + 1):
        r = llamar(messages=messages, tools=TOOLS)
        msg = r.choices[0].message

        if not msg.tool_calls:  # condición de parada
            messages.append({"role": "assistant", "content": msg.content})
            return msg.content, pasos

        messages.append(msg.model_dump(exclude_none=True))
        for tc in msg.tool_calls:
            resultado = ejecutar(tc)
            pasos.append(f"paso {paso} 🔧 {tc.function.name}({tc.function.arguments}) ↳ {resultado}")
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(resultado, ensure_ascii=False),
            })

    texto = "No pude resolverlo dentro del límite de pasos."
    messages.append({"role": "assistant", "content": texto})
    return texto, pasos


def correr_agente(messages: list) -> tuple[str, list[str]]:
    pasos = []
    for paso in range(1, MAX_PASOS + 1):
        r = llamar(messages=messages, tools=TOOLS)
        msg = r.choices[0].message
        if not msg.tool_calls:
            messages.append({"role": "assistant", "content": msg.content})
            return msg.content, pasos
        messages.append(msg.model_dump(exclude_none=True))
        for tc in msg.tool_calls:
            resultado = ejecutar(tc)
            pasos.append(f"paso {paso} 🔧 {tc.function.name}({tc.function.arguments}) ↳ {resultado}")
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": json.dumps(resultado, ensure_ascii=False)})
    texto = "No pude resolverlo dentro del límite de pasos."
    messages.append({"role": "assistant", "content": texto})
    return texto, pasos


def agente(pregunta: str) -> str:
    print(f"\n{'=' * 60}\nTú: {pregunta}")
    messages = [SYSTEM, {"role": "user", "content": pregunta}]
    texto, pasos = correr_agente(messages)
    for p in pasos:
        print("  " + p)
    return texto


if __name__ == "__main__":
    for p in [
        "Estoy en Chipre y necesito ir a Villamaría. ¿Qué bus tomo y en cuánto pasa?",
        "¿Cuál pasa primero por el Cable, la 5 o la 12?",
        "¿Cómo va la ruta 99?",
    ]:
        print("IA:", agente(p))
