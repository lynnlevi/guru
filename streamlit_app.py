"""
Fun little chatbot for friends — Streamlit version.
- Control the system prompt (edit SYSTEM_PROMPT below)
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
from email.message import EmailMessage

import streamlit as st
import mlflow
from openai import OpenAI

# ---------------------------------------------------------------------------
# Configuration — the parts you'll actually want to tweak
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = "You are a witty, warm assistant for Lynn's friends. Keep it fun."
MODEL = "gpt-4o-mini"

# Secrets come from Streamlit's Secrets manager (st.secrets), never hardcoded.
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
SMTP_USER = st.secrets["SMTP_USER"]
SMTP_PASS = st.secrets["SMTP_PASS"]
LYNN_EMAIL = st.secrets["LYNN_EMAIL"]

# ---------------------------------------------------------------------------
# Observability: MLflow Tracing (one-line autolog)
# ---------------------------------------------------------------------------
if "MLFLOW_TRACKING_URI" in st.secrets:
    mlflow.set_tracking_uri(st.secrets["MLFLOW_TRACKING_URI"])
mlflow.set_experiment("friends-chatbot")
mlflow.openai.autolog()

client = OpenAI(api_key=OPENAI_API_KEY)


@mlflow.trace
def get_reply(history):
    """history is a list of {'role', 'content'} dicts including the latest user msg."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
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
# UI
# ---------------------------------------------------------------------------
LYNN_MESSAGE = (
    "Send your chat to Lynn so she can be nosy about you =)))))))) "
    "Just kidding, but honestly your record can help her refine the bot — "
    "and if she's really nosy, she'll contact you for more chit chat."
)

st.set_page_config(page_title="Lynn's Guru", page_icon="🔮")
st.title("Chat away 🔮")

# Streamlit reruns the whole script on every interaction, so we keep the
# conversation in session_state to persist it across reruns.
if "messages" not in st.session_state:
    st.session_state.messages = []

# Replay the conversation so far.
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# Chat input at the bottom.
if prompt := st.chat_input("Say something..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            reply = get_reply(st.session_state.messages)
        st.markdown(reply)
    st.session_state.messages.append({"role": "assistant", "content": reply})

# ---------------------------------------------------------------------------
# End-of-session export
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Done chatting?")
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
