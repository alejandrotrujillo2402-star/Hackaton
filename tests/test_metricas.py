from fastapi.testclient import TestClient
import memoria
import metricas
import api


def test_metricas_estructura_y_rangos():
    memoria.registrar_cliente("2223334", "Marta")
    memoria.guardar_mensajes("2223334", [{"role": "user", "content": "hola"},
                                         {"role": "assistant", "content": "hola Marta"}], canal="web")
    m = metricas.calcular()
    for k in ("resolucion_autonoma_pct", "escalamiento_pct", "aht_segundos", "csat_pct",
              "acciones_resueltas", "canales", "emociones", "llamadas"):
        assert k in m
    assert 0 <= m["resolucion_autonoma_pct"] <= 100
    assert m["canales"]["web"] >= 1


def test_csat_cuenta_solo_4_y_5():
    antes = metricas.calcular()
    n0 = antes["encuestas"]
    buenos0 = round((antes["csat_pct"] or 0) * n0 / 100)
    metricas.registrar_encuesta("2223334", "voz", 5)
    metricas.registrar_encuesta("2223334", "voz", 2)
    m = metricas.calcular()
    assert m["encuestas"] == n0 + 2
    assert round(m["csat_pct"] * m["encuestas"] / 100) == buenos0 + 1


def test_endpoints_panel():
    c = TestClient(api.app)
    assert c.get("/metricas").status_code == 200
    assert c.post("/encuestas", json={"cedula": "2223334", "canal": "voz", "puntaje": 9}).status_code == 422
    assert c.post("/encuestas", json={"cedula": "2223334", "canal": "voz", "puntaje": 4}).status_code == 201
    r = c.get("/panel")
    import re
    assert r.status_code == 200 and not re.findall(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", r.text)