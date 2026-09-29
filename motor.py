"""MOTOR del agente: genérico, NO cambia entre retos."""
import inspect
import json
from llm import llamar


def tool(nombre, descripcion, props=None, requeridos=None):
    """Atajo para describir una herramienta en JSON Schema."""
    return {
        "type": "function",
        "function": {
            "name": nombre,
            "description": descripcion,
            "parameters": {"type": "object", "properties": props or {}, "required": requeridos or []},
        },
    }


def _ejecutar(tc, funciones: dict, contexto: dict) -> dict:
    try:
        args = json.loads(tc.function.arguments or "{}")
        f = funciones.get(tc.function.name)
        if f is None:
            raise ValueError(f"Herramienta desconocida: {tc.function.name}")
        args.pop("ctx", None)                           # el modelo NUNCA controla el contexto
        if "ctx" in inspect.signature(f).parameters:    # se inyecta desde la sesión
            args["ctx"] = contexto
        return f(**args)
    except Exception as e:
        return {"error": str(e)}


def correr_agente(messages: list, tools: list, funciones: dict, contexto: dict | None = None, max_pasos: int = 6):
    """Loop de agente. Modifica `messages`. Devuelve (texto, pasos).
    `contexto` (ej: {"cedula": ...}) viene de la sesión y solo lo ven las herramientas."""
    contexto = contexto or {}
    pasos = []
    for paso in range(1, max_pasos + 1):
        msg = llamar(messages=messages, tools=tools).choices[0].message

        if not msg.tool_calls:
            messages.append({"role": "assistant", "content": msg.content})
            return msg.content, pasos

        messages.append(msg.model_dump(exclude_none=True))
        for tc in msg.tool_calls:
            resultado = _ejecutar(tc, funciones, contexto)
            pasos.append(f"paso {paso} 🔧 {tc.function.name}({tc.function.arguments}) ↳ {resultado}")
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": json.dumps(resultado, ensure_ascii=False)})

    texto = "No pude resolverlo dentro del límite de pasos."
    messages.append({"role": "assistant", "content": texto})
    return texto, pasos