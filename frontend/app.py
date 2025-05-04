import streamlit as st
from autogen_ext.models.openai import OpenAIChatCompletionClient
import sys 
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.progress_bar import progress_manager
import asyncio
from openai import OpenAI
import logging
import warnings
from autogen_agentchat.messages import TextMessage
import threading
import time

# --- Configuration ---
MAX_HISTORY_TURNS = 20  # Keep last 20 pairs (user+assistant) for context

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

client1 = OpenAIChatCompletionClient(
    model=MODEL_NAME,
    base_url=OPEN_AI_URL,
    api_key=OPEN_AI_KEY,
    model_info={
        "family": "gpt-4o",
        "json_output": True,
        "vision": True,
        "function_calling": True,
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
    st.session_state.messages = list(INITIAL_MESSAGE)  # Ensure it's a mutable list copy
    st.rerun()  # Force rerun after reset

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

# Initialize session state values
if "messages" not in st.session_state:
    st.session_state.messages = list(INITIAL_MESSAGE)  # Use list() to ensure mutable copy
if "progress_value" not in st.session_state:
    st.session_state.progress_value = 0
if "status_message" not in st.session_state:
    st.session_state.status_message = ""
if "is_waiting" not in st.session_state:
    st.session_state.is_waiting = False
if "last_progress_update" not in st.session_state:
    st.session_state.last_progress_update = 0

# --- Display Chat History ---
avatar_assistant = None
avatar_user = None
for message in st.session_state.messages:
    with st.chat_message(message["role"], avatar=avatar_assistant if message["role"] == "assistant" else avatar_user):
        st.markdown(message["content"])

# --- Handle User Input ---
prompt_disabled = st.session_state.is_waiting  # Disable input if waiting for a response
prompt = st.chat_input("Type your Query", disabled=prompt_disabled)

# --- Handle Progress Simulation ---
# This runs completely in the background without updating UI directly
def simulate_progress_in_background(stop_event):
    status_messages = {
        5: "🔄 Initializing...",
        15: "🔍 Searching for predictions...",
        40: "📊 Analyzing market data...",
        65: "💡 Generating insights...",
        85: "✍️ Crafting final response..."
    }
    
    # Store progress in thread-safe variables
    progress = {"value": 0, "message": "🔄 Initializing..."}
    
    # Update the session state in the main thread via this dictionary
    # We're not doing UI updates here!
    for i in range(101):
        if stop_event.is_set():
            break
            
        # Update our local progress state
        progress["value"] = i
        if i in status_messages:
            progress["message"] = status_messages[i]
            
        # Store progress in a thread-safe manner
        # Note: We're not updating UI here!
        st.session_state.progress_value = i
        st.session_state.status_message = progress["message"]
        st.session_state.last_progress_update = time.time()
            
        time.sleep(0.9)  # Adjust for total duration ~90s

# --- Handle User Input ---
if prompt:
    # --- Set waiting flag to True ---
    st.session_state.is_waiting = True
    
    # Reset progress values
    st.session_state.progress_value = 0
    st.session_state.status_message = "🔄 Initializing..."

    # 1. Append user message to FULL history (for display)
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar=avatar_user):
        st.markdown(prompt)

    # 2. Prepare the LIMITED history to send to the agent
    # Keep only the last N messages (user + assistant pairs)
    history_limit = MAX_HISTORY_TURNS * 2
    limited_history = st.session_state.messages[-history_limit:]

    # Convert the LIMITED history to the format expected by your agent
    text_messages_for_agent = [
        TextMessage(content=m["content"], source=m["role"])
        for m in limited_history
    ]

    # 3. Call the agent with the LIMITED history
    with st.chat_message("assistant", avatar=avatar_assistant):
        placeholder = st.empty()
        placeholder.markdown("Thinking...")
        status_container = st.container()

        with status_container:
            # Create a progress bar and status text - these will be updated by rerunning
            progress_bar = st.progress(0)
            status_text = st.empty()
            status_text.text("🔄 Initializing...")
            
            try:
                stop_event = threading.Event()
                
                # Start background thread - doesn't update UI directly
                progress_thread = threading.Thread(
                    target=simulate_progress_in_background,
                    args=(stop_event,)
                )
                progress_thread.daemon = True  # Make thread daemon so it exits when main thread exits
                progress_thread.start()
                
                # NEW APPROACH - poll for progress updates with rerun
                # Create a placeholder for a timestamp
                start_time = time.time()
                
                # Call agent for response
                response = run_async_function(run_prediction_analysis(text_messages_for_agent))
                
                # Signal the progress thread to stop
                stop_event.set()
                if progress_thread.is_alive():
                    progress_thread.join(timeout=1.0)  # Wait up to 1 second for thread to finish
                
                # Set final progress
                st.session_state.progress_value = 100
                st.session_state.status_message = "✅ Done!"
                progress_bar.progress(100)
                status_text.text("✅ Done!")
                
                # Small delay before showing response
                time.sleep(0.5)
                
                # Replace placeholder with actual response
                placeholder.markdown(response)
                
                # Clear the progress elements
                progress_bar.empty()
                status_text.empty()
                
                # Add response to messages
                st.session_state.messages.append({"role": "assistant", "content": response})
                
                # Reset waiting flag
                st.session_state.is_waiting = False

            except Exception as e:
                # Signal the progress thread to stop
                stop_event.set()
                if 'progress_thread' in locals() and progress_thread.is_alive():
                    progress_thread.join(timeout=1.0)
                
                st.error(f"An error occurred: {e}")
                response = "Sorry, I encountered an error." # Provide a fallback response
                placeholder.markdown(response)
                print("AN EXCEPTION OCCURRED", e)
                
                # Clear the progress elements
                progress_bar.empty()
                status_text.empty()
                
                # Add error response to messages
                st.session_state.messages.append({"role": "assistant", "content": response})
                
                # Reset waiting flag
                st.session_state.is_waiting = False

# Add auto-rerun for progress updates during waiting state
if st.session_state.is_waiting:
    # Check if we need to update the UI based on progress changes
    current_time = time.time()
    last_update = st.session_state.last_progress_update
    
    # Only rerun if there was a recent progress update (within last 2 seconds)
    if current_time - last_update < 2.0:
        time.sleep(0.1)  # Small delay to prevent too frequent reruns
        st.rerun()