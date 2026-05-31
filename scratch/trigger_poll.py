import requests
import time

try:
    print("Triggering poll...")
    resp = requests.post("http://localhost:8000/api/poll/trigger", timeout=10)
    print(f"Status: {resp.status_code}")
    print(f"Body: {resp.text}")
except Exception as e:
    print(f"Error: {e}")
