import streamlit as st
from autogen_ext.models.openai import OpenAIChatCompletionClient
import os
import os
import asyncio
from openai import OpenAI
import warnings
from autogen_agentchat.messages import TextMessage
import sys 
import time
from threading import Thread, Event
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

# --- Configuration ---
MAX_HISTORY_TURNS = 20 # Keep last 5 pairs (user+assistant) for context

# Add the project root to Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Add this near the top of your script
warnings.filterwarnings("ignore", message=r"Model .* is not found. The cost will be 0.*")

# --- Streamlit App ---
st.set_page_config(page_title="SwarmCents Chat", page_icon="💰", layout="wide")
st.markdown("""
    <h1 style='text-align: center; color: gold;'>
        💰 SwarmCents Chat
    </h1>
    <p style='text-align: center; color: lightgray; font-size: 16px;'>
        Your AI guide to Polymarket predictions 📊🔍
    </p>
""", unsafe_allow_html=True)

# API Keys
OPEN_AI_KEY = os.environ.get("OPEN_AI_KEY")
MODEL_NAME = os.environ.get("MODEL_NAME", "gpt-4o-2024-08-06")
OPEN_AI_URL = os.environ.get("OPEN_AI_URL", "https://api.openai.com/v1")

# Sidebar
with st.sidebar:
    st.markdown("## 🛠️ How to use")
    st.markdown("1. Choose your Model 🤖\n"
                "2. Ask a question through natural language. 💬")

    st.markdown("---")
    st.markdown("### ⚙️ API Configuration")
    selected_model = st.selectbox("Choose Model", ["gpt-4o", "grok 2", "o3-mini"], index=0)
    
    st.markdown("---")
    st.markdown("### ℹ️ About")
    st.markdown("💰 <b>SwarmCents Chat</b> helps you explore and analyze predictions on Polymarket using AI.", unsafe_allow_html=True)

# Check for valid API Key & Model
if not OPEN_AI_KEY or not selected_model:
    st.warning("You must provide a valid OpenAI API key and select a model!", icon="⚠️")
    st.stop()

client = OpenAI(
    base_url=OPEN_AI_URL,
    api_key=OPEN_AI_KEY
)

client1  = OpenAIChatCompletionClient(
    model = MODEL_NAME,
    base_url=OPEN_AI_URL,
    api_key=OPEN_AI_KEY,
    model_info={
        "family": "gpt-4o",
        "json_output": True,
        "vision": True,  # This can be kept
        "function_calling": True,  # This can be kept
    }
)

from backend.Agent import run_prediction_analysis

# --- Initialize Chat History in Session State ---
INITIAL_MESSAGE = [
    {
        "role": "assistant",
        "content": 
"""Hey there, I'm SwarmCents Chat! I'm here to help you analyze predictions about Polymarket topics made on Twitter.
Please select one of these specific options:
1. Find predictions on [specific topic], also give account names of users who made them. 
2. Build profile for [@predictor_handle]. Show me their all prediction history and analysis.
3. Verify prediction: "[exact prediction text]"
4. Calculate the credibility score for [@predictor_handle].
Which option would you like to proceed with?""",
    },
]

# Add a reset button
if st.sidebar.button("🔄 Reset Chat"):
    for key in st.session_state.keys():
        del st.session_state[key]
    # Re-initialize after deleting
    st.session_state.messages = list(INITIAL_MESSAGE) # Ensure it's a mutable list copy
    st.rerun() # Force rerun after reset


# Display the chat messages
if "messages" not in st.session_state:
    st.session_state.messages = INITIAL_MESSAGE

def run_async_function(coro):
    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(coro)
        return loop.run_until_complete(task)
    except RuntimeError:
        # No running loop, so create one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            # Clean up any lingering async generators
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

# Initialize chat messages in session state    
if "messages" not in st.session_state:
    st.session_state.messages = list(INITIAL_MESSAGE) # Use list() to ensure mutable copy

# --- Display Chat History ---
avatar_assistant = None
avatar_user = None
for message in st.session_state.messages:
    with st.chat_message(message["role"], avatar=avatar_assistant if message["role"] == "assistant" else avatar_user):
        st.markdown(message["content"])

# --- Add a flag in session state to prevent double input ---
if "is_waiting" not in st.session_state:
    st.session_state.is_waiting = False

# --- Handle User Input ---
prompt_disabled = st.session_state.is_waiting  # Disable input if waiting for a response
prompt = st.chat_input("Type your Query", disabled=prompt_disabled)

response_holder = {"text": "Thinking..."}

def progress_thread_func(progress_bar, status_text, stop_event):
    # ctx = get_script_run_ctx()
    # add_script_run_ctx(Thread.current_thread(), ctx)

    for i in range(101):
        if stop_event.is_set():
            break  # Stop the thread gracefully when event is set
        if i == 10:
            progress_bar.progress(10)
            status_text.text("🔍 Searching for relevant data...")
        elif i == 30:
            progress_bar.progress(30)
            status_text.text("📊 Analyzing information...")
        elif i == 60:
            progress_bar.progress(60)
            status_text.text("💭 Formulating response...")
        elif i >= 90:
            progress_bar.progress(90)
            status_text.text("✏️ Finalizing answer...")
        time.sleep(0.3)

def agent_thread_func(history, holder):
    try:
        response = run_async_function(run_prediction_analysis(history))
    except Exception as e:
        print("AN EXCEPTION OCCURRED", e)
        response = "Sorry, I encountered an error."
    holder["text"] = response


# --- Handle User Input ---
if prompt:
    # --- Set waiting flag to True ---
    st.session_state.is_waiting = True

    # 1. Append user message to FULL history (for display)
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar=avatar_user):
        st.markdown(prompt)

    # 2. Prepare the LIMITED history to send to the agent
    # Keep only the last N messages (user + assistant pairs)
    # Multiply by 2 for pairs, add 1 if you always want the initial system message if any
    history_limit = MAX_HISTORY_TURNS * 2
    limited_history = st.session_state.messages[-history_limit:]

    # Convert the LIMITED history to the format expected by your agent
    text_messages_for_agent = [
        # Assuming TextMessage takes content and source)
        TextMessage(content=m["content"], source=m["role"]) # Adjust 'role' if it expects 'source' etc.
        for m in limited_history
    ]

    # 3. Call the agent with the LIMITED history
    with st.chat_message("assistant", avatar=avatar_assistant):
        placeholder = st.empty()
        placeholder.markdown("Thinking...")

        status_container = st.container()
        with status_container:
            progress_bar = st.progress(0)
            status_text = st.empty()
            status_text.text("🔄 Initializing...")
            try:

                # Create an event to signal when agent is done
                stop_event = Event()

                # Start progress bar thread
                progress_thread = Thread(target=progress_thread_func, args=(progress_bar, status_text, stop_event))
                add_script_run_ctx(progress_thread, get_script_run_ctx())
                progress_thread.start()


                # Start agent processing thread
                agent_thread = Thread(target=agent_thread_func, args=(text_messages_for_agent, response_holder))
                agent_thread.start()

                # Wait for agent response
                agent_thread.join()

                # Signal the progress thread to stop
                stop_event.set()

                progress_thread.join()


                # Ensure progress bar is at 100% when done
                # time.sleep(0.5)  # Small delay to ensure UI updates
                progress_bar.progress(100)
                status_text.text("✅ Done!")

                # Small delay before removing progress elements
                time.sleep(0.5)
                # Pass the truncated message list to your backend
                # response = run_async_function(run_prediction_analysis(text_messages_for_agent))
                # placeholder.markdown(response)
                placeholder.markdown(response_holder["text"])
                # Clear the progress elements
                progress_bar.empty()
                status_text.empty()
            except Exception as e:
                st.error(f"An error occurred: {e}")
                response = "Sorry, I encountered an error." # Provide a fallback response
                placeholder.markdown(response)
                print("AN EXCEPTION OCCURED", e)
                #st.session_state.clear()
                #st.rerun()
                # Clear the progress elements
                progress_bar.empty()
                status_text.empty()


    # 4. Append assistant response to FULL history (for display)
    st.session_state.messages.append({"role": "assistant", "content": response_holder["text"]})

    # 5. Optional: Rerun to ensure the latest message is displayed immediately if needed
    # st.rerun() # Usually not needed as Streamlit handles updates, but can force it.

    # --- Reset waiting flag ---
    st.session_state.is_waiting = False