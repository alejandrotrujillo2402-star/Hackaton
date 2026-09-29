from d2 import llamar 
SYSTEM = {"role": "system", "content": "Eres un aistente de inteligencia rtificial, responde máximo en tres lineas"}

messages = [SYSTEM]
ultimo_uso = None 

print("Bienvenido a este pequeño agente de ia, comandos: /salir, / reset, /historial./n")

while True:
    entrada = input("Tú:")
    if not entrada:
        continue 

    if entrada == "/salir":
        break

    if entrada == "/reset":
      messages = [SYSTEM]
      print("Historial de mensajes reseteado.")
      continue

    if entrada == "/historial":
        print(f"[mensajes: {len(messages)}]")
        if ultimo_uso:
            print(f"[última respuesta -> in={ultimo_uso.prompt_tokens} "
                  f"out={ultimo_uso.completion_tokens} total={ultimo_uso.total_tokens}]")
        print()
        continue
 # 1) agregamos mensajes al usuario 
    messages.append({"role": "user", "content": entrada})

    #2 enviar Todo el historial 
    r = llamar(messages=messages)
    texto = r.choices[0].message.content 
    ultimo_uso = r.usage

    #3) guardar la repsuesta para que el modelo la "recuerde" 
    messages.append({"role": "assistant", "content": texto})

    print(f"IA: {texto}")