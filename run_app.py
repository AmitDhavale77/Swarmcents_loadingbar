import streamlit.web.cli 
import sys
import os
import subprocess

# Get the directory of the entry point script (the project root)
if getattr(sys, 'frozen', False):
    current_dir = sys._MEIPASS
else:
    current_dir = os.path.dirname(os.path.abspath(__file__))

print(f"Current Directory: {current_dir}")
# Add both the frontend and backend directories to the Python path
frontend_dir = os.path.join(current_dir, "frontend")
backend_dir = os.path.join(current_dir, "backend")
print(f"Frontend Directory: {frontend_dir}")
print(f"Backend Directory: {backend_dir}")
if frontend_dir not in sys.path:
    sys.path.append(frontend_dir)
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

# Define the path to your main Streamlit app file within the frontend folder
streamlit_app_path = os.path.join(frontend_dir, "app.py") # Pointing specifically to frontend/app.py
print(f"Streamlit App Path: {streamlit_app_path}")
if __name__ == "__main__":
    # Check if the app file exists (optional but good practice)
    print(f"Running Streamlit app from: {streamlit_app_path}")
    if not os.path.exists(streamlit_app_path):
         print(f"Error: Streamlit app file not found at {streamlit_app_path}")
         sys.exit(1)

    # Simulate running 'streamlit run frontend/app.py'
    sys.argv = ["streamlit", "run", streamlit_app_path]
    subprocess.run(["streamlit", "run", streamlit_app_path]) 
