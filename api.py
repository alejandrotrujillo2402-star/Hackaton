"""API REST del agente. Todos los canales (web, voz, WhatsApp) usan /chat.
Ejecutar: uvicorn api:app --reload --host 127.0.0.1
Docs: http://127.0.0.1:8000/docs   Voz: /voz   WhatsApp simulado: /whatsapp
"""
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

import memoria
import escalamiento
import continuidad
import metricas
import seguridad
from motor import correr_agente
import importlib
import os
dominio = importlib.import_module(os.getenv("DOMINIO", "dominio_salud"))   # se elige en el .env

CARPETA = Path(__file__).parent


# ---------- Vigilante de llamadas cortadas (hilo en segundo plano) ----------
# >> Hilo en segundo plano: cada 2 s busca llamadas cortadas y dispara el WhatsApp.
def _vigilar():
    print("[vigilante] activo: revisando llamadas cada 2 s")
    while True:
        try:
            for llamada_id in continuidad.revisar_cortes():
                continuidad.manejar_corte(llamada_id)
        except Exception as e:
            print(f"[vigilante] {e}")
        time.sleep(2)


# >> Arranca el vigilante cuando inicia la API.
@asynccontextmanager
async def lifespan(_app):
    threading.Thread(target=_vigilar, daemon=True).start()
    yield


app = FastAPI(title=dominio.NOMBRE, lifespan=lifespan,
              description="Agente de atención con memoria por cliente y continuidad entre canales.")


# ---------- Esquemas ----------
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


class EncuestaIn(BaseModel):
    cedula: str = Field(pattern=r"^\d{5,12}$")
    canal: Literal["web", "voz", "whatsapp"]
    puntaje: int = Field(ge=1, le=5)


class LlamadaIn(BaseModel):
    cedula: str = Field(pattern=r"^\d{5,12}$")


INSTRUCCIONES_CANAL = {
    "voz": "\nEstás en una LLAMADA de voz: responde en máximo 2 frases cortas, sin markdown, sin listas "
           "ni símbolos, como hablaría una persona. Di fechas y horas de forma natural (ej: el viernes 2 de octubre a las 3 de la tarde), nunca en formato 2026-10-02 15:00.",
    "whatsapp": "\nEstás en WhatsApp: mensajes breves y cercanos, sin emojis ni markdown (nada de asteriscos). Si la conversación viene de una "
                "llamada cortada, continúa justo donde quedó sin pedir que repita.",
    "web": "",
}


# ---------- Páginas ----------
# >> La raíz redirige a la llamada de voz.
@app.get("/", include_in_schema=False)
def inicio():
    return RedirectResponse("/app")


# >> Sirve la página de llamada de voz.
@app.get("/chat-web", response_class=HTMLResponse, include_in_schema=False)
def pagina_chat():
    return (CARPETA / "chat.html").read_text(encoding="utf-8")


@app.get("/app", response_class=HTMLResponse, include_in_schema=False)
def pagina_app():
    return (CARPETA / "app.html").read_text(encoding="utf-8")


@app.get("/voz", response_class=HTMLResponse, include_in_schema=False)
def pagina_voz():
    return (CARPETA / "voz.html").read_text(encoding="utf-8")


# >> Sirve el panel de operación.
@app.get("/panel", response_class=HTMLResponse, include_in_schema=False)
def pagina_panel():
    return (CARPETA / "panel.html").read_text(encoding="utf-8")


# >> Sirve el WhatsApp simulado.
@app.get("/whatsapp", response_class=HTMLResponse, include_in_schema=False)
def pagina_whatsapp():
    return (CARPETA / "whatsapp.html").read_text(encoding="utf-8")


# ---------- Endpoints ----------
# >> Indica si la API está viva y qué dominio cargó.
@app.get("/health")
def health():
    return {"estado": "ok", "dominio": dominio.NOMBRE}


# >> Registra un cliente (cédula validada).
@app.post("/clientes", status_code=201)
def crear_cliente(c: ClienteIn):
    return memoria.registrar_cliente(c.cedula, c.nombre, c.telefono)


# >> Lista clientes para el panel.
@app.get("/clientes")
def listar_clientes():
    return memoria.listar_clientes()


# >> Entrega los indicadores al panel.
@app.get("/metricas")
def ver_metricas():
    return metricas.calcular()


# >> Recibe la calificación CSAT.
@app.post("/encuestas", status_code=201)
def crear_encuesta(e: EncuestaIn):
    metricas.registrar_encuesta(e.cedula, e.canal, e.puntaje)
    return {"ok": True}


# >> Lista los casos escalados a humanos.
@app.get("/escalamientos")
def escalamientos_pendientes():
    return escalamiento.listar_escalamientos()


# >> Conversación completa de un cliente.
@app.get("/clientes/{cedula}/historial")
def historial(cedula: str):
    if not memoria.obtener_cliente(cedula):
        raise HTTPException(404, "Cliente no registrado")
    return [{"rol": r, "texto": t, "herramientas": p} for r, t, p in memoria.a_chat(memoria.cargar_historial(cedula))]


# >> Puerta única de todos los canales: carga historial, corre el agente y guarda el turno con su canal.
@app.post("/chat", response_model=ChatOut)
def chat(entrada: ChatIn):
    cliente = memoria.obtener_cliente(entrada.cedula)
    if not cliente:
        raise HTTPException(404, "Cliente no registrado. Usa POST /clientes primero.")

    system = {"role": "system", "content": dominio.SYSTEM["content"] +
              f"\nCliente actual: {cliente['nombre']} (cédula {cliente['cedula']}). "
              f"Canal actual: {entrada.canal}. Llámalo por su nombre. "
              "No repitas tickets, radicados ni información ya entregada, salvo que el cliente lo pregunte."
              + INSTRUCCIONES_CANAL[entrada.canal]}
    messages = [system] + memoria.cargar_historial(entrada.cedula)
    n = len(messages)
    messages.append({"role": "user", "content": entrada.mensaje})

    try:
        texto, pasos = correr_agente(messages, dominio.TOOLS, dominio.FUNCIONES, contexto={"cedula": entrada.cedula})
    except Exception as e:
        raise HTTPException(503, f"El agente no pudo responder: {e}")

    memoria.guardar_mensajes(entrada.cedula, messages[n:], canal=entrada.canal)
    return ChatOut(respuesta=texto, herramientas=pasos, canal=entrada.canal)


# ---------- Llamadas y continuidad ----------
# >> Registra una llamada nueva.
@app.post("/llamadas", status_code=201)
def iniciar_llamada(entrada: LlamadaIn):
    if not memoria.obtener_cliente(entrada.cedula):
        raise HTTPException(404, "Cliente no registrado")
    return {"id": continuidad.iniciar(entrada.cedula)}


@app.post("/llamadas/{llamada_id}/latido")
def latido(llamada_id: int):
    continuidad.latido(llamada_id)
    return {"ok": True}


# >> Cierra la llamada; si se cortó, envía WhatsApp; si colgó, cierra la verificación.
@app.post("/llamadas/{llamada_id}/finalizar")
def finalizar_llamada(llamada_id: int, motivo: Literal["colgo", "cortada"] = "colgo"):
    cambio = continuidad.finalizar(llamada_id, motivo)
    if cambio and motivo == "colgo" and (ced := continuidad.cedula_de(llamada_id)):
        seguridad.cerrar_sesion(ced)   # colgó: la próxima llamada vuelve a pedir código
    aviso = continuidad.manejar_corte(llamada_id) if (cambio and motivo == "cortada") else None
    return {"estado": "completada" if motivo == "colgo" else "cortada",
            "aviso_whatsapp": aviso.model_dump() if aviso else None}


# >> Mensajes del chat de WhatsApp simulado.
@app.get("/whatsapp/{cedula}/mensajes")
def mensajes_whatsapp(cedula: str):
    return continuidad.mensajes_whatsapp(cedula)