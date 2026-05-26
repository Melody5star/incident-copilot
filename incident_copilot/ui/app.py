"""Streamlit demo frontend for Incident Copilot."""

import json
import os
import time

import httpx
import streamlit as st

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8080")

st.set_page_config(
    page_title="Incident Copilot",
    page_icon="🚨",
    layout="wide",
)

st.title("🚨 Incident Copilot")
st.caption("Autonomous DevOps incident triage · Powered by Gemini + Elastic + GitLab")

with st.sidebar:
    st.header("Quick Actions")
    if st.button("🔍 Scan for active incidents", use_container_width=True):
        st.session_state["prefill"] = "Are there any active production incidents right now? Triage all affected services."
    if st.button("📋 Triage checkout service", use_container_width=True):
        st.session_state["prefill"] = "The checkout service has been throwing errors for the last 10 minutes. Please investigate, find the root cause, and file a GitLab issue."
    if st.button("🔎 Search recent commits", use_container_width=True):
        st.session_state["prefill"] = "Search for any commits in the last 24 hours that touched payment-related files. Identify any suspicious changes."

    st.divider()
    st.subheader("How it works")
    st.markdown("""
1. **Detect** — Queries Elastic for error spikes
2. **Investigate** — Pulls recent error logs
3. **Hypothesize** — Gemini reasons over evidence
4. **Trace** — Finds the offending GitLab commit
5. **Act** — Files a structured incident issue
    """)

if "messages" not in st.session_state:
    st.session_state["messages"] = []

for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

prefill = st.session_state.pop("prefill", "")
user_input = st.chat_input("Describe the incident or ask the agent to investigate...") or prefill

if user_input:
    st.session_state["messages"].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        tool_placeholder = st.empty()
        response_placeholder = st.empty()

        tool_calls: list[str] = []
        full_response = ""

        with st.spinner("Agent is investigating..."):
            try:
                with httpx.stream(
                    "POST",
                    f"{API_BASE}/triage",
                    json={"message": user_input},
                    timeout=120,
                ) as stream:
                    for line in stream.iter_lines():
                        if line.startswith("data: "):
                            chunk = line[6:]
                            if chunk.startswith("[Tool:"):
                                tool_name = chunk[7:-1]
                                tool_calls.append(tool_name)
                                tool_placeholder.info(f"Tools used: {', '.join(tool_calls)}")
                            else:
                                full_response += chunk
                                response_placeholder.markdown(full_response + "▌")

                response_placeholder.markdown(full_response)
                if tool_calls:
                    tool_placeholder.success(f"**{len(tool_calls)} tool calls:** {', '.join(tool_calls)}")

            except httpx.ConnectError:
                full_response = "Cannot reach the agent API. Make sure the backend is running: `uvicorn api.main:app --port 8080`"
                response_placeholder.error(full_response)

    st.session_state["messages"].append({"role": "assistant", "content": full_response})
