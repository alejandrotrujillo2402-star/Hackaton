##creacion del agente con historial de mensajes (que recuerde lo que se le ha dicho antes)
import os 
import time
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError

load_dotenv()
TOKEN = os.getenv("GEMINI_API_KEY")
MODEL = "gemini-3.6-flash"
assert TOKEN, "No se encontró GEMINI_API    KEY en .env"

#generamos un cliente de OpenAI con la API de Gemini
 
client = OpenAI(
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    api_key=TOKEN,
)

#logica 
def llamar(**kwargs):
    ##llama al modelo y reintenta si llega un 429 (limite máximo 5 peticiones)
 for intento in range(5):
    try:
        return client.chat.completions.create(model=MODEL, **kwargs)
    except RateLimitError:
       espera = 15 * (intento+1)
       print(f"[429] esperando {espera}s...")
       time.sleep(espera)
    raise RuntimeError("Se agotaron los reintentos")