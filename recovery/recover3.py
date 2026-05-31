import os
import datetime

history_dir = os.path.expandvars(r"%APPDATA%\Cursor\User\History")

candidates = []

for root, dirs, files in os.walk(history_dir):
    for f in files:
        if f == "entries.json": continue
        path = os.path.join(root, f)
        try:
            size = os.path.getsize(path)
            if size > 100000:  # api_server.py was ~140KB
                with open(path, "r", encoding="utf-8") as file:
                    content = file.read()
                    if "def agregar_tecnico_a_grupo" in content and "def mover_grupo" in content:
                        candidates.append((path, os.path.getmtime(path), size))
        except:
            pass

candidates.sort(key=lambda x: x[1], reverse=True)

for c in candidates[:10]:
    dt = datetime.datetime.fromtimestamp(c[1])
    print(f"{dt} | Size: {c[2]} | Path: {c[0]}")
    # Save the most recent one to a temp file
    if c == candidates[0]:
        with open("recovered_api_server.py", "w", encoding="utf-8") as out:
            with open(c[0], "r", encoding="utf-8") as inp:
                out.write(inp.read())
        print("-> Saved the most recent as recovered_api_server.py")
