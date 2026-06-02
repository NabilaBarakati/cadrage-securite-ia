import asyncio
import nest_asyncio
nest_asyncio.apply()

import streamlit as st
from database.db_manager import init_db
from views.auth import render_login
from views.admin import render_admin
from views.dashboard import render_dashboard

st.set_page_config(
    page_title="Cadrage Sécurité IA",
    page_icon="🔐",
    layout="wide",
    initial_sidebar_state="expanded",
)

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

init_db()

if "user" not in st.session_state:
    render_login()
elif st.session_state.get("current_view") == "admin":
    render_admin()
else:
    render_dashboard()
