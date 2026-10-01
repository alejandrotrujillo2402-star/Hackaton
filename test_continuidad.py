import types
import pytest
from fastapi.testclient import TestClient

import memoria
import continuidad
import api


@pytest.fixture
def con_conversacion():
    ced = "3334445"
    memoria.registrar_cliente(ced, "Laura", "3009998877")
    return ced


def _hablar_en_llamada(ced):
    memoria.guardar_mensajes(ced, [{"role": "user", "content": "Perdí mi tarjeta"},
                                   {"role": "assistant", "content": "Te envié un código"}], canal="voz")


def test_corte_por_falta_de_latido(con_conversacion, monkeypatch):
    lid = continuidad.iniciar(con_conversacion)
    ahora = continuidad.time.time()
    monkeypatch.setattr(continuidad.time, "time", lambda: ahora + 60)
    assert lid in continuidad.revisar_cortes()


def test_corte_envia_whatsapp_con_resumen(con_conversacion, monkeypatch):
    lid = continuidad.iniciar(con_conversacion)
    _hablar_en_llamada(con_conversacion)
    json_falso = ('{"resumen":"Bloqueo de tarjeta","pendiente":"Falta el código",'
                  '"mensaje":"Hola Laura, se cortó la llamada. Solo falta el código para bloquear tu tarjeta."}')
    monkeypatch.setattr(continuidad, "llamar", lambda **_: types.SimpleNamespace(
        choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=json_falso))]))
    continuidad.finalizar(lid, "cortada")
    aviso = continuidad.manejar_corte(lid)
    assert aviso.pendiente == "Falta el código"
    assert "Laura" in continuidad.mensajes_whatsapp(con_conversacion)[-1]["texto"]


def test_si_el_modelo_falla_usa_plantilla(con_conversacion, monkeypatch):
    lid = continuidad.iniciar(con_conversacion)
    _hablar_en_llamada(con_conversacion)
    def falla(**_): raise RuntimeError("sin cuota")
    monkeypatch.setattr(continuidad, "llamar", falla)
    continuidad.finalizar(lid, "cortada")
    assert "se cortó" in continuidad.manejar_corte(lid).mensaje


def test_colgar_normal_no_envia_nada():
    ced = "6667778"
    memoria.registrar_cliente(ced, "Pedro")
    c = TestClient(api.app)
    lid = c.post("/llamadas", json={"cedula": ced}).json()["id"]
    r = c.post(f"/llamadas/{lid}/finalizar?motivo=colgo").json()
    assert r["aviso_whatsapp"] is None and c.get(f"/whatsapp/{ced}/mensajes").json() == []


def test_llamada_sin_conversacion_no_molesta(con_conversacion):
    ced = "8889990"
    memoria.registrar_cliente(ced, "Sofía")
    lid = continuidad.iniciar(ced)
    continuidad.finalizar(lid, "cortada")
    assert continuidad.manejar_corte(lid) is None


def test_paginas_sin_emojis():
    import re
    c = TestClient(api.app)
    for ruta in ("/voz", "/whatsapp"):
        r = c.get(ruta)
        assert r.status_code == 200
        assert not re.findall(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", r.text)