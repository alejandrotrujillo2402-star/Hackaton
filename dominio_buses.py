"""DOMINIO: lo que CAMBIA en cada reto (instrucciones + herramientas + datos)."""
import secrets
import unicodedata
from datetime import datetime
from motor import tool
import rag
import memoria
import escalamiento
from seguridad import (generar_otp, enviar_sms_simulado, validar_otp,
                       requiere_verificacion)

NOMBRE = "Agente de Buses Manizales"
COLECCION = "faq_buses_multi"

# ---------- Datos falsos ----------
RUTAS = {
    "5": {"paradas": ["chipre", "centro", "cable", "villamaria"], "frecuencia_min": 10, "retraso_min": 20},
    "12": {"paradas": ["centro", "cable", "la enea"], "frecuencia_min": 15, "retraso_min": 0},
    "chipre-centro": {"paradas": ["chipre", "centro"], "frecuencia_min": 8, "retraso_min": 0},
    "villa-express": {"paradas": ["centro", "villamaria"], "frecuencia_min": 20, "retraso_min": 0},
}


def _norm(t: str) -> str:
    return unicodedata.normalize("NFD", t).encode("ascii", "ignore").decode().lower().strip()


def _ruta(ruta: str) -> dict:
    info = RUTAS.get(_norm(ruta))
    if info is None:
        raise ValueError(f"La ruta '{ruta}' no existe")
    return info


# ---------- Herramientas ----------
def buscar_rutas(origen: str, destino: str) -> dict:
    o, d = _norm(origen), _norm(destino)
    return {"rutas_directas": [r for r, i in RUTAS.items() if o in i["paradas"] and d in i["paradas"]]}


def consultar_ruta(ruta: str) -> dict:
    return {"ruta": ruta, **_ruta(ruta)}


def proximo_bus(ruta: str) -> dict:
    info = _ruta(ruta)
    f = info["frecuencia_min"]
    return {"ruta": ruta, "minutos_para_llegar": (f - datetime.now().minute % f) + info["retraso_min"]}


# ---------- Herramientas sensibles (requieren verificación) ----------
TARJETAS: dict[str, dict] = {}   # datos falsos por cédula


def _tarjeta(cedula: str) -> dict:
    return TARJETAS.setdefault(cedula, {"numero": f"****{cedula[-4:]}", "saldo": 18400, "bloqueada": False})


def solicitar_codigo(ctx: dict) -> dict:
    cliente = memoria.obtener_cliente(ctx["cedula"]) or {}
    tel = cliente.get("telefono")
    enviar_sms_simulado(ctx["cedula"], tel, generar_otp(ctx["cedula"]))
    destino = f"celular terminado en {tel[-4:]}" if tel else "tu celular registrado"
    return {"enviado": True, "destino": destino}


def verificar_codigo(codigo: str, ctx: dict) -> dict:
    return validar_otp(ctx["cedula"], codigo)


@requiere_verificacion
def saldo_tarjeta(ctx: dict) -> dict:
    t = _tarjeta(ctx["cedula"])
    return {"tarjeta": t["numero"], "saldo": t["saldo"], "bloqueada": t["bloqueada"]}


@requiere_verificacion
def bloquear_tarjeta(motivo: str, ctx: dict) -> dict:
    t = _tarjeta(ctx["cedula"])
    t["bloqueada"] = True
    return {"bloqueada": True, "tarjeta": t["numero"], "motivo": motivo,
            "radicado": f"BLQ-{secrets.randbelow(10**6):06d}"}


FUNCIONES = {
    "escalar_a_humano": escalamiento.escalar_a_humano,
    "solicitar_codigo": solicitar_codigo,
    "verificar_codigo": verificar_codigo,
    "saldo_tarjeta": saldo_tarjeta,
    "bloquear_tarjeta": bloquear_tarjeta,
    "buscar_rutas": buscar_rutas,
    "consultar_ruta": consultar_ruta,
    "proximo_bus": proximo_bus,
    "buscar_documentos": rag.buscador(COLECCION),
}

S = {"type": "string"}
TOOLS = [
    escalamiento.TOOL,
    tool("solicitar_codigo", "Envía un código de verificación de 6 dígitos por SMS al celular del cliente."),
    tool("verificar_codigo", "Verifica el código de 6 dígitos que el cliente recibió por SMS.",
         {"codigo": S}, ["codigo"]),
    tool("saldo_tarjeta", "Saldo y estado de la tarjeta de transporte del cliente actual. Requiere verificación."),
    tool("bloquear_tarjeta", "Bloquea la tarjeta del cliente actual (pérdida o robo) y genera un radicado. "
         "Requiere verificación.", {"motivo": S}, ["motivo"]),
    tool("buscar_rutas", "Rutas de bus directas entre dos barrios o paradas de Manizales.",
         {"origen": S, "destino": S}, ["origen", "destino"]),
    tool("consultar_ruta", "Paradas, frecuencia y retraso de una ruta.", {"ruta": S}, ["ruta"]),
    tool("proximo_bus", "Minutos para que pase el próximo bus de una ruta (incluye retraso).",
         {"ruta": S}, ["ruta"]),
    tool("buscar_documentos",
         "Busca en los documentos oficiales de la empresa: tarifas, tarjeta, objetos olvidados, "
         "mascotas, PQR, horarios de servicio, accesibilidad. Úsala para cualquier pregunta sobre "
         "políticas o reglas.",
         {"consulta": S}, ["consulta"]),
]

SYSTEM = {"role": "system", "content": (
    "Eres el asistente de la empresa de buses de Manizales. Responde en español, breve y amable.\n"
    "- Para rutas y tiempos usa las herramientas de rutas. Verifica que una ruta exista antes de consultar tiempos.\n"
    "- Para políticas, precios o reglas usa SIEMPRE buscar_documentos y responde SOLO con lo que digan los documentos.\n"
    "- Si buscar_documentos devuelve encontrado=false, di que no tienes esa información y ofrece "
    "comunicar al usuario con un asesor humano. NUNCA inventes.\n"
    "- Saldo y bloqueo de tarjeta: si la herramienta responde VERIFICACION_REQUERIDA, usa solicitar_codigo, "
    "pide al cliente el código de 6 dígitos que le llegó por SMS y luego usa verificar_codigo. "
    "Después reintenta la acción. Nunca inventes ni repitas códigos.\n"
    "- Al bloquear una tarjeta, confirma el motivo con el cliente y entrégale el número de radicado."
    + escalamiento.INSTRUCCIONES
)}


# ---------- Documentos del RAG (se cargan con: python cargar_documentos.py dominio_buses) ----------
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

PRUEBAS_RAG = [
    ("Dejé mi maleta en el bus, ¿qué hago?", "objetos"),
    ("¿Puedo subir con mi perro?", "mascotas"),
    ("¿Cuánto me cuesta si soy universitario?", "tarifas"),
    ("Quiero poner una queja", "pqr"),
    ("¿A qué hora pasa el último bus un domingo?", "horarios"),
]