import asyncio
import nest_asyncio
nest_asyncio.apply()

import streamlit as st

st.set_page_config(
    page_title="Cadrage Sécurité IA",
    page_icon="🔐",
    layout="wide",
    initial_sidebar_state="expanded",
)

from database.db_manager import init_db
from views.auth import render_login
from views.admin import render_admin
from views.dashboard import render_dashboard

st.markdown(
    """
    <style>
    table {
        display: block;
        overflow-x: auto;
        max-width: 100%;
        white-space: nowrap;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

try:
    init_db()
except Exception as e:
    st.error(f"Erreur lors de l'initialisation de la base de données : {e}")
    st.stop()

if "user" not in st.session_state:
    render_login()
elif st.session_state.get("current_view") == "admin":
    render_admin()
else:
    render_dashboard()
