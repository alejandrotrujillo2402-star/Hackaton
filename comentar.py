"""Agrega un comentario-guion encima de cada función del proyecto.
Solo inserta comentarios: no cambia la lógica. Se puede correr varias veces.
Uso: python comentar.py
"""
import re
from pathlib import Path

GUIONES = {
    "llm.py": {
        "_turno": "Respeta una pausa mínima entre llamadas para no superar el límite del proveedor.",
        "_esperar_turno": "Respeta una pausa mínima entre llamadas para no superar el límite del proveedor.",
        "llamar": "Única puerta al modelo: envía la conversación; si hay 429/503 reintenta o cambia al modelo de respaldo.",
    },
    "motor.py": {
        "tool": "Describe una herramienta en JSON Schema; el modelo decide usarla leyendo esta descripción.",
        "_ejecutar": "Corre la herramienta que pidió el modelo; inyecta la cédula de la sesión y convierte cualquier error en información.",
        "limpiar": "Quita restos internos del modelo (pensamientos, puntos sueltos) antes de mostrar la respuesta.",
        "correr_agente": "Loop del agente: pregunta al modelo, ejecuta herramientas y repite hasta responder (máximo 6 pasos).",
    },
    "rag.py": {
        "_coleccion": "Prepara el modelo de embeddings local y la colección de ChromaDB del dominio.",
        "cargar": "Guarda los documentos como embeddings; corre en el equipo, sin gastar tokens.",
        "buscador": "Fabrica la herramienta buscar_documentos atada a la colección del dominio.",
        "buscar_documentos": "Busca por significado y descarta lo que supere el umbral 0.75: si no hay nada, el agente dice 'no sé'.",
    },
    "memoria.py": {
        "_con": "Abre la conexión a SQLite.",
        "_ahora": "Fecha y hora actual en texto.",
        "registrar_cliente": "Devuelve el cliente; si no existe, lo crea.",
        "guardar_mensajes": "Guarda cada mensaje del turno con su canal (web, voz, whatsapp).",
        "cargar_historial": "Trae toda la conversación del cliente, venga del canal que venga: base de la continuidad.",
        "listar_clientes": "Resumen por cliente para el panel: mensajes, última fecha y último canal.",
        "a_chat": "Convierte el historial técnico en burbujas legibles para mostrar.",
        "obtener_cliente": "Busca un cliente por cédula.",
    },
    "seguridad.py": {
        "_hash": "Cifra el código con SHA-256: nunca se guarda en claro.",
        "generar_otp": "Crea un código de 6 dígitos que vence en 5 minutos.",
        "enviar_sms_simulado": "Simula el envío del SMS (en producción sería un proveedor real).",
        "validar_otp": "Revisa el código: vencimiento, máximo 3 intentos y un solo uso.",
        "esta_verificado": "Indica si el cliente sigue verificado (30 minutos).",
        "requiere_verificacion": "Decorador: la herramienta se niega sola si no hay verificación. La seguridad la impone el código.",
        "solicitar_codigo": "Herramienta: envía el código al celular registrado.",
        "verificar_codigo": "Herramienta: valida el código que dicta el cliente.",
        "herramientas_verificacion": "Entrega las herramientas de verificación para que cualquier dominio las reutilice.",
        "cerrar_sesion": "Al colgar, la verificación deja de valer: la próxima llamada vuelve a pedir código.",
    },
    "escalamiento.py": {
        "escalar_a_humano": "Pasa el caso a un asesor con emoción, urgencia, resumen y pendiente; entrega un ticket ESC.",
        "listar_escalamientos": "Casos pendientes para el panel del supervisor.",
    },
    "continuidad.py": {
        "iniciar": "Registra el inicio de una llamada.",
        "latido": "La página de voz avisa cada 4 s que la llamada sigue viva.",
        "finalizar": "Cierra la llamada como completada (colgó) o cortada (se perdió la señal).",
        "revisar_cortes": "Detecta llamadas con más de 10 s sin latido y las marca como cortadas.",
        "_transcripcion": "Arma el texto de lo que se habló en la llamada.",
        "generar_aviso": "El modelo resume la llamada en JSON validado: resumen, pendiente y mensaje; si falla, usa plantilla.",
        "manejar_corte": "Envía el WhatsApp para continuar justo donde quedó la llamada.",
        "mensajes_whatsapp": "Mensajes del canal WhatsApp para la página simulada.",
        "cedula_de": "Devuelve la cédula asociada a una llamada.",
    },
    "metricas.py": {
        "registrar_encuesta": "Guarda la calificación 1 a 5 al terminar la llamada (CSAT).",
        "_pct": "Calcula un porcentaje con un decimal.",
        "calcular": "Indicadores desde la BD, sin gastar tokens: resolución autónoma, escalamiento, AHT, CSAT y continuidad.",
        "_sesion_de": "Ubica a qué conversación pertenece un escalamiento.",
    },
    "dominio_salud.py": {
        "_norm": "Quita tildes y mayúsculas: 'Pediatría' y 'pediatria' valen lo mismo.",
        "_horarios": "Agenda posible: próximos 3 días hábiles con 3 franjas cada uno.",
        "consultar_disponibilidad": "Horarios libres = agenda posible menos citas activas de esa especialidad.",
        "agendar_cita": "Requiere verificación. Revisa de nuevo la disponibilidad y agenda; entrega código CITA.",
        "mis_citas": "Requiere verificación. Citas activas del afiliado de la sesión.",
        "cancelar_cita": "Requiere verificación. Solo cancela citas propias; no revela si existen para otro.",
        "estado_autorizacion": "Requiere verificación. Estado de una autorización médica (AUT-xxxx).",
    },
    "api.py": {
        "_vigilar": "Hilo en segundo plano: cada 2 s busca llamadas cortadas y dispara el WhatsApp.",
        "lifespan": "Arranca el vigilante cuando inicia la API.",
        "inicio": "La raíz redirige a la llamada de voz.",
        "pagina_voz": "Sirve la página de llamada de voz.",
        "pagina_panel": "Sirve el panel de operación.",
        "pagina_whatsapp": "Sirve el WhatsApp simulado.",
        "health": "Indica si la API está viva y qué dominio cargó.",
        "crear_cliente": "Registra un cliente (cédula validada).",
        "listar_clientes": "Lista clientes para el panel.",
        "ver_metricas": "Entrega los indicadores al panel.",
        "crear_encuesta": "Recibe la calificación CSAT.",
        "escalamientos_pendientes": "Lista los casos escalados a humanos.",
        "historial": "Conversación completa de un cliente.",
        "chat": "Puerta única de todos los canales: carga historial, corre el agente y guarda el turno con su canal.",
        "iniciar_llamada": "Registra una llamada nueva.",
        "finalizar_llamada": "Cierra la llamada; si se cortó, envía WhatsApp; si colgó, cierra la verificación.",
        "mensajes_whatsapp": "Mensajes del chat de WhatsApp simulado.",
    },
}

total = 0
for archivo, guiones in GUIONES.items():
    ruta = Path(archivo)
    if not ruta.exists():
        print(f"(no existe {archivo}, se omite)")
        continue
    lineas = ruta.read_text(encoding="utf-8").splitlines(keepends=True)
    salida, n = [], 0
    for i, linea in enumerate(lineas):
        m = re.match(r"^(\s*)(?:async\s+)?def\s+(\w+)\s*\(", linea)
        if m and m.group(2) in guiones:
            sangria, nombre = m.group(1), m.group(2)
            # si hay decoradores justo arriba, el comentario va encima de ellos
            j = len(salida)
            while j > 0 and salida[j - 1].strip().startswith("@"):
                j -= 1
            if not (j > 0 and salida[j - 1].strip().startswith("# >>")):
                salida.insert(j, f"{sangria}# >> {guiones[nombre]}\n")
                n += 1
        salida.append(linea)
    ruta.write_text("".join(salida), encoding="utf-8")
    print(f"{archivo}: {n} guiones")
    total += n
print(f"\nTotal: {total} guiones agregados")