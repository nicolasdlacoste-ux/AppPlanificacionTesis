import urllib.request
import json
try:
    req = urllib.request.Request('http://127.0.0.1:8000/api/eventos')
    with urllib.request.urlopen(req) as response:
        data = response.read()
        parsed = json.loads(data)
        print(type(parsed))
        if isinstance(parsed, list):
            print(f"List length: {len(parsed)}")
        else:
            print(parsed)
except Exception as e:
    print("Error:", e)
