import os
import ssl
import certifi

# ---------------------------------------------------------------------------
# SSL fix: trust system certificates (needed when behind corporate proxy/VPN)
# Append system keychain certs to certifi's bundle once at startup.
# ---------------------------------------------------------------------------
try:
    import subprocess, tempfile, pathlib
    _certifi_path = certifi.where()
    _existing = pathlib.Path(_certifi_path).read_text()
    _sys_certs = subprocess.run(
        ["security", "find-certificate", "-a", "-p", "/Library/Keychains/System.keychain"],
        capture_output=True, text=True
    ).stdout
    if _sys_certs and _sys_certs not in _existing:
        with open(_certifi_path, "a") as f:
            f.write(_sys_certs)
except Exception:
    pass  # non-macOS or no system certs — safe to ignore

import streamlit as st

st.set_page_config(
    page_title="CSV to Visualizations",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Provider / model configuration
# ---------------------------------------------------------------------------

PROVIDERS = ["Groq", "OpenAI", "Anthropic"]

PROVIDER_MODELS = {
    "Groq": [
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "qwen/qwen3.8-27b",
        "allam-2-7b",
    ],
    "OpenAI": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-3.5-turbo",
    ],
    "Anthropic": [
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
    ],
}

PROVIDER_ENV_VAR = {
    "Groq":      "GROQ_API_KEY",
    "OpenAI":    "OPENAI_API_KEY",
    "Anthropic": "ANTHROPIC_API_KEY",
}

PROVIDER_SECRET_KEY = {
    "Groq":      "groq_api_key",
    "OpenAI":    "openai_api_key",
    "Anthropic": "anthropic_api_key",
}


def _default_key(provider: str) -> str:
    """
    Return the owner-supplied default API key for a provider.
    Priority: st.secrets[defaults] → environment variable → empty string.
    """
    # 1. st.secrets (set by app owner in .streamlit/secrets.toml or Streamlit Cloud UI)
    try:
        key = st.secrets["defaults"][PROVIDER_SECRET_KEY[provider]]
        if key:
            return key
    except (KeyError, FileNotFoundError):
        pass
    # 2. environment variable
    return os.environ.get(PROVIDER_ENV_VAR[provider], "")


# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------

defaults = {
    "provider":    "Groq",
    "model":       "openai/gpt-oss-120b",
    "api_key":     _default_key("Groq"),
    "using_default_key": True,   # tracks whether user entered a custom key
    # Per-provider stored user-supplied overrides
    "custom_key_Groq":      "",
    "custom_key_OpenAI":    "",
    "custom_key_Anthropic": "",
    # Pipeline data
    "uploaded_dataframes": {},
    "validation_issues": [],
    "upload_complete": False,
    "raw_schema": {},
    "confirmed_schema": {},
    "schema_ddl": "",
    "db_connection": None,
    "schema_confirmed": False,
    "last_question": "",
    "last_generated_sql": "",
    "last_query_result": None,
    "viz_specs": [],
    "viz_figures": [],
    "dashboard_data": {},
    "dashboard_figures": [],
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("📊 CSV to Viz")
    st.divider()

    st.subheader("AI Configuration")

    # Provider selector
    provider_idx = PROVIDERS.index(st.session_state["provider"])
    provider = st.selectbox("Provider", PROVIDERS, index=provider_idx)

    if provider != st.session_state["provider"]:
        st.session_state["provider"] = provider
        st.session_state["model"] = PROVIDER_MODELS[provider][0]
        # Restore: use custom key if stored, else fall back to owner default
        custom = st.session_state.get(f"custom_key_{provider}", "")
        st.session_state["api_key"] = custom if custom else _default_key(provider)
        st.session_state["using_default_key"] = not bool(custom)

    # Model selector
    models = PROVIDER_MODELS[provider]
    cur_model = st.session_state["model"]
    model_idx = models.index(cur_model) if cur_model in models else 0
    model = st.selectbox("Model", models, index=model_idx)
    if model != st.session_state["model"]:
        st.session_state["model"] = model

    st.divider()

    # API Key section
    st.subheader("API Key")
    default_key = _default_key(provider)
    has_default = bool(default_key)

    if has_default:
        use_own = st.toggle(
            "Use my own API key",
            value=not st.session_state.get("using_default_key", True),
        )
        st.session_state["using_default_key"] = not use_own
    else:
        use_own = True
        st.session_state["using_default_key"] = False

    if use_own or not has_default:
        stored_custom = st.session_state.get(f"custom_key_{provider}", "")
        user_key = st.text_input(
            "Your API Key",
            value=stored_custom,
            type="password",
            placeholder=f"Enter your {provider} API key...",
        )
        if user_key != stored_custom:
            st.session_state[f"custom_key_{provider}"] = user_key
        active_key = user_key if user_key else default_key
    else:
        active_key = default_key
        st.info("Using app's default API key.", icon="🔑")

    st.session_state["api_key"] = active_key

    # Status + Test button
    if active_key:
        source_label = "app key" if (not use_own and has_default) else "your key"
        st.success(f"Key set ({source_label})", icon="✅")

        if st.button("🔌 Test Connection", use_container_width=True):
            with st.spinner(f"Testing {provider} connection..."):
                try:
                    from utils.llm import _chat_completion
                    result = _chat_completion(
                        "Reply with only: OK",
                        active_key,
                        st.session_state["model"],
                        provider,
                        max_tokens=5,
                    )
                    st.success(f"Connection OK — model responded: `{result.strip()}`")
                except Exception as exc:
                    st.error(f"**{type(exc).__name__}:** {exc}")
    else:
        st.warning(
            f"No API key. Enter your {provider} key above.",
            icon="⚠️",
        )

    st.divider()

    # Pipeline status
    st.subheader("Pipeline Status")
    steps = [
        ("Upload",    "upload_complete"),
        ("Schema",    "schema_confirmed"),
        ("Query",     "last_generated_sql"),
        ("Visualize", "viz_specs"),
        ("Dashboard", "dashboard_data"),
    ]
    for label, key in steps:
        done = bool(st.session_state.get(key))
        st.write(f"{'✅' if done else '⬜'} {label}")

# ---------------------------------------------------------------------------
# Home page
# ---------------------------------------------------------------------------

st.title("CSV to Visualizations")
st.write(
    "Upload tabular data files and transform them into interactive visualizations "
    "and dashboards powered by AI."
)

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.info("**Step 1**\nUpload Files", icon="📁")
with col2:
    st.info("**Step 2**\nReview Schema", icon="🗂️")
with col3:
    st.info("**Step 3**\nQuery Data", icon="🔍")
with col4:
    st.info("**Step 4**\nVisualize", icon="📈")
with col5:
    st.info("**Step 5**\nDashboard", icon="🎨")

st.divider()

if not st.session_state["api_key"]:
    st.warning(
        "No API key configured. Enter your key in the sidebar to get started.",
        icon="⚠️",
    )

st.page_link("pages/01_upload.py", label="→ Start: Upload Files", icon="📁")
