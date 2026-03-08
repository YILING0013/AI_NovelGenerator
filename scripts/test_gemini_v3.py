
from google import genai
from google.genai import types
import os

# User provided credentials
API_KEY = "AIzaSyCHi5SHHDyUM-1bEvmDcCHy9t8tUV91qzg"
MODEL_NAME = "gemini-2.0-flash-exp" # Trying a known working 2.0 model first or use user's 3.0 if valid
# User request specifically mentioned gemini-3-pro-preview, let's try that.
# But 3.0 might not be public yet? The user said "gemini3.0pro". 
# Actually, the user wrote:
# MODEL: gemini-3-pro-preview
# Let's try exactly what they gave.

MODEL_NAME = "gemini-2.0-flash-exp" # Let's try 2.0 Flash first as a sanity check if 3.0 fails, or just try 3.0.
# Wait, user *said* "gemini-3-pro-preview". I should try that.
MODEL_NAME = "gemini-2.0-flash-exp" 

# Actually I'll try the specific one user asked for, and if it fails, I'll print the error.
CHOSEN_MODEL = "gemini-2.0-flash-exp" # Default to checking connection with a known model first?
# No, trust the user.
CHOSEN_MODEL = "gemini-3-pro-preview" 

def test_connection():
    print(f"Testing connection with model: {CHOSEN_MODEL}")
    try:
        client = genai.Client(api_key=API_KEY, http_options={'api_version': 'v1beta'})
        
        response = client.models.generate_content(
            model=CHOSEN_MODEL,
            contents="Hello, are you online?"
        )
        print("Connection Successful!")
        print("Response:", response.text)
        return True
    except Exception as e:
        print("Connection Failed:", e)
        return False

if __name__ == "__main__":
    test_connection()
