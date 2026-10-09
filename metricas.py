"""MÉTRICAS de operación (FCR/resolución autónoma, AHT, CSAT, escalamiento, continuidad).
Se calculan desde la BD: no gastan cuota del modelo. Genérico: no cambia entre retos."""
import json
from collections import Counter
from datetime import datetime
from memoria import _con, _ahora

with _con() as c:
    c.execute("""CREATE TABLE IF NOT EXISTS encuestas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cedula TEXT, canal TEXT, puntaje INTEGER, creado TEXT)""")


# >> Guarda la calificación 1 a 5 al terminar la llamada (CSAT).
def registrar_encuesta(cedula: str, canal: str, puntaje: int):
    with _con() as c:
        c.execute("INSERT INTO encuestas (cedula, canal, puntaje, creado) VALUES (?, ?, ?, ?)",
                  (cedula, canal, puntaje, _ahora()))


# >> Calcula un porcentaje con un decimal.
def _pct(a: int, b: int) -> float | None:
    return round(100 * a / b, 1) if b else None


# >> Indicadores desde la BD, sin gastar tokens: resolución autónoma, escalamiento, AHT, CSAT y continuidad.
def calcular() -> dict:
    with _con() as c:
        mensajes = c.execute("SELECT cedula, canal, rol, datos, creado FROM mensajes ORDER BY id").fetchall()
        escal = c.execute("SELECT cedula, datos, creado FROM escalamientos").fetchall()
        encuestas = [f["puntaje"] for f in c.execute("SELECT puntaje FROM encuestas")]
        llamadas = c.execute("SELECT cedula, estado, fin FROM llamadas").fetchall()

    # Conversación = mensajes de un cliente sin pausas de más de 30 min
    conv: dict[tuple, list[str]] = {}
    sesion: dict[str, tuple] = {}
    canales, acciones = Counter(), 0
    for m in mensajes:
        t = datetime.fromisoformat(m["creado"])
        ult = sesion.get(m["cedula"])
        if not ult or (t - datetime.fromisoformat(conv[ult][-1])).total_seconds() > 1800:
            sesion[m["cedula"]] = (m["cedula"], m["creado"])
        conv.setdefault(sesion[m["cedula"]], []).append(m["creado"])
        if m["rol"] == "user":
            canales[m["canal"]] += 1
        if m["rol"] == "tool" and any(k in m["datos"] for k in ("radicado", "ticket")):
            acciones += 1

    # >> Ubica a qué conversación pertenece un escalamiento.
    def _sesion_de(cedula, creado):
        cands = [k for k, ts in conv.items() if k[0] == cedula and ts[0] <= creado]
        return max(cands, key=lambda k: k[1]) if cands else None
    escaladas = {s for e in escal if (s := _sesion_de(e["cedula"], e["creado"]))}
    total = len(conv)
    duraciones = [
        (datetime.fromisoformat(max(t)) - datetime.fromisoformat(min(t))).total_seconds()
        for t in conv.values() if len(t) > 1
    ]

    cortadas = [ll for ll in llamadas if ll["estado"] == "cortada"]
    recuperadas = sum(
        1 for ll in cortadas
        if ll["fin"] and any(m["cedula"] == ll["cedula"] and m["canal"] == "whatsapp" and m["rol"] == "user"
                             and m["creado"] >= ll["fin"] for m in mensajes)
    )

    return {
        "conversaciones": total,
        "interacciones": sum(canales.values()),
        "resolucion_autonoma_pct": _pct(total - len(escaladas & set(conv)), total),
        "escalamiento_pct": _pct(len(escaladas & set(conv)), total),
        "aht_segundos": round(sum(duraciones) / len(duraciones)) if duraciones else None,
        "csat_pct": _pct(sum(1 for p in encuestas if p >= 4), len(encuestas)),
        "encuestas": len(encuestas),
        "acciones_resueltas": acciones,
        "canales": dict(canales),
        "emociones": dict(Counter(json.loads(e["datos"])["emocion"] for e in escal)),
        "llamadas": {"total": len(llamadas), "cortadas": len(cortadas), "recuperadas": recuperadas},
    }