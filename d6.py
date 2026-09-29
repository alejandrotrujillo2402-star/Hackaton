import streamlit as st
from d5 import SYSTEM, correr_agente

st.set_page_config(page_title="Agente de Buses Manizales", page_icon="🚌")
st.title("🚌 Agente de Buses Manizales")

# ---------- Estado (sobrevive entre interacciones) ----------
if "messages" not in st.session_state:
    st.session_state.messages = [SYSTEM]   # lo que ve el modelo
    st.session_state.chat = []             # lo que ve el usuario: (rol, texto, pasos)

# ---------- Barra lateral ----------
with st.sidebar:
    st.header("Panel")
    st.metric("Mensajes en memoria", len(st.session_state.messages))
    if st.button("🗑️ Nueva conversación"):
        st.session_state.messages = [SYSTEM]
        st.session_state.chat = []
        st.rerun()
    st.caption("Cada mensaje usa 2–3 llamadas al modelo.")

# ---------- Historial ----------
for rol, texto, pasos in st.session_state.chat:
    with st.chat_message(rol):
        if pasos:
            with st.expander(f"🔧 {len(pasos)} herramienta(s) usada(s)"):
                for p in pasos:
                    st.code(p, language=None)
        st.markdown(texto)

# ---------- Entrada ----------
if pregunta := st.chat_input("Pregunta por rutas, horarios, paradas..."):
    st.session_state.chat.append(("user", pregunta, []))
    st.session_state.messages.append({"role": "user", "content": pregunta})
    with st.chat_message("user"):
        st.markdown(pregunta)

    with st.chat_message("assistant"):
        with st.spinner("Pensando y consultando herramientas..."):
            try:
                texto, pasos = correr_agente(st.session_state.messages)
            except Exception as e:
                texto, pasos = f"⚠️ Error: {e}", []
        if pasos:
            with st.expander(f"🔧 {len(pasos)} herramienta(s) usada(s)"):
                for p in pasos:
                    st.code(p, language=None)
        st.markdown(texto)

    st.session_state.chat.append(("assistant", texto, pasos))