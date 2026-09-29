import json
import re
import types

import pytest
from fastapi.testclient import TestClient

import memoria
import seguridad
import motor
import dominio_buses as dominio
import api


# ---------- utilidades: un LLM falso ----------
def tool_call(nombre, args, id_="t1"):
    return types.SimpleNamespace(id=id_, function=types.SimpleNamespace(name=nombre, arguments=json.dumps(args)))


class MensajeFalso:
    def __init__(self, content=None, tool_calls=None):
        self.content, self.tool_calls = content, tool_calls

    def model_dump(self, **_):
        return {"role": "assistant", "content": self.content,
                "tool_calls": [{"id": t.id, "type": "function",
                                "function": {"name": t.function.name, "arguments": t.function.arguments}}
                               for t in self.tool_calls or []]}


def respuesta(msg):
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])


@pytest.fixture
def cliente():
    ced = "1112223"
    memoria.registrar_cliente(ced, "Test", "3001234567")
    return {"cedula": ced}


def codigo_sms(cedula):
    return re.search(r"\d{6}", seguridad.ULTIMOS_SMS[cedula]).group()


# ---------- SEGURIDAD ----------
def test_accion_sensible_bloqueada_sin_verificar(cliente):
    r = motor._ejecutar(tool_call("saldo_tarjeta", {}), dominio.FUNCIONES, cliente)
    assert r["error"] == "VERIFICACION_REQUERIDA"


def test_modelo_no_puede_suplantar_cedula(cliente):
    r = motor._ejecutar(tool_call("saldo_tarjeta", {"ctx": {"cedula": "9999999"}}), dominio.FUNCIONES, cliente)
    assert r["error"] == "VERIFICACION_REQUERIDA"


def test_flujo_otp_completo(cliente):
    motor._ejecutar(tool_call("solicitar_codigo", {}), dominio.FUNCIONES, cliente)
    codigo = codigo_sms(cliente["cedula"])
    malo = "000000" if codigo != "000000" else "111111"
    assert not seguridad.validar_otp(cliente["cedula"], malo)["ok"]
    assert seguridad.validar_otp(cliente["cedula"], codigo)["ok"]
    r = motor._ejecutar(tool_call("bloquear_tarjeta", {"motivo": "robo"}), dominio.FUNCIONES, cliente)
    assert r["bloqueada"] and r["radicado"].startswith("BLQ-")


def test_codigo_es_de_un_solo_uso(cliente):
    seguridad.enviar_sms_simulado(cliente["cedula"], None, seguridad.generar_otp(cliente["cedula"]))
    codigo = codigo_sms(cliente["cedula"])
    assert seguridad.validar_otp(cliente["cedula"], codigo)["ok"]
    assert not seguridad.validar_otp(cliente["cedula"], codigo)["ok"]


def test_maximo_tres_intentos(cliente):
    seguridad.generar_otp(cliente["cedula"])
    for _ in range(3):
        seguridad.validar_otp(cliente["cedula"], "abcdef")
    assert "Demasiados" in seguridad.validar_otp(cliente["cedula"], "abcdef")["motivo"]


def test_codigo_vencido(cliente, monkeypatch):
    seguridad.enviar_sms_simulado(cliente["cedula"], None, seguridad.generar_otp(cliente["cedula"]))
    codigo = codigo_sms(cliente["cedula"])
    ahora = seguridad.time.time()
    monkeypatch.setattr(seguridad.time, "time", lambda: ahora + 10 * 60)
    assert "venció" in seguridad.validar_otp(cliente["cedula"], codigo)["motivo"]


# ---------- MOTOR ----------
def test_herramienta_desconocida_no_rompe(cliente):
    assert "error" in motor._ejecutar(tool_call("borrar_todo", {}), dominio.FUNCIONES, cliente)


def test_loop_encadena_herramientas(monkeypatch):
    guion = iter([
        respuesta(MensajeFalso(tool_calls=[tool_call("buscar_rutas", {"origen": "Chipre", "destino": "Villamaría"})])),
        respuesta(MensajeFalso(content="Toma la ruta 5")),
    ])
    monkeypatch.setattr(motor, "llamar", lambda **_: next(guion))
    msgs = [{"role": "user", "content": "¿Qué bus tomo?"}]
    texto, pasos = motor.correr_agente(msgs, dominio.TOOLS, dominio.FUNCIONES)
    assert texto == "Toma la ruta 5"
    assert "buscar_rutas" in pasos[0] and "'5'" in pasos[0]
    assert msgs[-1]["role"] == "assistant"


def test_limite_de_pasos(monkeypatch):
    monkeypatch.setattr(motor, "llamar",
                        lambda **_: respuesta(MensajeFalso(tool_calls=[tool_call("proximo_bus", {"ruta": "5"})])))
    texto, pasos = motor.correr_agente([{"role": "user", "content": "x"}], dominio.TOOLS, dominio.FUNCIONES, max_pasos=3)
    assert "límite" in texto and len(pasos) == 3


# ---------- API ----------
@pytest.fixture
def api_client(monkeypatch):
    def agente_eco(messages, tools, funciones, contexto=None, max_pasos=6):
        previos = [m["content"] for m in messages if m["role"] == "user"][:-1]
        texto = f"antes: {previos}"
        messages.append({"role": "assistant", "content": texto})
        return texto, []
    monkeypatch.setattr(api, "correr_agente", agente_eco)
    return TestClient(api.app)


def test_api_valida_entrada(api_client):
    assert api_client.post("/chat", json={"cedula": "12", "mensaje": "hola"}).status_code == 422
    assert api_client.post("/chat", json={"cedula": "5555555", "mensaje": "hola"}).status_code == 404


def test_api_continuidad_entre_canales(api_client):
    api_client.post("/clientes", json={"cedula": "7778889", "nombre": "Ana"})
    api_client.post("/chat", json={"cedula": "7778889", "mensaje": "mi perro", "canal": "web"})
    r = api_client.post("/chat", json={"cedula": "7778889", "mensaje": "¿de qué hablábamos?", "canal": "whatsapp"})
    assert "mi perro" in r.json()["respuesta"]
    fila = next(c for c in api_client.get("/clientes").json() if c["cedula"] == "7778889")
    assert fila["ultimo_canal"] == "whatsapp"


# ---------- MEMORIA ----------
def test_historial_reconstruye_chat():
    memoria.registrar_cliente("4445556", "Luis")
    memoria.guardar_mensajes("4445556", [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": None,
         "tool_calls": [{"id": "a", "type": "function", "function": {"name": "proximo_bus", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "a", "content": "{}"},
        {"role": "assistant", "content": "listo"},
    ])
    chat = memoria.a_chat(memoria.cargar_historial("4445556"))
    assert [c[0] for c in chat] == ["user", "assistant"]
    assert "proximo_bus" in chat[1][2][0]