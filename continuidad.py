"""CONTINUIDAD entre canales: si una llamada se corta, se continúa por WhatsApp.
Genérico: no cambia entre retos."""
import json
import re
import time
from pydantic import BaseModel
import memoria
from memoria import _con, _ahora
from llm import llamar

TIMEOUT_LATIDO = 10   # segundos sin señal = llamada cortada

with _con() as c:
    c.execute("""CREATE TABLE IF NOT EXISTS llamadas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cedula TEXT, inicio TEXT,
        ultimo_latido REAL, estado TEXT DEFAULT 'activa', fin TEXT)""")


# ---------- Ciclo de vida de la llamada ----------
def iniciar(cedula: str) -> int:
    with _con() as c:
        cur = c.execute("INSERT INTO llamadas (cedula, inicio, ultimo_latido) VALUES (?, ?, ?)",
                        (cedula, _ahora(), time.time()))
        return cur.lastrowid


def latido(llamada_id: int):
    with _con() as c:
        c.execute("UPDATE llamadas SET ultimo_latido = ? WHERE id = ? AND estado = 'activa'",
                  (time.time(), llamada_id))


def finalizar(llamada_id: int, motivo: str) -> bool:
    """motivo: 'colgo' (cierre normal) o 'cortada'. Devuelve True si cambió de estado."""
    estado = "completada" if motivo == "colgo" else "cortada"
    with _con() as c:
        cur = c.execute("UPDATE llamadas SET estado = ?, fin = ? WHERE id = ? AND estado = 'activa'",
                        (estado, _ahora(), llamada_id))
        return cur.rowcount == 1


def revisar_cortes() -> list[int]:
    """Llamadas activas sin latido reciente -> se marcan como cortadas."""
    limite = time.time() - TIMEOUT_LATIDO
    with _con() as c:
        ids = [f["id"] for f in c.execute(
            "SELECT id FROM llamadas WHERE estado = 'activa' AND ultimo_latido < ?", (limite,))]
    return [i for i in ids if finalizar(i, "cortada")]


# ---------- Aviso por WhatsApp ----------
class Aviso(BaseModel):
    resumen: str
    pendiente: str
    mensaje: str


def _transcripcion(cedula: str, desde: str) -> str:
    with _con() as c:
        filas = c.execute("""SELECT datos FROM mensajes WHERE cedula = ? AND canal = 'voz' AND creado >= ?
                             ORDER BY id""", (cedula, desde)).fetchall()
    lineas = []
    for f in filas:
        m = json.loads(f["datos"])
        if m["role"] in ("user", "assistant") and m.get("content"):
            lineas.append(f"{'Cliente' if m['role'] == 'user' else 'Agente'}: {m['content']}")
    return "\n".join(lineas)


def generar_aviso(nombre: str, transcripcion: str) -> Aviso:
    prompt = (
        f"Una llamada de atención al cliente con {nombre} se cortó. Con la transcripción, responde SOLO un JSON "
        'con las claves "resumen" (1 frase de lo que se habló), "pendiente" (qué faltaba por resolver, o '
        '"nada") y "mensaje" (WhatsApp breve, cálido y profesional, SIN emojis: saluda por el nombre, dice que '
        "la llamada se cortó, recuerda en qué iban y ofrece continuar por este chat).\n\n" + transcripcion
    )
    try:
        r = llamar(messages=[{"role": "user", "content": prompt}], temperature=0)
        crudo = re.sub(r"```(json)?", "", r.choices[0].message.content or "").strip()
        return Aviso.model_validate_json(crudo)
    except Exception:   # si el modelo falla, igual avisamos con una plantilla
        return Aviso(resumen="Llamada interrumpida", pendiente="Por confirmar",
                     mensaje=f"Hola {nombre}, se cortó nuestra llamada. Si quieres, seguimos por aquí "
                             "justo donde quedamos.")


def manejar_corte(llamada_id: int) -> Aviso | None:
    with _con() as c:
        ll = c.execute("SELECT * FROM llamadas WHERE id = ?", (llamada_id,)).fetchone()
    cliente = memoria.obtener_cliente(ll["cedula"]) or {"nombre": "cliente", "telefono": None}
    transcripcion = _transcripcion(ll["cedula"], ll["inicio"])
    print(f"[continuidad] llamada {llamada_id} cortada; transcripción: {len(transcripcion)} caracteres")
    if not transcripcion:   # no alcanzó a decir nada: no molestamos al cliente
        print("[continuidad] sin conversación: no se envía aviso")
        return None
    aviso = generar_aviso(cliente["nombre"], transcripcion)
    memoria.guardar_mensajes(ll["cedula"], [{"role": "assistant", "content": aviso.mensaje}], canal="whatsapp")
    print(f"[WHATSAPP SIMULADO a {cliente.get('telefono') or 'sin teléfono'}] {aviso.mensaje}")
    return aviso


def mensajes_whatsapp(cedula: str) -> list[dict]:
    with _con() as c:
        filas = c.execute("SELECT datos, creado FROM mensajes WHERE cedula = ? AND canal = 'whatsapp' ORDER BY id",
                          (cedula,)).fetchall()
    salida = []
    for f in filas:
        m = json.loads(f["datos"])
        if m["role"] in ("user", "assistant") and m.get("content"):
            salida.append({"rol": m["role"], "texto": m["content"], "hora": f["creado"][11:16]})
    return salida