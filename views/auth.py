import streamlit as st
from database.db_manager import verify_user


def render_login() -> None:
    _, col, _ = st.columns([1, 1, 1])

    with col:
        st.markdown("## 🔐 Cadrage Sécurité IA")
        st.caption("Plateforme d'accompagnement expert — analyse & cadrage sécurité de projets IT")
        st.divider()

        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Nom d'utilisateur", placeholder="admin")
            password = st.text_input("Mot de passe", type="password")
            submitted = st.form_submit_button(
                "Se connecter", use_container_width=True, type="primary"
            )

        if submitted:
            if not username or not password:
                st.error("Veuillez remplir tous les champs.")
            else:
                user = verify_user(username, password)
                if user:
                    st.session_state.user = user
                    st.rerun()
                else:
                    st.error("Identifiants incorrects.")
