import urllib.request
import json

try:
    req = urllib.request.Request('http://localhost:5000/api/eventos')
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        found = 0
        for ev in data:
            if 'test' in ev.get('summary', '').lower():
                print(f"HTTP ID: {ev.get('id')} | Cal: {ev.get('calendar_id')} | Title: {ev.get('summary')}")
                found += 1
        print(f"Total test events found via HTTP: {found}")
except Exception as e:
    print(f"Error: {e}")
