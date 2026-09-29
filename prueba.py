import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
TOKEN = os.getenv("GEMINI_API_KEY")

client = OpenAI(
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    api_key=TOKEN,
)

respuesta = client.chat.completions.create(
    model="gemini-3.6-flash",
    messages=[{"role": "user", "content": "Hola, explícame qué es un agente de IA en 2 líneas"}],
)

print(respuesta.choices[0].message.content)