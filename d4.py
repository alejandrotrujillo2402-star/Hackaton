import json
from datetime import datetime
from d2 import llamar

# ---------- 1) Funciones normales de Python ----------
RUTAS = {
    "12": {"origen": "Centro", "destino": "La Enea", "frecuencia_min": 15, "estado": "normal"},
    "5": {"origen": "Chipre", "destino": "Villamaría", "frecuencia_min": 10, "estado": "retraso de 20 min"},
    "chipre-centro": {"origen": "Chipre", "destino": "Centro", "frecuencia_min": 8, "estado": "desvío por accidente"},
}


def consultar_ruta(ruta: str) -> dict:
    return RUTAS.get(ruta.lower().strip(), {"error": f"La ruta {ruta} no existe"})


def hora_actual() -> dict:
    return {"hora": datetime.now().strftime("%H:%M")}


FUNCIONES = {"consultar_ruta": consultar_ruta, "hora_actual": hora_actual}

# ---------- 2) Descripción para el modelo ----------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "consultar_ruta",
            "description": "Devuelve origen, destino, frecuencia y estado actual de una ruta de bus de Manizales.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Número o nombre de la ruta, ej: '12' o 'chipre-centro'"}
                },
                "required": ["ruta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hora_actual",
            "description": "Devuelve la hora actual (HH:MM).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

SYSTEM = {"role": "system",
          "content": "Eres un asistente de buses de Manizales. Usa las herramientas cuando necesites datos reales. Responde en español, breve."}


# ---------- 3) Flujo: pedir -> ejecutar -> responder ----------
def preguntar(pregunta: str):
    print(f"\nTú: {pregunta}")
    messages = [SYSTEM, {"role": "user", "content": pregunta}]

    r = llamar(messages=messages, tools=TOOLS)
    msg = r.choices[0].message

    if not msg.tool_calls:  # respondió sin herramientas
        print(f"IA: {msg.content}")
        return

    # Guardar el mensaje del asistente que pidió las herramientas
    # (model_dump conserva campos extra que Gemini necesita, como thought_signature)
    messages.append(msg.model_dump(exclude_none=True))

    for tc in msg.tool_calls:
        nombre = tc.function.name
        args = json.loads(tc.function.arguments or "{}")
        print(f"  🔧 {nombre}({args})")

        resultado = FUNCIONES[nombre](**args)  # TU código ejecuta
        print(f"     ↳ {resultado}")

        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": json.dumps(resultado, ensure_ascii=False),
        })

    # Segunda llamada: el modelo redacta con los resultados
    r2 = llamar(messages=messages, tools=TOOLS)
    msg2 = r2.choices[0].message

    if msg2.tool_calls:
        print("  [quería otra herramienta → esto lo resuelve el loop de agente (d5)]")
    print(f"IA: {msg2.content}")


preguntar("¿Cómo va la ruta 5?")
preguntar("¿Qué hora es y cada cuánto pasa la 12?")
preguntar("¿Qué es un bus articulado?")