import streamlit as st
import requests

st.title("🤖 Invoice AI Chat")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# Chat input
if prompt := st.chat_input("Ask me about invoices..."):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Get agent response
    try:
        response = requests.post(
            "http://localhost:8001/agent/chat",
            json={"message": prompt}
        )
        agent_response = response.json()["response"]
        st.session_state.messages.append({"role": "assistant", "content": agent_response})
    except:
        st.error("Cannot connect to agent")

    st.rerun()