from datetime import datetime
from typing import Dict, List, Optional

import streamlit as st
from database import db_manager
from services import llm_service
from services.exporter import export_to_docx, export_to_pdf


_KPI_CSS = """
<style>
[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 1.2rem 1rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
[data-testid="stMetricLabel"] {
    font-size: 0.82rem !important;
    color: #64748b !important;
    font-weight: 500 !important;
}
[data-testid="stMetricValue"] {
    font-size: 2rem !important;
    font-weight: 700 !important;
    color: #1e293b !important;
}
</style>
"""

_BADGE_STYLE = {
    "Élevé":  "background:#ef4444;color:#fff;padding:2px 10px;border-radius:20px;font-size:0.72rem;font-weight:600;white-space:nowrap;",
    "Moyen":  "background:#f97316;color:#fff;padding:2px 10px;border-radius:20px;font-size:0.72rem;font-weight:600;white-space:nowrap;",
    "Faible": "background:#22c55e;color:#fff;padding:2px 10px;border-radius:20px;font-size:0.72rem;font-weight:600;white-space:nowrap;",
}


# ── State bootstrap ───────────────────────────────────────────────────────────

def _init_step_states(session_id: int) -> None:
    """Load step states from DB into session_state once per project session."""
    if st.session_state.get("_steps_session_id") == session_id:
        return

    st.session_state._steps_session_id = session_id

    sr_list = db_manager.get_step_responses(session_id)
    sr_by_step = {sr["step_number"]: sr for sr in sr_list}

    steps: dict = {}
    inferred_validated: set = set()

    for meta in llm_service.get_steps():
        n = meta["number"]
        if n in sr_by_step:
            sr = sr_by_step[n]
            initial = sr["ai_response"]

            records = db_manager.get_chat_history(sr["id"])
            follow_ups = [{"role": r["role"], "content": r["content"]} for r in records]

            full_chat = [{"role": "assistant", "content": initial}] + follow_ups

            display = next(
                (m["content"] for m in reversed(full_chat) if m["role"] == "assistant"),
                initial,
            )
            steps[n] = {"response": display, "sr_id": sr["id"], "chat": full_chat}
        else:
            steps[n] = {"response": None, "sr_id": None, "chat": []}

    for n in sorted(sr_by_step):
        if (n + 1) in sr_by_step or n == 10:
            inferred_validated.add(n)

    st.session_state.steps = steps
    existing = st.session_state.get("validated_steps", set())
    st.session_state.validated_steps = inferred_validated | existing


def _previous_responses(step_number: int) -> List[Dict]:
    session_id = st.session_state.session["id"]
    return [r for r in db_manager.get_step_responses(session_id) if r["step_number"] < step_number]


# ── Export helpers ────────────────────────────────────────────────────────────

def _build_export_markdown(session: dict, steps_meta: List[Dict], steps: dict) -> str:
    now = datetime.now().strftime("%d/%m/%Y à %H:%M")
    lines: List[str] = [
        f"# Cadrage Sécurité — {session['project_name']}",
        "",
        f"**Date d'export :** {now}  ",
        f"**Statut :** {session['status']}",
        "",
        "---",
        "",
    ]
    if session.get("project_desc"):
        lines += ["## Description du projet", "", session["project_desc"], "", "---", ""]

    for s in steps_meta:
        n = s["number"]
        response = steps.get(n, {}).get("response")
        if response:
            lines += [
                f"## Étape {n} — {s['icon']} {s['title']}",
                "",
                response,
                "",
                "---",
                "",
            ]

    return "\n".join(lines)


def _render_export_section() -> None:
    session = st.session_state.session
    steps_meta = llm_service.get_steps()
    steps = st.session_state.steps
    validated = st.session_state.validated_steps

    steps_with_response = [s for s in steps_meta if steps.get(s["number"], {}).get("response")]
    if not steps_with_response:
        return

    st.divider()
    st.markdown("#### 📥 Export du rapport de cadrage")

    n_done = len(steps_with_response)
    n_val = sum(1 for s in steps_meta if s["number"] in validated)

    if n_val == 10:
        st.success("Toutes les étapes sont validées — le rapport est complet.")
    else:
        st.info(
            f"**{n_done}/10** étapes générées · **{n_val}/10** validées. "
            "L'export inclut toutes les étapes générées."
        )

    md_content = _build_export_markdown(session, steps_meta, steps)
    safe_name = (
        session["project_name"].lower().replace(" ", "-").replace("/", "-")
    )
    filename = f"cadrage-securite_{safe_name}_{datetime.now().strftime('%Y%m%d')}.md"

    st.download_button(
        label=f"⬇️ Télécharger le rapport Markdown ({n_done} étapes)",
        data=md_content,
        file_name=filename,
        mime="text/markdown",
        type="primary",
        use_container_width=True,
        key="export_report_btn",
    )

    st.download_button(
        label="⬇️ Télécharger en Word (.docx)",
        data=export_to_docx(md_content),
        file_name=filename.replace(".md", ".docx"),
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        use_container_width=True,
        key="export_report_docx",
    )

    st.download_button(
        label="⬇️ Télécharger en PDF (.pdf)",
        data=export_to_pdf(md_content),
        file_name=filename.replace(".md", ".pdf"),
        mime="application/pdf",
        use_container_width=True,
        key="export_report_pdf",
    )


# ── Sidebar ───────────────────────────────────────────────────────────────────

def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown("## 🔐 Cadrage Sécurité IA")
        st.divider()

        user = st.session_state.user
        st.markdown(f"**Utilisateur :** {user['username']}")
        st.markdown(f"**Rôle :** `{user['role']}`")

        if user["role"] == "ADMIN":
            if st.button("⚙️ Administration", use_container_width=True):
                st.session_state.current_view = "admin"
                st.rerun()

        st.divider()

        session = st.session_state.get("session")
        if not session:
            current_page = st.session_state.get("current_page", "home_dashboard")
            if current_page == "projects":
                if st.button("🏠 Tableau de bord", use_container_width=True):
                    st.session_state.current_page = "home_dashboard"
                    st.rerun()
            if st.button("🚪 Déconnexion", use_container_width=True):
                st.session_state.clear()
                st.rerun()
            return

        st.markdown("**📁 Projet en cours**")
        st.markdown(f"#### {session['project_name']}")
        if session.get("project_desc"):
            with st.expander("Description", expanded=False):
                st.markdown(session["project_desc"])

        st.divider()

        validated: set = st.session_state.get("validated_steps", set())
        steps_meta = llm_service.get_steps()
        n_validated = len(validated)
        st.markdown(f"**Progression : {n_validated} / {len(steps_meta)} étapes validées**")
        st.progress(n_validated / len(steps_meta))

        for s in steps_meta:
            n = s["number"]
            state = st.session_state.steps.get(n, {})
            is_unlocked = n == 1 or (n - 1) in validated
            if n in validated:
                badge = "✅"
            elif state.get("response"):
                badge = "🔄"
            elif is_unlocked:
                badge = "▶️"
            else:
                badge = "🔒"
            st.caption(f"{badge} {s['icon']} {s['short_title']}")

        st.divider()

        if st.button("🏠 Retour à l'accueil", use_container_width=True):
            for key in ("session", "_steps_session_id", "steps", "validated_steps"):
                st.session_state.pop(key, None)
            st.session_state.current_page = "home_dashboard"
            st.rerun()

        if st.button("🚪 Déconnexion", use_container_width=True):
            st.session_state.clear()
            st.rerun()


# ── Home Dashboard ────────────────────────────────────────────────────────────

def _criticality(steps_done: int) -> tuple:
    if steps_done >= 8:
        return ("Faible", _BADGE_STYLE["Faible"])
    elif steps_done >= 4:
        return ("Moyen", _BADGE_STYLE["Moyen"])
    return ("Élevé", _BADGE_STYLE["Élevé"])


def _render_project_row(session: dict) -> None:
    steps_done = session.get("steps_done", 0)
    current_step = session.get("current_step", 0)
    label, style = _criticality(steps_done)

    if session["status"] == "COMPLETED" or current_step == 10:
        step_label = "Étape 10 — Terminé ✅"
    elif current_step > 0:
        step_label = f"Étape {current_step} — En cours"
    else:
        step_label = "Étape 1 — À démarrer"

    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
        with c1:
            st.markdown(f"**{session['project_name']}**")
        with c2:
            st.caption(step_label)
        with c3:
            st.markdown(f'<span style="{style}">{label}</span>', unsafe_allow_html=True)
        with c4:
            if st.button("Ouvrir →", key=f"dash_open_{session['id']}", use_container_width=True):
                st.session_state.session = db_manager.get_session(session["id"])
                st.rerun()


def _render_home_dashboard() -> None:
    user = st.session_state.user

    st.markdown(_KPI_CSS, unsafe_allow_html=True)
    st.title("🏠 Tableau de bord")
    st.markdown(
        f"Bienvenue, **{user['username']}** &nbsp;·&nbsp; Rôle&nbsp;: `{user['role']}`",
        unsafe_allow_html=True,
    )
    st.divider()

    # ── KPI cards ────────────────────────────────────────────────────────────
    kpis = db_manager.get_dashboard_kpis()
    total_projects = kpis["in_progress"] + kpis["completed"]
    demo_mode = total_projects == 0

    if demo_mode:
        d = {"in_progress": 3, "completed": 12, "risks": 47, "requirements": 89}
        st.caption("_Mode démo — aucun projet en base. Données indicatives._")
    else:
        d = {
            "in_progress": kpis["in_progress"],
            "completed": kpis["completed"],
            "risks": kpis["risks"] * 8,
            "requirements": kpis["requirements"] * 12,
        }

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🔵 Projets en cours", d["in_progress"])
    c2.metric("✅ Projets terminés", d["completed"])
    c3.metric("⚠️ Risques identifiés", d["risks"])
    c4.metric("📋 Exigences générées", d["requirements"])

    st.divider()

    # ── Two-column section ───────────────────────────────────────────────────
    col_left, col_right = st.columns([3, 2], gap="large")

    with col_left:
        st.subheader("📁 Projets récents")
        sessions = db_manager.get_recent_sessions_with_progress(limit=8)

        if not sessions:
            for name, step_label, badge_key in [
                ("Système de Paiement e-Commerce", "Étape 7 — En cours", "Moyen"),
                ("Plateforme RH Cloud", "Étape 10 — Terminé ✅", "Faible"),
                ("API Open Banking", "Étape 3 — En cours", "Élevé"),
            ]:
                with st.container(border=True):
                    cd1, cd2, cd3 = st.columns([3, 2, 1])
                    with cd1:
                        st.markdown(f"**{name}**")
                    with cd2:
                        st.caption(step_label)
                    with cd3:
                        st.markdown(
                            f'<span style="{_BADGE_STYLE[badge_key]}">{badge_key}</span>',
                            unsafe_allow_html=True,
                        )
        else:
            for s in sessions:
                _render_project_row(s)

        st.write("")
        btn_label = "📁 Gérer les projets" if user["role"] != "VIEWER" else "📁 Voir tous les projets"
        if st.button(btn_label, type="primary", use_container_width=True, key="goto_projects"):
            st.session_state.current_page = "projects"
            st.rerun()

    with col_right:
        st.subheader("🛡️ Couverture des domaines")
        st.caption("Couverture estimée par domaine de sécurité")
        st.write("")

        domains = [
            ("Cyber & IT", 0.82),
            ("Opérations", 0.67),
            ("Développement", 0.74),
            ("Lutte contre la Fraude", 0.55),
            ("Intelligence Artificielle", 0.48),
        ]
        for name, value in domains:
            col_n, col_p = st.columns([4, 1])
            with col_n:
                st.markdown(f"**{name}**")
            with col_p:
                st.markdown(f"`{int(value * 100)}%`")
            st.progress(value)
            st.write("")


# ── Project selection ─────────────────────────────────────────────────────────

def _render_project_selection() -> None:
    st.title("📁 Gestion des projets")

    user = st.session_state.user
    is_viewer = user["role"] == "VIEWER"

    if is_viewer:
        col_list = st.container()
    else:
        col_new, col_list = st.columns([1, 1], gap="large")

    if not is_viewer:
        with col_new:
            st.subheader("Créer un nouveau projet")
            with st.form("new_project_form"):
                name = st.text_input("Nom du projet *")
                desc = st.text_area(
                    "Description *",
                    placeholder=(
                        "Décrivez le projet IT à analyser : type de système, périmètre fonctionnel, "
                        "technologies envisagées, contexte métier, utilisateurs cibles…"
                    ),
                    height=180,
                )
                submitted = st.form_submit_button(
                    "🚀 Créer le projet", type="primary", use_container_width=True
                )

            if submitted:
                if not name.strip() or not desc.strip():
                    st.error("Le nom et la description sont obligatoires.")
                else:
                    sid = db_manager.create_session(name.strip(), desc.strip(), user["id"])
                    st.session_state.session = db_manager.get_session(sid)
                    st.rerun()

    with col_list:
        st.subheader("Projets existants")
        sessions = db_manager.get_sessions(
            created_by=user["id"] if user["role"] == "CREATOR" else None
        )

        if not sessions:
            msg = (
                "Aucun projet disponible."
                if is_viewer
                else "Aucun projet. Créez votre premier projet ci-contre."
            )
            st.info(msg)
        else:
            for s in sessions:
                with st.container(border=True):
                    status_icon = {"DRAFT": "🟡", "IN_PROGRESS": "🔵", "COMPLETED": "🟢"}.get(
                        s["status"], "⚪"
                    )
                    st.markdown(f"**{s['project_name']}** {status_icon} `{s['status']}`")
                    st.caption(f"Créé le {s['created_at'][:10]}")
                    if s.get("project_desc"):
                        preview = s["project_desc"][:120]
                        st.markdown(preview + ("…" if len(s["project_desc"]) > 120 else ""))
                    if st.button("Ouvrir →", key=f"open_{s['id']}", use_container_width=True):
                        st.session_state.session = s
                        st.rerun()


# ── Step tab ──────────────────────────────────────────────────────────────────

def _render_step_tab(step_meta: dict, is_unlocked: bool) -> None:
    n = step_meta["number"]
    state: dict = st.session_state.steps[n]
    session: dict = st.session_state.session
    validated: set = st.session_state.validated_steps
    is_validated = n in validated
    is_viewer = st.session_state.user.get("role") == "VIEWER"

    if not is_unlocked:
        st.info(
            f"🔒 Cette étape est verrouillée. "
            f"Validez l'étape **{n - 1}** pour la débloquer.",
            icon="🔒",
        )
        return

    col_left, col_right = st.columns([6, 4], gap="medium")

    # ── Colonne gauche : analyse IA ───────────────────────────────────────────
    with col_left:
        title_col, badge_col = st.columns([5, 1])
        with title_col:
            st.subheader(f"{step_meta['icon']} {step_meta['title']}")
        with badge_col:
            if is_validated:
                st.markdown("✅ **Validée**")
            elif state["response"]:
                st.markdown("🔄 En cours")

        if state["response"] is None:
            if is_viewer:
                st.info("Aucune analyse générée pour cette étape.")
            else:
                st.info("Lancez la génération IA pour obtenir l'analyse de cette étape.")
                if st.button(
                    "🚀 Générer l'analyse",
                    key=f"gen_{n}",
                    type="primary",
                    use_container_width=True,
                ):
                    previous = _previous_responses(n)
                    with st.spinner("Analyse en cours, merci de patienter…"):
                        full_response: str = st.write_stream(
                            llm_service.stream_step_response(
                                n,
                                session["project_name"],
                                session["project_desc"],
                                previous,
                            )
                        )
                    sr_id = db_manager.upsert_step_response(
                        session["id"], n,
                        f"Étape {n} : {step_meta['title']}",
                        full_response,
                    )
                    db_manager.update_session_status(
                        session["id"], db_manager.SessionStatus.IN_PROGRESS
                    )
                    state["response"] = full_response
                    state["sr_id"] = sr_id
                    state["chat"] = [{"role": "assistant", "content": full_response}]
                    st.rerun()
        else:
            with st.container(border=True):
                st.markdown(state["response"])

            if not is_validated and not is_viewer:
                st.divider()
                btn_regen, _, btn_validate = st.columns([2, 1, 3])

                with btn_regen:
                    if st.button("🔄 Régénérer", key=f"regen_{n}", use_container_width=True):
                        previous = _previous_responses(n)
                        with st.spinner("Régénération en cours…"):
                            full_response = st.write_stream(
                                llm_service.stream_step_response(
                                    n,
                                    session["project_name"],
                                    session["project_desc"],
                                    previous,
                                )
                            )
                        sr_id = db_manager.upsert_step_response(
                            session["id"], n,
                            f"Étape {n} : {step_meta['title']}",
                            full_response,
                        )
                        if state["sr_id"]:
                            db_manager.clear_chat_history(state["sr_id"])
                        state["response"] = full_response
                        state["sr_id"] = sr_id
                        state["chat"] = [{"role": "assistant", "content": full_response}]
                        st.rerun()

                with btn_validate:
                    if st.button(
                        "✅ Valider l'étape",
                        key=f"validate_{n}",
                        type="primary",
                        use_container_width=True,
                    ):
                        st.session_state.validated_steps.add(n)
                        if n == 10:
                            db_manager.update_session_status(
                                session["id"], db_manager.SessionStatus.COMPLETED
                            )
                        st.rerun()

    # ── Colonne droite : chat ─────────────────────────────────────────────────
    with col_right:
        st.subheader("💬 Discussion")

        if state["response"] is None:
            st.caption("Générez d'abord l'analyse pour accéder au chat.")
        else:
            follow_ups = state["chat"][1:]

            chat_box = st.container(height=480, border=False)
            with chat_box:
                if not follow_ups:
                    st.caption(
                        "Posez une question, demandez une précision ou challengez "
                        "l'analyse pour la modifier à la volée."
                    )
                for msg in follow_ups:
                    with st.chat_message(msg["role"]):
                        st.markdown(msg["content"])

            if is_validated:
                st.caption("💡 Étape validée — discussion désactivée.")
            elif is_viewer:
                st.caption("💡 Mode lecture — discussion désactivée.")
            else:
                with st.form(key=f"chat_form_{n}", clear_on_submit=True):
                    user_input = st.text_area(
                        "Message",
                        key=f"chat_text_{n}",
                        height=80,
                        placeholder="Challengez ou affinez cette analyse…",
                        label_visibility="collapsed",
                    )
                    submitted = st.form_submit_button("Envoyer ↵", use_container_width=True)

                if submitted and user_input.strip():
                    user_input = user_input.strip()
                    previous = _previous_responses(n)
                    generator = llm_service.stream_chat_followup(
                        n,
                        session["project_name"],
                        session["project_desc"],
                        previous,
                        state["chat"],
                        user_input,
                    )

                    with chat_box:
                        with st.chat_message("user"):
                            st.markdown(user_input)
                        with st.chat_message("assistant"):
                            ai_response: str = st.write_stream(generator)

                    db_manager.add_chat_message(state["sr_id"], "user", user_input)
                    db_manager.add_chat_message(state["sr_id"], "assistant", ai_response)

                    state["chat"].append({"role": "user", "content": user_input})
                    state["chat"].append({"role": "assistant", "content": ai_response})
                    state["response"] = ai_response

                    st.rerun()

    # ── Export section (step 10 only) ─────────────────────────────────────────
    if n == 10:
        _render_export_section()


# ── Main entry point ──────────────────────────────────────────────────────────

def render_dashboard() -> None:
    if "session" in st.session_state:
        _init_step_states(st.session_state.session["id"])

    _render_sidebar()

    if "session" not in st.session_state:
        page = st.session_state.get("current_page", "home_dashboard")
        if page == "home_dashboard":
            _render_home_dashboard()
        else:
            _render_project_selection()
        return

    session = st.session_state.session

    validated: set = st.session_state.validated_steps
    steps_meta = llm_service.get_steps()

    tab_labels = [
        f"{s['icon']} {s['short_title']}" + (" ✅" if s["number"] in validated else "")
        for s in steps_meta
    ]

    tabs = st.tabs(tab_labels)

    for tab, step_meta in zip(tabs, steps_meta):
        n = step_meta["number"]
        is_unlocked = (n == 1) or ((n - 1) in validated)
        with tab:
            _render_step_tab(step_meta, is_unlocked)
