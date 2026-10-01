"""ESCALAMIENTO a humano con emoción, urgencia y resumen. Genérico: no cambia entre retos."""
import json
import secrets
from typing import Literal
from pydantic import BaseModel, Field
from memoria import _con, _ahora
from motor import tool

EMOCIONES = ["calmado", "confundido", "frustrado", "enojado"]


class Escalamiento(BaseModel):
    motivo: str = Field(min_length=3)
    emocion: Literal["calmado", "confundido", "frustrado", "enojado"]
    urgencia: int = Field(ge=1, le=5)
    resumen: str = Field(min_length=10)
    pendiente: str = Field(min_length=3)


with _con() as c:
    c.execute("""CREATE TABLE IF NOT EXISTS escalamientos (
        ticket TEXT PRIMARY KEY, cedula TEXT, datos TEXT,
        estado TEXT DEFAULT 'pendiente', creado TEXT)""")


def escalar_a_humano(motivo: str, emocion: str, urgencia: int, resumen: str, pendiente: str, ctx: dict) -> dict:
    e = Escalamiento(motivo=motivo, emocion=emocion, urgencia=urgencia, resumen=resumen, pendiente=pendiente)
    ticket = f"ESC-{secrets.randbelow(10**6):06d}"
    with _con() as c:
        c.execute("INSERT INTO escalamientos (ticket, cedula, datos, creado) VALUES (?, ?, ?, ?)",
                  (ticket, ctx["cedula"], e.model_dump_json(), _ahora()))
    return {"escalado": True, "ticket": ticket,
            "mensaje": "Un asesor humano continuará la atención con el resumen del caso."}


def listar_escalamientos(estado: str = "pendiente") -> list[dict]:
    with _con() as c:
        filas = c.execute("""SELECT e.ticket, e.cedula, c.nombre, e.datos, e.creado FROM escalamientos e
                             LEFT JOIN clientes c ON c.cedula = e.cedula
                             WHERE e.estado = ? ORDER BY e.creado DESC""", (estado,)).fetchall()
    return [{"ticket": f["ticket"], "cedula": f["cedula"], "nombre": f["nombre"], "creado": f["creado"],
             **json.loads(f["datos"])} for f in filas]


TOOL = tool(
    "escalar_a_humano",
    "Transfiere el caso a un asesor humano con un resumen completo para que no tenga que volver a preguntar.",
    {
        "motivo": {"type": "string", "description": "Por qué se escala"},
        "emocion": {"type": "string", "enum": EMOCIONES, "description": "Emoción percibida del cliente"},
        "urgencia": {"type": "integer", "minimum": 1, "maximum": 5, "description": "1 = baja, 5 = crítica"},
        "resumen": {"type": "string", "description": "Qué pasó en la conversación, en 1-3 frases"},
        "pendiente": {"type": "string", "description": "Qué debe resolver el asesor"},
    },
    ["motivo", "emocion", "urgencia", "resumen", "pendiente"],
)

INSTRUCCIONES = (
    "\n- Usa escalar_a_humano si: el cliente pide hablar con una persona, está frustrado o enojado, "
    "o no pudiste resolver su caso tras 2 intentos. Llena bien el resumen y lo pendiente para que el "
    "asesor no tenga que preguntar de nuevo. Muestra empatía y entrega el número de ticket. "
    "Después de escalar, NO vuelvas a mencionar el escalamiento ni al asesor, salvo que el cliente "
    "pregunte por su caso. Responde solo lo que el cliente pide en cada mensaje."
)