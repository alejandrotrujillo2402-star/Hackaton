"""DOMINIO: EPS ficticia "Salud Vital". Lo que CAMBIA en cada reto."""
import secrets
from datetime import datetime, timedelta

import escalamiento
import rag
from motor import tool
from seguridad import requiere_verificacion, herramientas_verificacion, INSTRUCCIONES_VERIFICACION

NOMBRE = "Asistente EPS Salud Vital"
COLECCION = "faq_salud"

# ---------- Datos falsos ----------
ESPECIALIDADES = ["medicina general", "odontologia", "pediatria", "ginecologia", "psicologia", "laboratorio"]
CITAS: dict[str, dict] = {}   # codigo -> {cedula, especialidad, fecha_hora, estado}
AUTORIZACIONES = {
    "AUT-1001": {"servicio": "Resonancia magnética de rodilla", "estado": "aprobada", "vigencia": "30 días"},
    "AUT-1002": {"servicio": "Consulta con ortopedia", "estado": "en revisión", "tiempo_estimado": "3 días hábiles"},
    "AUT-1003": {"servicio": "Medicamento no incluido en el plan", "estado": "rechazada",
                 "motivo": "Falta historia clínica actualizada"},
}


# >> Quita tildes y mayúsculas: 'Pediatría' y 'pediatria' valen lo mismo.
def _norm(t: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFD", t).encode("ascii", "ignore").decode().lower().strip()


# >> Agenda posible: próximos 3 días hábiles con 3 franjas cada uno.
def _horarios() -> list[str]:
    """Próximos 3 días hábiles, 3 franjas por día."""
    dias, d = [], datetime.now()
    while len(dias) < 3:
        d += timedelta(days=1)
        if d.weekday() < 5:
            dias.append(d)
    return [f"{x:%Y-%m-%d} {h}" for x in dias for h in ("08:00", "10:30", "15:00")]


# ---------- Herramientas ----------
# >> Horarios libres = agenda posible menos citas activas de esa especialidad.
def consultar_disponibilidad(especialidad: str) -> dict:
    esp = _norm(especialidad)
    if esp not in ESPECIALIDADES:
        return {"error": f"Especialidad no disponible. Opciones: {', '.join(ESPECIALIDADES)}"}
    ocupados = {c["fecha_hora"] for c in CITAS.values() if c["especialidad"] == esp and c["estado"] == "activa"}
    return {"especialidad": esp, "horarios": [h for h in _horarios() if h not in ocupados]}


# >> Requiere verificación. Revisa de nuevo la disponibilidad y agenda; entrega código CITA.
@requiere_verificacion
def agendar_cita(especialidad: str, fecha_hora: str, ctx: dict) -> dict:
    disp = consultar_disponibilidad(especialidad)
    if "error" in disp:
        return disp
    if fecha_hora not in disp["horarios"]:
        return {"error": "Ese horario no está disponible", "horarios_disponibles": disp["horarios"]}
    codigo = f"CITA-{secrets.randbelow(10**6):06d}"
    CITAS[codigo] = {"cedula": ctx["cedula"], "especialidad": disp["especialidad"],
                     "fecha_hora": fecha_hora, "estado": "activa"}
    return {"agendada": True, "codigo": codigo, "especialidad": disp["especialidad"], "fecha_hora": fecha_hora,
            "indicacion": "Llegar 15 minutos antes con documento de identidad."}


# >> Requiere verificación. Citas activas del afiliado de la sesión.
@requiere_verificacion
def mis_citas(ctx: dict) -> dict:
    return {"citas": [{"codigo": k, **{c: v for c, v in x.items() if c != "cedula"}}
                      for k, x in CITAS.items() if x["cedula"] == ctx["cedula"] and x["estado"] == "activa"]}


# >> Requiere verificación. Solo cancela citas propias; no revela si existen para otro.
@requiere_verificacion
def cancelar_cita(codigo: str, ctx: dict) -> dict:
    cita = CITAS.get(codigo.strip().upper())
    if not cita or cita["cedula"] != ctx["cedula"]:   # no se revela si existe para otro afiliado
        return {"error": "No encontramos esa cita a tu nombre"}
    cita["estado"] = "cancelada"
    return {"cancelada": True, "codigo": codigo.upper()}


# >> Requiere verificación. Estado de una autorización médica (AUT-xxxx).
@requiere_verificacion
def estado_autorizacion(numero: str, ctx: dict) -> dict:
    aut = AUTORIZACIONES.get(numero.strip().upper())
    return {"numero": numero.upper(), **aut} if aut else {"error": "Número de autorización no encontrado"}


_f_verif, _t_verif = herramientas_verificacion()
S = {"type": "string"}

FUNCIONES = {
    **_f_verif,
    "escalar_a_humano": escalamiento.escalar_a_humano,
    "buscar_documentos": rag.buscador(COLECCION),
    "consultar_disponibilidad": consultar_disponibilidad,
    "agendar_cita": agendar_cita,
    "mis_citas": mis_citas,
    "cancelar_cita": cancelar_cita,
    "estado_autorizacion": estado_autorizacion,
}

TOOLS = [
    *_t_verif,
    escalamiento.TOOL,
    tool("buscar_documentos", "Busca en los documentos oficiales de la EPS: copagos, cuotas moderadoras, "
         "urgencias, autorizaciones, medicamentos, portabilidad, PQR, red de atención.", {"consulta": S}, ["consulta"]),
    tool("consultar_disponibilidad", f"Horarios disponibles para una especialidad. Opciones: {', '.join(ESPECIALIDADES)}.",
         {"especialidad": S}, ["especialidad"]),
    tool("agendar_cita", "Agenda una cita. fecha_hora debe ser EXACTAMENTE uno de los horarios disponibles "
         "(formato 'AAAA-MM-DD HH:MM'). Requiere verificación.",
         {"especialidad": S, "fecha_hora": S}, ["especialidad", "fecha_hora"]),
    tool("mis_citas", "Citas activas del afiliado actual. Requiere verificación."),
    tool("cancelar_cita", "Cancela una cita por su código (CITA-xxxxxx). Requiere verificación.",
         {"codigo": S}, ["codigo"]),
    tool("estado_autorizacion", "Estado de una autorización médica por su número (AUT-xxxx). Requiere verificación.",
         {"numero": S}, ["numero"]),
]

SYSTEM = {"role": "system", "content": (
    "Eres el asistente virtual de la EPS Salud Vital. Responde en español, breve, cálido y profesional.\n"
    "- SEGURIDAD MÉDICA: nunca diagnostiques, recetes ni recomiendes medicamentos o dosis. Si el afiliado describe "
    "una emergencia (dolor en el pecho, dificultad para respirar, sangrado abundante, pérdida de conciencia, "
    "intención de hacerse daño), indícale de inmediato que llame al 123 o vaya a urgencias, antes que cualquier trámite.\n"
    "- Para citas usa SIEMPRE consultar_disponibilidad antes de ofrecer horarios (nunca uses horarios de mensajes anteriores) y ofrece máximo 3; luego agendar_cita con el horario exacto.\n"
    "- Para copagos, cuotas moderadoras, medicamentos, urgencias, autorizaciones y PQR usa SIEMPRE buscar_documentos "
    "y responde SOLO con lo que digan. Si encontrado=false, dilo y ofrece un asesor. NUNCA inventes.\n"
    "- Al agendar o cancelar, entrega siempre el código de la cita."
    + INSTRUCCIONES_VERIFICACION + escalamiento.INSTRUCCIONES
)}

# ---------- Documentos del RAG (ficticios) ----------
DOCUMENTOS = [
    ("cuotas", "Cuotas moderadoras y copagos",
     "La cuota moderadora se paga en consultas y exámenes y depende del ingreso del cotizante: categoría A 4.700, "
     "B 18.700 y C 49.300 pesos. Los beneficiarios pagan copago en hospitalizaciones y cirugías. "
     "Las urgencias vitales y los controles prenatales no pagan cuota moderadora. Preguntas frecuentes: cuánto pago por una consulta, cuánto cuesta una cita, valor del copago, cuánto debo pagar."),
    ("urgencias", "Urgencias",
     "En una emergencia vital llama al 123 o acude a cualquier servicio de urgencias del país, aunque no sea de la "
     "red de Salud Vital; no se requiere autorización previa. Para síntomas leves usa la línea de orientación médica 24/7. Preguntas frecuentes: me duele el pecho, no puedo respirar, me siento muy mal, qué hago en una emergencia, a dónde voy si es grave."),
    ("autorizaciones", "Autorizaciones de servicios",
     "Exámenes especializados, cirugías y algunos medicamentos requieren autorización. Se solicita con la orden "
     "médica por la app o la web. La respuesta tarda máximo 5 días hábiles y la autorización tiene vigencia de 30 días. Preguntas frecuentes: necesito permiso para un examen, resonancia, ecografía, cirugía, cómo pido una autorización, cuánto tarda."),
    ("medicamentos", "Entrega de medicamentos",
     "Los medicamentos formulados se reclaman en las farmacias de la red con la fórmula vigente y el documento. "
     "Si falta un medicamento, la farmacia debe entregarlo a domicilio en máximo 48 horas. Preguntas frecuentes: no tenían mi medicina, la farmacia no me entregó, dónde reclamo mis medicamentos, me falta un medicamento."),
    ("portabilidad", "Portabilidad",
     "Si vas a estar fuera de tu ciudad más de un mes, solicita la portabilidad en la web para ser atendido en "
     "otra ciudad. Se aprueba en máximo 10 días hábiles. Preguntas frecuentes: me voy a vivir a otra ciudad, viajo por varios meses, me mudo temporalmente, atención en otra ciudad."),
    ("pqr", "Peticiones, quejas y reclamos",
     "Las PQR se radican en la web, la app, la línea telefónica o las oficinas. La EPS responde en máximo 15 días "
     "hábiles. Si no recibes respuesta puedes acudir a la Superintendencia Nacional de Salud. Preguntas frecuentes: quiero poner una queja, mala atención, reclamo, inconformidad, denuncia."),
    ("red", "Red de atención y horarios",
     "Las sedes de atención básica funcionan de lunes a viernes de 7:00 a.m. a 6:00 p.m. y sábados de 8:00 a.m. a "
     "12:00 m. Las citas se pueden agendar por la app, la web o con el asistente virtual las 24 horas. Preguntas frecuentes: a qué hora abren, horario de atención, sedes, dónde me atienden."),
]

PRUEBAS_RAG = [
    ("¿Cuánto pago por una consulta?", "cuotas"),
    ("Me duele mucho el pecho, ¿qué hago?", "urgencias"),
    ("Necesito permiso para una resonancia", "autorizaciones"),
    ("En la farmacia no tenían mi medicina", "medicamentos"),
    ("Me voy a vivir dos meses a Medellín", "portabilidad"),
    ("Quiero quejarme de la atención", "pqr"),
]