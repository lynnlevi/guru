"""
Fun little chatbot for friends — Streamlit version.
- Two modes swap the system prompt: "Explore my goal" and "How to get there"
- Observability via MLflow Tracing (one-line autolog)
- Email the transcript to the user and/or to Lynn

Deploy on Streamlit Community Cloud (free). Put these in the app's
Secrets panel (NOT in the code / GitHub repo):

  OPENAI_API_KEY = "sk-..."
  SMTP_USER = "you@gmail.com"
  SMTP_PASS = "your-gmail-app-password"
  LYNN_EMAIL = "lynn@example.com"
  MLFLOW_TRACKING_URI = "https://..."   # optional, for persistent traces
"""

import smtplib
import ssl
import os
from email.message import EmailMessage
from pathlib import Path

import streamlit as st
import mlflow
from openai import OpenAI

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODEL = "gpt-4o-mini"

# Each mode's system prompt lives in its own text file so you can edit the
# wording without touching this code. Just edit the .txt files and push.
PROMPT_DIR = Path(__file__).parent
PROMPT_FILES = {"explore": "explore_prompt.txt", "howto": "howto_prompt.txt"}


def load_prompt(mode):
    """Read a mode's prompt from its text file (re-read on every rerun)."""
    try:
        text = (PROMPT_DIR / PROMPT_FILES[mode]).read_text(encoding="utf-8").strip()
        if text:
            return text
    except FileNotFoundError:
        pass
    return "You are a warm, witty assistant. (Prompt file missing — using fallback.)"


# Streamlit re-runs the whole script on each interaction, so these re-read the
# files each time — meaning local edits show up on the next interaction.
MODE_PROMPTS = {mode: load_prompt(mode) for mode in PROMPT_FILES}
MODE_LABELS = {"explore": "🌱 Explore my goal", "howto": "🛠️ Let's make a plan"}

# Secrets come from Streamlit's Secrets manager, never hardcoded.
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
SMTP_USER = st.secrets["SMTP_USER"]
SMTP_PASS = st.secrets["SMTP_PASS"]
LYNN_EMAIL = st.secrets["LYNN_EMAIL"]

# ---------------------------------------------------------------------------
# Observability: MLflow Tracing (one-line autolog)
# ---------------------------------------------------------------------------
try:
    tracking_uri = st.secrets.get("MLFLOW_TRACKING_URI")  # "databricks" for hosted
    if tracking_uri:
        # Databricks-managed MLflow authenticates via these env vars.
        if "DATABRICKS_HOST" in st.secrets:
            os.environ["DATABRICKS_HOST"] = st.secrets["DATABRICKS_HOST"]
        if "DATABRICKS_TOKEN" in st.secrets:
            os.environ["DATABRICKS_TOKEN"] = st.secrets["DATABRICKS_TOKEN"]
        mlflow.set_tracking_uri(tracking_uri)

    # On Databricks the experiment must be a workspace path (starts with "/").
    experiment = st.secrets.get("MLFLOW_EXPERIMENT")
    if not experiment:
        experiment = (
            "/Shared/friends-chatbot"
            if tracking_uri == "databricks"
            else "friends-chatbot"
        )
    mlflow.set_experiment(experiment)
    mlflow.openai.autolog()
except Exception as e:
    # Tracing is optional — a bad token or connection must never break the chat.
    print(f"MLflow setup skipped: {e}")

client = OpenAI(api_key=OPENAI_API_KEY)


@mlflow.trace
def get_reply(history, system_prompt):
    messages = [{"role": "system", "content": system_prompt}] + history
    resp = client.chat.completions.create(model=MODEL, messages=messages)
    return resp.choices[0].message.content


# ---------------------------------------------------------------------------
# Transcript + email helpers
# ---------------------------------------------------------------------------
def format_transcript(history):
    label = {"user": "You", "assistant": "Bot"}
    return "\n\n".join(
        f"{label.get(m['role'], m['role'])}: {m['content']}" for m in history
    )


def send_email(to_addr, subject, body):
    msg = EmailMessage()
    msg["From"] = SMTP_USER
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)


# ---------------------------------------------------------------------------
# Page + state
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Guru Lynn", page_icon="🔮", layout="wide")

# Fit the app to one screen: trim Streamlit's big default padding, and make the
# scrollable chat box size itself to the viewport so only the chat scrolls.
st.markdown(
    """
    <style>
      /* trim the large default top/bottom padding */
      .block-container { padding-top: 2.5rem; padding-bottom: 1rem; }
      /* the chat history box (the only bordered container) fills the screen */
      div[data-testid="stVerticalBlockBorderWrapper"] {
          height: calc(100vh - 210px) !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

GREETING = (
    "Need some clarity but don't wanna be judged by the real Lynn? "
    "Dump it here and leave with ammo to harass her later. 😏"
)


def fresh_chat():
    """Start a conversation with Guru Lynn's greeting already in place."""
    return [{"role": "assistant", "content": GREETING}]


if "messages" not in st.session_state:
    st.session_state.messages = fresh_chat()
if "mode" not in st.session_state:
    st.session_state.mode = "explore"
if "pending" not in st.session_state:
    st.session_state.pending = False

LYNN_MESSAGE = (
    "Send your chat to Lynn so she can be nosy about you =)))))))) "
    "Just kidding, but honestly your record can help her refine the bot — "
    "and if she's really nosy, she'll contact you for more chit chat."
)

# Left = chat, Right = menu + email panel
chat_col, right_col = st.columns([2, 1], gap="large")

# ---------------------------------------------------------------------------
# LEFT: the chat
# ---------------------------------------------------------------------------
with chat_col:
    st.title("Guru Lynn 🔮")
    st.caption("Your chatty friend reincarnated as an AI")
    st.caption(f"Mode: {MODE_LABELS[st.session_state.mode]}")

    if st.session_state.mode == "howto":
        # This mode isn't built yet — show a cheeky placeholder, no chat.
        st.info("Lynn hasn't figured this out yet muahahaha =)))")
    else:
        # The conversation lives in a fixed-height, scrollable box. Only this
        # area scrolls, so the menu on the right stays put while you scroll.
        chat_box = st.container(height=460)
        with chat_box:
            for m in st.session_state.messages:
                with st.chat_message(m["role"]):
                    st.markdown(m["content"])

            # If a reply is pending, generate it here — the user's message is
            # already shown above, and the bot's "Thinking..." bubble appears
            # in place, right where the reply will land.
            if st.session_state.pending:
                with st.chat_message("assistant"):
                    with st.spinner("Thinking..."):
                        reply = get_reply(
                            st.session_state.messages,
                            MODE_PROMPTS[st.session_state.mode],
                        )
                    st.markdown(reply)
                st.session_state.messages.append(
                    {"role": "assistant", "content": reply}
                )
                st.session_state.pending = False

        # Input sits below the chat box. On submit we show the user's message
        # and flag a pending reply, then rerun so the bubble renders in place.
        if prompt := st.chat_input("Say something..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            st.session_state.pending = True
            st.rerun()

# ---------------------------------------------------------------------------
# RIGHT: menu (part 1) + email chat (part 2)
# ---------------------------------------------------------------------------
with right_col:
    # --- Part 1: menu ---
    # Clicking a mode starts a fresh conversation in that mode.
    def switch_mode(mode):
        st.session_state.mode = mode
        st.session_state.messages = fresh_chat()
        st.session_state.pending = False

    st.subheader("Menu")
    if st.button(MODE_LABELS["explore"], use_container_width=True):
        switch_mode("explore")
        st.rerun()
    if st.button(MODE_LABELS["howto"], use_container_width=True):
        switch_mode("howto")
        st.rerun()

    st.divider()

    # --- Part 2: email the chat ---
    st.subheader("Done chatting?")
    st.caption("Grab a copy of your conversation.")
    user_email = st.text_input("Your email (optional)", placeholder="you@example.com")
    send_to_lynn = st.checkbox(LYNN_MESSAGE)

    if st.button("Email my transcript", type="primary"):
        history = st.session_state.messages
        if not history:
            st.warning("Nothing to export yet — say something first!")
        else:
            transcript = format_transcript(history)
            sent_to = []
            try:
                if user_email:
                    send_email(user_email, "Your chat transcript", transcript)
                    sent_to.append("you")
                if send_to_lynn:
                    send_email(LYNN_EMAIL, "A friend's chat transcript", transcript)
                    sent_to.append("Lynn")
            except Exception as e:
                st.error(f"Something went wrong sending the email: {e}")
            else:
                if sent_to:
                    st.success(f"Sent to {' and '.join(sent_to)}! Thanks for chatting =)")
                else:
                    st.info("Pick at least one option — your email or the box for Lynn. =)")
