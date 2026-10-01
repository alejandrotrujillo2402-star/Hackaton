import re
import memoria
import seguridad
import motor
import dominio_salud as salud
from tests.test_agente import tool_call

F = salud.FUNCIONES


def _verificado(ced):
    memoria.registrar_cliente(ced, "Ana", "3001112233")
    motor._ejecutar(tool_call("solicitar_codigo", {}), F, {"cedula": ced})
    codigo = re.search(r"\d{6}", seguridad.ULTIMOS_SMS[ced]).group()
    assert motor._ejecutar(tool_call("verificar_codigo", {"codigo": codigo}), F, {"cedula": ced})["ok"]
    return {"cedula": ced}


def test_disponibilidad_sin_verificar_y_tildes():
    r = motor._ejecutar(tool_call("consultar_disponibilidad", {"especialidad": "Pediatría"}), F, {"cedula": "1"})
    assert len(r["horarios"]) == 9


def test_agendar_requiere_verificacion():
    r = motor._ejecutar(tool_call("agendar_cita", {"especialidad": "odontologia", "fecha_hora": "x"}),
                        F, {"cedula": "5550001"})
    assert r["error"] == "VERIFICACION_REQUERIDA"


def test_flujo_cita_completo():
    ctx = _verificado("5550002")
    h = salud.consultar_disponibilidad("medicina general")["horarios"][0]
    r = motor._ejecutar(tool_call("agendar_cita", {"especialidad": "medicina general", "fecha_hora": h}), F, ctx)
    assert r["codigo"].startswith("CITA-")
    assert h not in salud.consultar_disponibilidad("medicina general")["horarios"]   # ya ocupado
    assert len(motor._ejecutar(tool_call("mis_citas", {}), F, ctx)["citas"]) == 1
    assert motor._ejecutar(tool_call("cancelar_cita", {"codigo": r["codigo"]}), F, ctx)["cancelada"]


def test_no_cancela_cita_ajena():
    ctx_a = _verificado("5550003")
    h = salud.consultar_disponibilidad("psicologia")["horarios"][0]
    cod = motor._ejecutar(tool_call("agendar_cita", {"especialidad": "psicologia", "fecha_hora": h}), F, ctx_a)["codigo"]
    ctx_b = _verificado("5550004")
    assert "error" in motor._ejecutar(tool_call("cancelar_cita", {"codigo": cod}), F, ctx_b)


def test_horario_invalido_ofrece_alternativas():
    ctx = _verificado("5550005")
    r = motor._ejecutar(tool_call("agendar_cita", {"especialidad": "pediatria", "fecha_hora": "2020-01-01 03:00"}), F, ctx)
    assert "horarios_disponibles" in r


def test_prompt_tiene_guardrail_medico():
    assert "123" in salud.SYSTEM["content"] and "nunca diagnostiques" in salud.SYSTEM["content"]