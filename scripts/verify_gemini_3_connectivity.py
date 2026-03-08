from google import genai
import os

API_KEY = "AIzaSyCHi5SHHDyUM-1bEvmDcCHy9t8tUV91qzg"

def test_connection():
    # Only test flash now
    models = ["gemini-3-flash-preview"]
    
    print(f"Testing connectivity for models: {models}")
    
    client = genai.Client(api_key=API_KEY, http_options={'api_version': 'v1beta'})
    
    for model_name in models:
        print(f"\n--- Testing {model_name} ---")
        try:
            response = client.models.generate_content(
                model=model_name,
                contents="Hello, check connection."
            )
            print(f"✅ Connection Successful for {model_name}!")
            print(f"Response: {response.text}")
        except Exception as e:
            print(f"❌ Connection Failed for {model_name}")
            print(f"Error: {e}")

if __name__ == "__main__":
    test_connection()
