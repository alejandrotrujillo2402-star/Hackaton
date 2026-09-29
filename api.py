"""API REST del agente. Todos los canales (web, voz, WhatsApp) usan /chat.
Ejecutar: uvicorn api:app --reload --host 127.0.0.1
Docs interactivas: http://127.0.0.1:8000/docs
"""
from typing import Literal
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import memoria
import escalamiento
from motor import correr_agente
import dominio_buses as dominio   # <- el día del reto: import dominio_X as dominio

app = FastAPI(title=dominio.NOMBRE, description="Agente de atención con memoria por cliente y continuidad entre canales.")


# ---------- Esquemas (validación automática de entrada/salida) ----------
class ClienteIn(BaseModel):
    cedula: str = Field(pattern=r"^\d{5,12}$", examples=["1234567"])
    nombre: str = Field(min_length=1, examples=["Alejandro"])
    telefono: str | None = Field(default=None, examples=["3001234567"])


class ChatIn(BaseModel):
    cedula: str = Field(pattern=r"^\d{5,12}$", examples=["1234567"])
    mensaje: str = Field(min_length=1, max_length=2000, examples=["¿Puedo llevar a mi perro?"])
    canal: Literal["web", "voz", "whatsapp"] = "web"


class ChatOut(BaseModel):
    respuesta: str
    herramientas: list[str]
    canal: str


# ---------- Endpoints ----------
@app.get("/health")
def health():
    return {"estado": "ok", "dominio": dominio.NOMBRE}


@app.post("/clientes", status_code=201)
def crear_cliente(c: ClienteIn):
    return memoria.registrar_cliente(c.cedula, c.nombre, c.telefono)


@app.get("/clientes")
def listar_clientes():
    return memoria.listar_clientes()


@app.get("/escalamientos")
def escalamientos_pendientes():
    return escalamiento.listar_escalamientos()


@app.get("/clientes/{cedula}/historial")
def historial(cedula: str):
    if not memoria.obtener_cliente(cedula):
        raise HTTPException(404, "Cliente no registrado")
    return [{"rol": r, "texto": t, "herramientas": p} for r, t, p in memoria.a_chat(memoria.cargar_historial(cedula))]


@app.post("/chat", response_model=ChatOut)
def chat(entrada: ChatIn):
    cliente = memoria.obtener_cliente(entrada.cedula)
    if not cliente:
        raise HTTPException(404, "Cliente no registrado. Usa POST /clientes primero.")

    # 1) Reconstruir la conversación desde la BD (sin importar el canal anterior)
    system = {"role": "system", "content": dominio.SYSTEM["content"] +
              f"\nCliente actual: {cliente['nombre']} (cédula {cliente['cedula']}). "
              f"Canal actual: {entrada.canal}. Llámalo por su nombre."}
    messages = [system] + memoria.cargar_historial(entrada.cedula)
    n = len(messages)
    messages.append({"role": "user", "content": entrada.mensaje})

    # 2) Correr el agente
    try:
        texto, pasos = correr_agente(messages, dominio.TOOLS, dominio.FUNCIONES, contexto={"cedula": entrada.cedula})
    except Exception as e:
        raise HTTPException(503, f"El agente no pudo responder: {e}")

    # 3) Guardar SOLO lo nuevo de este turno, marcado con su canal
    memoria.guardar_mensajes(entrada.cedula, messages[n:], canal=entrada.canal)
    return ChatOut(respuesta=texto, herramientas=pasos, canal=entrada.canal)