import streamlit as st
import memoria
import seguridad
import escalamiento
from motor import correr_agente
import dominio_buses as dominio   # <- el día del reto: import dominio_X as dominio

st.set_page_config(page_title=dominio.NOMBRE, page_icon="🤖")
st.title(dominio.NOMBRE)


def system_para(cliente: dict) -> dict:
    return {"role": "system", "content": dominio.SYSTEM["content"] +
            f"\nCliente actual: {cliente['nombre']} (cédula {cliente['cedula']}). Llámalo por su nombre."}


def mostrar_pasos(pasos):
    if pasos:
        with st.expander(f"🔧 {len(pasos)} herramienta(s) usada(s)"):
            for p in pasos:
                st.code(p, language=None)


# ---------- Barra lateral: sesión + panel del supervisor ----------
with st.sidebar:
    if "cliente" in st.session_state:
        cli = st.session_state.cliente
        st.header(f"👤 {cli['nombre']}")
        st.caption(f"Cédula {cli['cedula']}")
        st.metric("Mensajes en memoria", len(st.session_state.messages))
        st.write("🔐 Verificado" if seguridad.esta_verificado(cli["cedula"]) else "🔓 No verificado")
        if sms := seguridad.ULTIMOS_SMS.get(cli["cedula"]):
            st.info(f"📱 SMS simulado:\n\n{sms}")
        if st.button("🚪 Cerrar sesión"):
            for k in ("cliente", "messages", "chat"):
                st.session_state.pop(k, None)
            st.rerun()
    st.divider()
    st.subheader("🖥️ Panel del supervisor")
    clientes = memoria.listar_clientes()
    if clientes:
        st.dataframe(clientes, hide_index=True, use_container_width=True)
    else:
        st.caption("Aún no hay clientes.")
    st.subheader("🚨 Escalamientos pendientes")
    ICONO = {"calmado": "🙂", "confundido": "😕", "frustrado": "😤", "enojado": "😡"}
    esc = escalamiento.listar_escalamientos()
    if not esc:
        st.caption("Ninguno 🎉")
    for e in esc:
        with st.expander(f"{ICONO[e['emocion']]} {e['ticket']} · {e['nombre']} · urgencia {e['urgencia']}/5"):
            st.write(f"**Motivo:** {e['motivo']}")
            st.write(f"**Resumen:** {e['resumen']}")
            st.write(f"**Pendiente:** {e['pendiente']}")

# ---------- Entrada: identificar al cliente ----------
if "cliente" not in st.session_state:
    st.subheader("Identifícate para empezar")
    cedula = st.text_input("Cédula")
    nombre = st.text_input("Nombre (solo si es tu primera vez)")
    telefono = st.text_input("Celular (solo si es tu primera vez)")
    if st.button("Entrar", type="primary"):
        cedula = cedula.strip()
        if not cedula.isdigit():
            st.error("Escribe una cédula válida (solo números).")
            st.stop()
        cliente = memoria.registrar_cliente(cedula, nombre.strip() or "Cliente", telefono.strip() or None)
        historial = memoria.cargar_historial(cedula)
        st.session_state.cliente = cliente
        st.session_state.messages = [system_para(cliente)] + historial
        st.session_state.chat = memoria.a_chat(historial)
        st.rerun()
    st.stop()

# ---------- Conversación ----------
cli = st.session_state.cliente
if st.session_state.chat and not cli["nuevo"]:
    st.info(f"👋 Hola de nuevo, {cli['nombre']}. Aquí está tu conversación anterior.")

for rol, texto, pasos in st.session_state.chat:
    with st.chat_message(rol):
        mostrar_pasos(pasos)
        st.markdown(texto)

if pregunta := st.chat_input("Pregunta por rutas, tarifas, objetos perdidos..."):
    st.session_state.chat.append(("user", pregunta, []))
    st.session_state.messages.append({"role": "user", "content": pregunta})
    with st.chat_message("user"):
        st.markdown(pregunta)

    with st.chat_message("assistant"):
        n = len(st.session_state.messages)
        with st.spinner("Pensando y consultando..."):
            try:
                texto, pasos = correr_agente(st.session_state.messages, dominio.TOOLS, dominio.FUNCIONES,
                                            contexto={"cedula": cli["cedula"]})
                memoria.guardar_mensajes(cli["cedula"], st.session_state.messages[n - 1:], canal="web")
            except Exception as e:
                del st.session_state.messages[n - 1:]   # deshacer el turno a medias
                st.session_state.chat.pop()
                texto, pasos = f"⚠️ {e}", []
        mostrar_pasos(pasos)
        st.markdown(texto)

    if not texto.startswith("⚠️"):
        st.session_state.chat.append(("assistant", texto, pasos))
        st.rerun()