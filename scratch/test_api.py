import urllib.request
import json

def test_endpoint(url):
    print(f"Testing {url}...")
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode())
            print(f"Success! Received {len(data)} items.")
            if len(data) > 0:
                print(f"Sample: {data[0]}")
    except Exception as e:
        print(f"Error: {e}")

test_endpoint("http://127.0.0.1:8000/api/tecnicos")
test_endpoint("http://127.0.0.1:8000/api/eventos")
