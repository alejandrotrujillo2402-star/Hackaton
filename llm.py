import os, re, time
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError, InternalServerError, APIConnectionError

load_dotenv()
TOKEN = os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY")
BASE_URL = os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
MODEL = os.getenv("LLM_MODEL", "gemini-3.8-flash")
MODEL_RESPALDO = None             # <- otro modelo de tu lista, ej: "gemini-3.6-flash"
assert TOKEN, "No se encontró GEMINI_API_KEY en .env"

client = OpenAI(base_url=BASE_URL, api_key=TOKEN)

INTERVALO = 1
_ultima = 0.0

def _turno():
    global _ultima
    falta = INTERVALO - (time.time() - _ultima)
    if falta > 0:
        time.sleep(falta)
    _ultima = time.time()

def llamar(**kwargs):
    modelo = MODEL
    for intento in range(4):
        _turno()
        try:
            return client.chat.completions.create(model=modelo, **kwargs)
        except RateLimitError as e:
            texto = str(e)
            if "PerDay" in texto:
                if MODEL_RESPALDO and modelo != MODEL_RESPALDO:
                    print(f"[cuota diaria de {modelo}] cambiando a {MODEL_RESPALDO}")
                    modelo = MODEL_RESPALDO
                    continue
                raise RuntimeError("Cuota DIARIA agotada. Revisa https://ai.dev/rate-limit") from e
            m = re.search(r"retry in ([\d.]+)s", texto)
            espera = float(m.group(1)) + 1 if m else 20 * (intento + 1)
            print(f"[429] esperando {espera:.0f}s...")
            time.sleep(espera)
        except (InternalServerError, APIConnectionError) as e:   # 500/503 o red caída
            if intento >= 1 and MODEL_RESPALDO and modelo != MODEL_RESPALDO:
                print(f"[{modelo} saturado] cambiando a {MODEL_RESPALDO}")
                modelo = MODEL_RESPALDO
            else:
                espera = 5 * (intento + 1)
                print(f"[503/red] reintentando en {espera}s...")
                time.sleep(espera)
    raise RuntimeError("El servicio de IA no responde. Intenta en unos minutos.")
