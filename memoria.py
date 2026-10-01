"""MEMORIA por cliente en SQLite. Genérica: no cambia entre retos.
La conversación pertenece al CLIENTE, no al canal -> base de la continuidad omnicanal."""
import json
import os
import sqlite3
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
DB = os.getenv("AGENTE_DB", "agente.db")   # los tests usan otra BD


def _con():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


with _con() as c:
    c.executescript("""
    CREATE TABLE IF NOT EXISTS clientes (
        cedula   TEXT PRIMARY KEY,
        nombre   TEXT,
        telefono TEXT,
        creado   TEXT
    );
    CREATE TABLE IF NOT EXISTS mensajes (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        cedula  TEXT REFERENCES clientes(cedula),
        canal   TEXT,          -- web | voz | whatsapp
        rol     TEXT,          -- user | assistant | tool
        datos   TEXT,          -- el mensaje completo en JSON
        creado  TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_mensajes_cedula ON mensajes(cedula);
    """)


def registrar_cliente(cedula: str, nombre: str, telefono: str | None = None) -> dict:
    """Devuelve el cliente; si no existe lo crea."""
    with _con() as c:
        fila = c.execute("SELECT * FROM clientes WHERE cedula = ?", (cedula,)).fetchone()
        if fila:
            return {**dict(fila), "nuevo": False}
        c.execute("INSERT INTO clientes VALUES (?, ?, ?, ?)", (cedula, nombre, telefono, _ahora()))
        return {"cedula": cedula, "nombre": nombre, "telefono": telefono, "nuevo": True}


def guardar_mensajes(cedula: str, mensajes: list[dict], canal: str = "web"):
    with _con() as c:
        c.executemany(
            "INSERT INTO mensajes (cedula, canal, rol, datos, creado) VALUES (?, ?, ?, ?, ?)",
            [(cedula, canal, m["role"], json.dumps(m, ensure_ascii=False), _ahora()) for m in mensajes],
        )


def cargar_historial(cedula: str) -> list[dict]:
    with _con() as c:
        filas = c.execute("SELECT datos FROM mensajes WHERE cedula = ? ORDER BY id", (cedula,)).fetchall()
    return [json.loads(f["datos"]) for f in filas]


def listar_clientes() -> list[dict]:
    """Para el panel del supervisor."""
    with _con() as c:
        filas = c.execute("""
            SELECT c.cedula, c.nombre,
                   COUNT(m.id)  AS mensajes,
                   MAX(m.creado) AS ultimo,
                   (SELECT canal FROM mensajes WHERE cedula = c.cedula ORDER BY id DESC LIMIT 1) AS ultimo_canal
            FROM clientes c LEFT JOIN mensajes m ON m.cedula = c.cedula
            GROUP BY c.cedula
            ORDER BY ultimo DESC
        """).fetchall()
    return [dict(f) for f in filas]


def a_chat(historial: list[dict]) -> list[tuple]:
    """Convierte el historial del modelo en burbujas (rol, texto, pasos) para mostrar."""
    chat, pasos, llamadas = [], [], {}
    for m in historial:
        if m["role"] == "user":
            chat.append(("user", m["content"], []))
        elif m["role"] == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                llamadas[tc["id"]] = f'{tc["function"]["name"]}({tc["function"]["arguments"]})'
        elif m["role"] == "tool":
            pasos.append(f'🔧 {llamadas.get(m["tool_call_id"], "?")} ↳ {m["content"]}')
        elif m["role"] == "assistant":
            chat.append(("assistant", m.get("content") or "", pasos))
            pasos = []
    return chat


def obtener_cliente(cedula: str) -> dict | None:
    with _con() as c:
        fila = c.execute("SELECT * FROM clientes WHERE cedula = ?", (cedula,)).fetchone()
    return dict(fila) if fila else None