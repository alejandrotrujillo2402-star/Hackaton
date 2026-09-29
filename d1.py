import os
import time
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError

load_dotenv()
TOKEN = os.getenv("GEMINI_API_KEY")
MODEL = "gemini-3.6-flash"
assert TOKEN, "No se encontró GEMINI_API_KEY en .env"

client = OpenAI(
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    api_key=TOKEN,
)


def llamar(**kwargs):
    """Llama al modelo y reintenta si llega un 429 (límite: 5 peticiones/min)."""
    for intento in range(5):
        try:
            return client.chat.completions.create(model=MODEL, **kwargs)
        except RateLimitError:
            espera = 15 * (intento + 1)
            print(f"[429] esperando {espera}s...")
            time.sleep(espera)
    raise RuntimeError("Se agotaron los reintentos")


# 1) system prompt + conteo de tokens
r = llamar(
    messages=[
        {"role": "system", "content": "Eres un asistente conciso. Responde en español."},
        {"role": "user", "content": "¿Qué es un agente de IA? 2 líneas."},
    ],
)
print(r.choices[0].message.content)

u = r.usage  # tokens gastados
razonamiento = u.total_tokens - u.prompt_tokens - u.completion_tokens
print(f"\ntokens -> in={u.prompt_tokens} out={u.completion_tokens} "
      f"razonamiento={razonamiento} total={u.total_tokens}")

# 2) temperatura: 0 = predecible, 1 = creativo
for t in (0.0, 1.0):
    print(f"\n--- temperature={t} ---")
    for _ in range(3):
        r = llamar(
            temperature=t,
            messages=[{"role": "user", "content": "Nombre creativo para una app de buses. Solo el nombre."}],
        )
        print(r.choices[0].message.content.strip())

# 3) streaming: el texto aparece palabra por palabra
print("\n--- streaming ---")
stream = llamar(
    stream=True,
    messages=[{"role": "user", "content": "Explica RAG en 3 frases."}],
)
for chunk in stream:
    if chunk.choices and chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
print()