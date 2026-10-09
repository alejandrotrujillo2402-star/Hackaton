"""SEGURIDAD: verificación en 2 pasos (OTP). Genérica: no cambia entre retos.
La regla la impone el CÓDIGO, no el modelo."""
import functools
import hashlib
import secrets
import time
from memoria import _con

VIGENCIA_OTP = 5 * 60        # el código vence en 5 min
VIGENCIA_SESION = 30 * 60    # verificado por 30 min
MAX_INTENTOS = 3
ULTIMOS_SMS: dict[str, str] = {}   # SMS simulados, para mostrarlos en el panel

with _con() as c:
    c.execute("""CREATE TABLE IF NOT EXISTS verificaciones (
        cedula TEXT PRIMARY KEY, codigo_hash TEXT, expira REAL,
        intentos INTEGER DEFAULT 0, verificado_hasta REAL DEFAULT 0)""")


def _hash(codigo: str) -> str:
    return hashlib.sha256(codigo.encode()).hexdigest()   # nunca guardamos el código en claro


def generar_otp(cedula: str) -> str:
    codigo = f"{secrets.randbelow(10**6):06d}"
    with _con() as c:
        c.execute("""INSERT INTO verificaciones (cedula, codigo_hash, expira, intentos, verificado_hasta)
                     VALUES (?, ?, ?, 0, 0)
                     ON CONFLICT(cedula) DO UPDATE SET codigo_hash=excluded.codigo_hash,
                     expira=excluded.expira, intentos=0""",
                  (cedula, _hash(codigo), time.time() + VIGENCIA_OTP))
    return codigo


def enviar_sms_simulado(cedula: str, telefono: str | None, codigo: str):
    texto = f"Tu código de verificación es {codigo}. Vence en 5 minutos."
    ULTIMOS_SMS[cedula] = texto
    print(f"📱 [SMS SIMULADO a {telefono or 'sin teléfono'}] {texto}")


def validar_otp(cedula: str, codigo: str) -> dict:
    with _con() as c:
        f = c.execute("SELECT * FROM verificaciones WHERE cedula = ?", (cedula,)).fetchone()
        if not f or not f["codigo_hash"]:
            return {"ok": False, "motivo": "No hay un código activo. Solicita uno nuevo."}
        if f["intentos"] >= MAX_INTENTOS:
            return {"ok": False, "motivo": "Demasiados intentos. Solicita un código nuevo."}
        if time.time() > f["expira"]:
            return {"ok": False, "motivo": "El código venció. Solicita uno nuevo."}
        if _hash(str(codigo).strip()) != f["codigo_hash"]:
            c.execute("UPDATE verificaciones SET intentos = intentos + 1 WHERE cedula = ?", (cedula,))
            return {"ok": False, "motivo": "Código incorrecto.",
                    "intentos_restantes": MAX_INTENTOS - f["intentos"] - 1}
        c.execute("UPDATE verificaciones SET codigo_hash = NULL, verificado_hasta = ? WHERE cedula = ?",
                  (time.time() + VIGENCIA_SESION, cedula))
    return {"ok": True, "mensaje": "Identidad verificada por 30 minutos."}


def esta_verificado(cedula: str) -> bool:
    with _con() as c:
        f = c.execute("SELECT verificado_hasta FROM verificaciones WHERE cedula = ?", (cedula,)).fetchone()
    return bool(f) and time.time() < f["verificado_hasta"]


def requiere_verificacion(func):
    """Decorador: la herramienta se niega si el cliente no está verificado."""
    @functools.wraps(func)
    def envoltura(*args, ctx: dict, **kwargs):
        if not esta_verificado(ctx["cedula"]):
            return {"error": "VERIFICACION_REQUERIDA",
                    "mensaje": "El cliente debe verificar su identidad con un código antes de esta acción."}
        return func(*args, ctx=ctx, **kwargs)
    return envoltura


# ---------- Herramientas genéricas de verificación (cualquier dominio las reutiliza) ----------
def solicitar_codigo(ctx: dict) -> dict:
    import memoria
    cliente = memoria.obtener_cliente(ctx["cedula"]) or {}
    tel = cliente.get("telefono")
    enviar_sms_simulado(ctx["cedula"], tel, generar_otp(ctx["cedula"]))
    return {"enviado": True, "destino": f"celular terminado en {tel[-4:]}" if tel else "tu celular registrado"}


def verificar_codigo(codigo: str, ctx: dict) -> dict:
    return validar_otp(ctx["cedula"], codigo)


def herramientas_verificacion():
    from motor import tool
    funciones = {"solicitar_codigo": solicitar_codigo, "verificar_codigo": verificar_codigo}
    tools = [
        tool("solicitar_codigo", "Envía un código de verificación de 6 dígitos por SMS al celular del cliente."),
        tool("verificar_codigo", "Verifica el código de 6 dígitos que el cliente recibió por SMS.",
             {"codigo": {"type": "string"}}, ["codigo"]),
    ]
    return funciones, tools


INSTRUCCIONES_VERIFICACION = (
    "\n- Si una herramienta responde VERIFICACION_REQUERIDA, usa solicitar_codigo, pide al cliente el código "
    "de 6 dígitos que le llegó por SMS y luego usa verificar_codigo. Después reintenta la acción. "
    "Nunca inventes ni repitas códigos."
)

def cerrar_sesion(cedula: str):
    """Al terminar la llamada normalmente, la verificación deja de valer."""
    with _con() as c:
        c.execute("UPDATE verificaciones SET verificado_hasta = 0 WHERE cedula = ?", (cedula,))
