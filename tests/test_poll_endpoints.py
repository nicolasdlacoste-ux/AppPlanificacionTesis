"""Test HTTP de los endpoints de polling."""
import requests, json

BASE = "http://localhost:8000"

tests = []

# GET /api/poll/status
r = requests.get(f"{BASE}/api/poll/status")
tests.append(("GET /api/poll/status", r.status_code == 200 and "polling_active" in r.json()))
print(f"[{'OK' if tests[-1][1] else 'FAIL'}] GET /api/poll/status → {r.status_code}")
print(f"      {json.dumps(r.json(), indent=6)}")

# GET /api/poll/review_queue
r = requests.get(f"{BASE}/api/poll/review_queue")
tests.append(("GET /api/poll/review_queue", r.status_code == 200))
print(f"[{'OK' if tests[-1][1] else 'FAIL'}] GET /api/poll/review_queue → {r.status_code}, items={len(r.json())}")

# GET /api/poll/log
r = requests.get(f"{BASE}/api/poll/log?limit=5")
tests.append(("GET /api/poll/log", r.status_code == 200))
print(f"[{'OK' if tests[-1][1] else 'FAIL'}] GET /api/poll/log → {r.status_code}, entries={len(r.json())}")
if r.json():
    first = r.json()[0]
    print(f"      latest: {first['event_type']} @ {first['timestamp']}")

# POST /api/poll/stop (seguro aunque no esté activo)
r = requests.post(f"{BASE}/api/poll/stop")
tests.append(("POST /api/poll/stop", r.status_code == 200))
print(f"[{'OK' if tests[-1][1] else 'FAIL'}] POST /api/poll/stop → {r.status_code} {r.json()}")

print()
passed = sum(1 for _, ok in tests if ok)
print(f"{'='*50}")
print(f"Resultado: {passed}/{len(tests)} endpoints OK")
print(f"{'='*50}")
