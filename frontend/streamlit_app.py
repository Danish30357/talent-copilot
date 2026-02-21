"""
TalentCopilot — Streamlit Frontend

Full-featured chat UI with:
- Login / authentication
- Chat interface with message history
- Confirmation modal (approve/deny tool actions)
- CV file upload (two-step HITL: parse → confirm → save → confirm)
- GitHub URL ingestion (HITL-gated)
- Job status polling with auto-refresh
- Workspace snapshot (candidates + repositories)
"""


import time
import uuid
from datetime import datetime

import requests
import streamlit as st

import os

# ── Configuration ───────────────────────────────────────────
API_BASE = os.getenv("API_BASE", "http://localhost:8000")


# ── Session State Initialisation ────────────────────────────
def init_state():
    defaults = {
        "authenticated": False,
        "access_token": None,
        "refresh_token": None,
        "current_session_id": None,
        "messages": [],
        "pending_confirmation": None,   # HITL prompt shown in chat
        "active_jobs": [],              # job IDs being tracked
        "parse_job_completed": None,    # parse job result waiting for save confirmation
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_state()


# ── API Helpers ─────────────────────────────────────────────
def api_headers():
    return {"Authorization": f"Bearer {st.session_state.access_token}"}


def api_get(endpoint: str, params: dict = None):
    try:
        resp = requests.get(
            f"{API_BASE}{endpoint}",
            headers=api_headers(),
            params=params,
            timeout=30,
        )
        return resp
    except requests.ConnectionError:
        st.error("Cannot connect to backend. Is the server running?")
        return None


def api_post(endpoint: str, json_data: dict = None, files=None, params: dict = None):
    try:
        resp = requests.post(
            f"{API_BASE}{endpoint}",
            headers=api_headers() if not files else {k: v for k, v in api_headers().items()},
            json=json_data,
            files=files,
            params=params,
            timeout=60,
        )
        return resp
    except requests.ConnectionError:
        st.error("Cannot connect to backend. Is the server running?")
        return None


# ── Login Page ──────────────────────────────────────────────
def render_login():
    st.markdown(
        """
        <div style="text-align:center; padding:2rem 0;">
            <h1 style="color:#6C63FF;">🧠 TalentCopilot</h1>
            <p style="color:#888;">AI-Powered Recruiting Assistant</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("login_form"):
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            tenant = st.text_input("Tenant Name", placeholder="acme-corp")
            email = st.text_input("Email", placeholder="recruiter@acme.com")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("🔐 Sign In", use_container_width=True)

        if submitted:
            if not all([tenant, email, password]):
                st.error("All fields are required.")
                return

            resp = requests.post(
                f"{API_BASE}/auth/login",
                json={"tenant_name": tenant, "email": email, "password": password},
                timeout=10,
            )
            if resp and resp.status_code == 200:
                data = resp.json()
                st.session_state.authenticated = True
                st.session_state.access_token = data["access_token"]
                st.session_state.refresh_token = data["refresh_token"]
                st.rerun()
            else:
                detail = resp.json().get("detail", "Invalid credentials") if resp else "Server error"
                st.error(f"Login failed: {detail}")


# ── Sidebar ─────────────────────────────────────────────────
def render_sidebar():
    with st.sidebar:
        st.markdown("### 🧠 TalentCopilot")
        st.divider()

        # Sessions
        st.markdown("#### 💬 Sessions")
        if st.button("➕ New Chat", use_container_width=True):
            st.session_state.current_session_id = None
            st.session_state.messages = []
            st.rerun()

        resp = api_get("/chat/sessions")
        if resp and resp.status_code == 200:
            sessions = resp.json()
            for s in sessions[:20]:
                label = s["title"][:40]
                if st.button(f"📝 {label}", key=s["id"], use_container_width=True):
                    st.session_state.current_session_id = s["id"]
                    _load_history(s["id"])
                    st.rerun()

        st.divider()

        # ── GitHub Ingestion ────────────────────────────────
        st.markdown("#### 🔗 GitHub Ingestion")
        repo_url = st.text_input(
            "Repository URL",
            placeholder="https://github.com/owner/repo",
            key="github_url_input",
        )
        if st.button("📥 Request Ingestion", use_container_width=True):
            if not repo_url:
                st.warning("Enter a GitHub URL.")
            elif not st.session_state.current_session_id:
                st.warning("Start or open a chat session first.")
            else:
                resp = api_post(
                    "/ingest/github",
                    json_data={"repo_url": repo_url},
                    params={"session_id": st.session_state.current_session_id},
                )
                if resp and resp.status_code == 200:
                    data = resp.json()
                    st.session_state.pending_confirmation = {
                        "id": data["confirmation_id"],
                        "tool": "GitHub Ingestion",
                        "message": data["message"],
                        "payload": {"repo_url": repo_url},
                    }
                    st.success("Confirmation required! See the chat area.")
                    st.rerun()
                elif resp:
                    st.error(resp.json().get("detail", "Error requesting ingestion"))

        st.divider()

        # ── CV Upload (Step 1: Parse) ───────────────────────
        st.markdown("#### 📄 CV Upload")
        uploaded_file = st.file_uploader("Upload CV (PDF/DOCX)", type=["pdf", "docx"])
        if uploaded_file and st.button("📤 Upload & Request Parse", use_container_width=True):
            if not st.session_state.current_session_id:
                st.warning("Start or open a chat session first.")
            else:
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                resp = requests.post(
                    f"{API_BASE}/upload/cv",
                    headers=api_headers(),
                    files=files,
                    params={"session_id": st.session_state.current_session_id},
                    timeout=30,
                )
                if resp and resp.status_code == 200:
                    data = resp.json()
                    st.session_state.pending_confirmation = {
                        "id": data["confirmation_id"],
                        "tool": "CV Parsing",
                        "message": data["message"],
                        "payload": {"filename": uploaded_file.name},
                    }
                    st.success("Parsing confirmation required! See the chat area.")
                    st.rerun()
                elif resp:
                    st.error(resp.json().get("detail", "Upload error"))

        # ── CV Save Confirmation (Step 2, shown after parse completes) ──
        if st.session_state.parse_job_completed:
            _render_parse_complete_save_prompt()

        st.divider()

        # ── Active Jobs ─────────────────────────────────────
        st.markdown("#### ⚙️ Active Jobs")
        if st.session_state.active_jobs:
            still_active = []
            for job_id in st.session_state.active_jobs:
                completed = _render_job_status(job_id)
                if not completed:
                    still_active.append(job_id)
            # Atomically replace the list instead of mutating during iteration
            st.session_state.active_jobs = still_active
        else:
            st.caption("No active jobs.")

        st.divider()
        if st.button("🚪 Logout", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()


def _render_parse_complete_save_prompt():
    """Show save confirmation prompt after CV parse job completes."""
    parse_result = st.session_state.parse_job_completed
    st.markdown("---")
    st.success(f"✅ CV parsed: **{parse_result.get('full_name', 'Unknown')}**")
    st.markdown(f"Skills: {', '.join(parse_result.get('skills', [])[:5])}")
    st.markdown(f"Experience entries: {len(parse_result.get('experience', []))}")

    if st.button("💾 Request Save to Workspace", use_container_width=True):
        if not st.session_state.current_session_id:
            st.warning("Open a chat session first.")
        else:
            resp = api_post(
                "/upload/cv/save-confirmation",
                params={
                    "session_id": st.session_state.current_session_id,
                    "parse_job_id": parse_result["parse_job_id"],
                },
            )
            if resp and resp.status_code == 200:
                data = resp.json()
                st.session_state.pending_confirmation = {
                    "id": data["confirmation_id"],
                    "tool": "CV Save",
                    "message": data["message"],
                    "payload": data.get("candidate_preview", {}),
                }
                st.session_state.parse_job_completed = None
                st.success("Save confirmation required! See the chat area.")
                st.rerun()
            elif resp:
                st.error(resp.json().get("detail", "Error"))


def _render_job_status(job_id: str) -> bool:
    """Render job status badge. Returns True if job is terminal (completed/failed)."""
    resp = api_get(f"/jobs/{job_id}/status")
    if resp and resp.status_code == 200:
        job = resp.json()
        status = job["status"]
        status_emoji = {
            "queued": "⏳",
            "running": "🔄",
            "completed": "✅",
            "failed": "❌",
            "retrying": "🔁",
        }.get(status, "❓")
        st.markdown(f"{status_emoji} **{job['tool_name']}** — {status}")

        # If parse job completed, store result for save confirmation
        if status == "completed" and job["tool_name"] == "cv_parsing":
            result = job.get("result", {})
            if result.get("parsed_only") and not st.session_state.parse_job_completed:
                result["parse_job_id"] = job_id
                st.session_state.parse_job_completed = result

        return status in ("completed", "failed")
    return False


# ── Confirmation Modal ──────────────────────────────────────
def render_confirmation_modal():
    """Shows the HITL yes/no prompt in the main chat area."""
    conf = st.session_state.pending_confirmation
    if not conf:
        return

    st.markdown("---")
    with st.container():
        st.warning(f"**⚠️ Confirmation Required: {conf['tool']}**")
        st.info(conf.get("message", "Please confirm or deny this action."))

        if conf.get("payload"):
            st.json(conf["payload"])

        col1, col2, _ = st.columns([1, 1, 2])
        with col1:
            if st.button("✅ Yes / Approve", type="primary", use_container_width=True,
                          key="confirm_yes"):
                _handle_confirmation_decision(conf["id"], approved=True)
        with col2:
            if st.button("❌ No / Deny", type="secondary", use_container_width=True,
                          key="confirm_no"):
                _handle_confirmation_decision(conf["id"], approved=False)

    st.markdown("---")


def _handle_confirmation_decision(confirmation_id: str, approved: bool):
    resp = api_post(
        "/confirm",
        json_data={"confirmation_id": confirmation_id, "approved": approved},
    )
    if resp and resp.status_code == 200:
        data = resp.json()
        if approved:
            if data.get("job_id"):
                st.session_state.active_jobs.append(data["job_id"])
                st.success(f"✅ Approved! Job dispatched: `{data['job_id']}`")
            else:
                st.success("✅ Approved!")
        else:
            st.info("❌ Denied. No action taken.")
        st.session_state.pending_confirmation = None
        st.rerun()
    elif resp:
        st.error(resp.json().get("detail", "Error processing confirmation"))


# ── Chat Interface ──────────────────────────────────────────
def render_chat():
    st.markdown("### 💬 Chat")

    # Show HITL confirmation block if pending
    render_confirmation_modal()

    # Message history
    for msg in st.session_state.messages:
        role = msg.get("role", "user")
        with st.chat_message(role):
            st.markdown(msg["content"])

    # Input
    if prompt := st.chat_input("Ask TalentCopilot..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                resp = api_post(
                    "/chat",
                    json_data={
                        "session_id": st.session_state.current_session_id,
                        "content": prompt,
                    },
                )

            if resp and resp.status_code == 200:
                data = resp.json()
                st.session_state.current_session_id = data["session_id"]

                content = data["message"]["content"]
                st.markdown(content)
                st.session_state.messages.append({"role": "assistant", "content": content})

                # If HITL confirmation from LLM tool detection
                if data.get("confirmation_required"):
                    conf_details = data.get("confirmation_details", {})
                    tool_name = conf_details.get("tool_name", "Unknown Tool")
                    tool_payload = conf_details.get("tool_payload", {})

                    # Build HITL message based on tool type
                    if tool_name == "github_ingestion":
                        repo = tool_payload.get("repo_url", "the repository")
                        message = f"Would you like me to crawl this repository: {repo} ? (yes/no)"
                    elif tool_name == "cv_parsing":
                        fname = tool_payload.get("filename", "the CV")
                        message = f"Would you like me to parse this CV: '{fname}'? (yes/no)"
                    else:
                        message = f"Please confirm execution of: {tool_name}"

                    st.session_state.pending_confirmation = {
                        "id": data["confirmation_id"],
                        "tool": tool_name.replace("_", " ").title(),
                        "message": message,
                        "payload": tool_payload,
                    }
                    st.rerun()

            elif resp:
                error_msg = resp.json().get("detail", "Something went wrong.")
                st.error(error_msg)


def _load_history(session_id: str):
    resp = api_get(f"/chat/sessions/{session_id}/history")
    if resp and resp.status_code == 200:
        st.session_state.messages = [
            {"role": m["role"], "content": m["content"]}
            for m in resp.json()
        ]


# ── Workspace View ──────────────────────────────────────────
def render_workspace():
    st.markdown("### 🏢 Workspace")

    # Fetch combined snapshot
    resp = api_get("/workspace")
    if resp and resp.status_code == 200:
        snapshot = resp.json()
        stats = snapshot.get("stats", {})
        col1, col2, col3 = st.columns(3)
        col1.metric("Candidates", stats.get("total_candidates", 0))
        col2.metric("Repositories", stats.get("total_repos", 0))
        col3.metric("Sessions", stats.get("total_sessions", 0))
        st.divider()
    else:
        st.warning("Could not load workspace snapshot.")

    tab1, tab2, tab3 = st.tabs(["👤 Candidates", "📦 Repositories", "💬 Sessions"])

    with tab1:
        resp = api_get("/workspace/candidates")
        if resp and resp.status_code == 200:
            candidates = resp.json()
            if not candidates:
                st.info("No candidates saved yet. Upload and approve a CV to add one.")
            for c in candidates:
                with st.expander(f"👤 {c['full_name']} — {c.get('email', 'N/A')}"):
                    st.markdown(f"**Phone:** {c.get('phone', 'N/A')}")
                    skills = c.get("skills", [])
                    st.markdown(f"**Skills:** {', '.join(skills[:15]) if skills else 'N/A'}")
                    st.markdown(f"**Source:** {c.get('source_filename', 'N/A')}")
                    if c.get("experience"):
                        st.markdown("**Experience:**")
                        for exp in c["experience"]:
                            st.markdown(
                                f"- **{exp.get('title', '')}** at {exp.get('company', '')} "
                                f"({exp.get('duration', '')})"
                            )
                    if c.get("education"):
                        st.markdown("**Education:**")
                        for edu in c["education"]:
                            st.markdown(
                                f"- {edu.get('degree', '')} — {edu.get('institution', '')} "
                                f"({edu.get('year', '')})"
                            )
                    if c.get("projects"):
                        st.markdown("**Projects:**")
                        for p in c["projects"]:
                            techs = ", ".join(p.get("technologies", []))
                            st.markdown(f"- **{p.get('name', '')}**: {p.get('description', '')} [{techs}]")

    with tab2:
        resp = api_get("/workspace/repositories")
        if resp and resp.status_code == 200:
            repos = resp.json()
            if not repos:
                st.info("No repositories ingested yet. Provide a GitHub URL to add one.")
            for r in repos:
                with st.expander(f"📦 {r['repo_name']}"):
                    st.markdown(f"**URL:** [{r['repo_url']}]({r['repo_url']})")
                    st.markdown(f"**Description:** {r.get('description') or 'N/A'}")
                    langs = r.get("languages", [])
                    st.markdown(f"**Languages:** {', '.join(langs) if langs else 'N/A'}")
                    st.markdown(f"**Ingested:** {r.get('ingested_at', 'N/A')[:10]}")

    with tab3:
        resp = api_get("/workspace")
        if resp and resp.status_code == 200:
            sessions = resp.json().get("sessions", [])
            if not sessions:
                st.info("No sessions yet.")
            for s in sessions:
                with st.expander(f"💬 {s['title']} — {s['updated_at'][:10]}"):
                    if s.get("latest_summary"):
                        st.markdown("**Latest Summary:**")
                        st.write(s["latest_summary"])
                    else:
                        st.caption("No summary yet (conversation not long enough).")


# ── Main App ────────────────────────────────────────────────
def main():
    st.set_page_config(
        page_title="TalentCopilot",
        page_icon="🧠",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown(
        """
        <style>
        .stApp { background-color: #0e1117; }
        .stChatMessage { border-radius: 12px; padding: 0.5rem; }
        [data-testid="stSidebar"] { background-color: #161b22; }
        .stButton>button { border-radius: 8px; transition: all 0.2s ease; }
        .stButton>button:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(108, 99, 255, 0.3);
        }
        .stMetric { background: #1c2130; border-radius: 8px; padding: 0.5rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if not st.session_state.authenticated:
        render_login()
    else:
        render_sidebar()

        main_tab, workspace_tab = st.tabs(["💬 Chat", "🏢 Workspace"])

        with main_tab:
            render_chat()

        with workspace_tab:
            render_workspace()


if __name__ == "__main__":
    main()
