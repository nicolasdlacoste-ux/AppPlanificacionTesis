import urllib.request
import json

url = "http://127.0.0.1:8000/api/eventos"
with urllib.request.urlopen(url) as response:
    data = json.loads(response.read().decode())
    if data:
        ev = data[0]
        print(json.dumps(ev, indent=2))
        print("\nTipos de datos:")
        for k, v in ev.items():
            print(f"{k}: {type(v).__name__}")
        if "extendedProperties" in ev:
            print("\nExtendedProperties content:")
            print(json.dumps(ev["extendedProperties"], indent=2))
