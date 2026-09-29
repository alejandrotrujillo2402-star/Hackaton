import json
from typing import Literal
from pydantic import BaseModel, ValidationError
from d2 import llamar


# 1) Esquema: lo que TU código necesita recibir
class Reporte(BaseModel):
    ruta: str
    hora: str | None
    retraso_min: int
    tipo: Literal["retraso", "accidente", "lleno", "otro"]


SYSTEM = f"""Extraes datos de reportes de buses.
Responde SOLO con un JSON válido, sin texto adicional ni bloques ```.
Esquema: {json.dumps(Reporte.model_json_schema(), ensure_ascii=False)}
Si un dato no aparece: hora=null, retraso_min=0."""


def limpiar(texto: str) -> str:
    """Quita ```json ... ``` si el modelo lo agrega."""
    return texto.replace("```json", "").replace("```", "").strip()


def extraer(texto: str, reintentos: int = 2) -> Reporte:
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": texto},
    ]
    for _ in range(reintentos + 1):
        r = llamar(messages=messages, temperature=0)
        crudo = limpiar(r.choices[0].message.content)
        try:
            return Reporte.model_validate_json(crudo)
        except ValidationError as e:
            # 2) Autocorrección: le mostramos su error al modelo
            print(f"[JSON inválido, reintentando]\n{e}\n")
            messages.append({"role": "assistant", "content": crudo})
            messages.append({"role": "user",
                             "content": f"Tu JSON es inválido: {e}. Corrígelo. Solo JSON."})
    raise RuntimeError(f"No se pudo extraer: {texto}")


reportes = [
    "El bus de la ruta 12 pasó a las 7:40, iba con 20 minutos de retraso",
    "hoy no pasó nada raró a medio día",
    "el bus numero 7 se volcó",
]

for texto in reportes:
    rep = extraer(texto)
    print(texto)
    print(" ->", rep.model_dump())

    # 3) Ahora sí puedes usar los datos con lógica normal
    if rep.retraso_min > 15:
        print(" ⚠️  retraso alto, notificar")
    print()