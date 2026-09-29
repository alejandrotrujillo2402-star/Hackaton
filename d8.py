import streamlit as st
from motor import correr_agente
import dominio_buses as dominio   # <- el día del reto: import dominio_banco as dominio

st.set_page_config(page_title=dominio.NOMBRE, page_icon="🤖")
st.title(dominio.NOMBRE)

if "messages" not in st.session_state:
    st.session_state.messages = [dominio.SYSTEM]
    st.session_state.chat = []

with st.sidebar:
    st.header("Panel")
    st.metric("Mensajes en memoria", len(st.session_state.messages))
    st.caption(f"Herramientas: {', '.join(dominio.FUNCIONES)}")
    if st.button("🗑️ Nueva conversación"):
        st.session_state.messages = [dominio.SYSTEM]
        st.session_state.chat = []
        st.rerun()


def mostrar_pasos(pasos):
    if pasos:
        with st.expander(f"🔧 {len(pasos)} herramienta(s) usada(s)"):
            for p in pasos:
                st.code(p, language=None)


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
        with st.spinner("Pensando y consultando..."):
            n = len(st.session_state.messages)
            try:
                texto, pasos = correr_agente(st.session_state.messages, dominio.TOOLS, dominio.FUNCIONES)
            except Exception as e:
                del st.session_state.messages[n - 1:]   # deshacer el turno a medias
                texto, pasos = f"⚠️ {e}", []
        mostrar_pasos(pasos)
        st.markdown(texto)

    st.session_state.chat.append(("assistant", texto, pasos))