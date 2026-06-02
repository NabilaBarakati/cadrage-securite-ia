from typing import Dict, List

import streamlit as st
from database import db_manager
from services import llm_service


# ── Helpers ───────────────────────────────────────────────────────────────────

def _count_admins(users: List[Dict]) -> int:
    return sum(1 for u in users if u["role"] == "ADMIN")


# ── Sidebar ───────────────────────────────────────────────────────────────────

def _render_admin_sidebar() -> None:
    with st.sidebar:
        st.markdown("## ⚙️ Administration")
        st.divider()

        user = st.session_state.user
        st.markdown(f"**{user['username']}** `{user['role']}`")
        st.divider()

        if st.button("📊 Retour aux projets", use_container_width=True):
            st.session_state.current_view = "dashboard"
            st.rerun()

        st.divider()

        if st.button("🚪 Déconnexion", use_container_width=True):
            st.session_state.clear()
            st.rerun()


# ── User management ───────────────────────────────────────────────────────────

def _render_user_management() -> None:
    current_uid = st.session_state.user["id"]

    # ── Add user form ─────────────────────────────────────────────────────────
    with st.expander("➕ Ajouter un utilisateur", expanded=True):
        with st.form("add_user_form", clear_on_submit=True):
            col_a, col_b = st.columns(2)
            with col_a:
                new_username = st.text_input("Nom d'utilisateur *")
                new_password = st.text_input("Mot de passe *", type="password")
            with col_b:
                new_role = st.selectbox("Rôle", ["CREATOR", "VIEWER", "ADMIN"])
                new_password_confirm = st.text_input("Confirmer le mot de passe *", type="password")
            submitted = st.form_submit_button(
                "Créer l'utilisateur", type="primary", use_container_width=True
            )

        if submitted:
            if not new_username.strip() or not new_password:
                st.error("Nom d'utilisateur et mot de passe obligatoires.")
            elif new_password != new_password_confirm:
                st.error("Les mots de passe ne correspondent pas.")
            elif len(new_password) < 4:
                st.error("Le mot de passe doit contenir au moins 4 caractères.")
            else:
                try:
                    db_manager.create_user(new_username.strip(), new_password, new_role)
                    st.toast(f"Utilisateur « {new_username.strip()} » créé avec le rôle {new_role}.", icon="✅")
                    st.rerun()
                except Exception as e:
                    if "UNIQUE" in str(e):
                        st.error("Ce nom d'utilisateur est déjà pris.")
                    else:
                        st.error(f"Erreur : {e}")

    st.divider()
    st.subheader("Utilisateurs existants")

    users = db_manager.get_all_users()
    n_admins = _count_admins(users)
    role_options = ["ADMIN", "CREATOR", "VIEWER"]

    for u in users:
        is_self = u["id"] == current_uid
        is_last_admin = u["role"] == "ADMIN" and n_admins == 1
        protected = is_self or is_last_admin

        with st.container(border=True):
            col_info, col_role, col_actions = st.columns([3, 3, 2])

            with col_info:
                self_badge = " *(vous)*" if is_self else ""
                st.markdown(f"**{u['username']}**{self_badge}")
                st.caption(f"ID #{u['id']} · Créé le {u['created_at'][:10]}")

            with col_role:
                if protected:
                    st.markdown(f"`{u['role']}`")
                    if is_last_admin:
                        st.caption("Dernier administrateur")
                else:
                    selected_role = st.selectbox(
                        "Rôle",
                        role_options,
                        index=role_options.index(u["role"]),
                        key=f"role_sel_{u['id']}",
                        label_visibility="collapsed",
                    )

            with col_actions:
                if not protected:
                    apply_col, del_col = st.columns(2)
                    with apply_col:
                        if st.button("✓", key=f"apply_{u['id']}", help="Appliquer le rôle"):
                            db_manager.update_user_role(u["id"], selected_role)
                            st.toast(f"Rôle de « {u['username']} » mis à jour.", icon="✅")
                            st.rerun()
                    with del_col:
                        if st.button("🗑", key=f"del_{u['id']}", help="Supprimer l'utilisateur"):
                            db_manager.delete_user(u["id"])
                            st.toast(f"Utilisateur « {u['username']} » supprimé.", icon="✅")
                            st.rerun()


# ── Prompt configuration ──────────────────────────────────────────────────────

def _render_prompt_config() -> None:
    st.markdown(
        "Modifiez le texte des prompts envoyés à l'IA pour chaque étape. "
        "Les variables injectées automatiquement sont :"
    )
    st.code("{project_name}   {project_desc}   {previous_steps_context}", language=None)
    st.divider()

    steps = llm_service.get_all_steps_full()

    for s in steps:
        with st.expander(f"{s['icon']} Étape {s['number']} — {s['title']}", expanded=False):
            edited_prompt = st.text_area(
                "Prompt",
                value=s["prompt"],
                height=340,
                key=f"prompt_edit_{s['number']}",
                label_visibility="collapsed",
            )
            save_col, hint_col = st.columns([1, 4])
            with save_col:
                if st.button("💾 Sauvegarder", key=f"save_prompt_{s['number']}", type="primary"):
                    try:
                        llm_service.update_step_prompt(s["number"], edited_prompt)
                        st.toast(f"Prompt de l'étape {s['number']} sauvegardé.", icon="✅")
                    except Exception as e:
                        st.error(f"Erreur : {e}")
            with hint_col:
                st.caption(
                    "⚠️ La modification s'applique aux prochaines générations. "
                    "Les réponses déjà enregistrées ne sont pas affectées."
                )


# ── Main entry point ──────────────────────────────────────────────────────────

def render_admin() -> None:
    if st.session_state.user.get("role") != "ADMIN":
        st.error("Accès refusé. Cette page est réservée aux administrateurs.")
        return

    _render_admin_sidebar()

    st.title("⚙️ Administration")

    tab_users, tab_prompts = st.tabs(["👥 Gestion des utilisateurs", "📝 Configuration des prompts"])

    with tab_users:
        _render_user_management()

    with tab_prompts:
        _render_prompt_config()
