import os
import glob
import datetime

history_dir = os.path.expandvars(r"%APPDATA%\Cursor\User\History")

candidates = []

for root, dirs, files in os.walk(history_dir):
    for f in files:
        if f == "entries.json": continue
        path = os.path.join(root, f)
        try:
            with open(path, "r", encoding="utf-8") as file:
                content = file.read()
                if "def agregar_tecnico_a_grupo" in content and "snapshot_before = None" in content:
                    candidates.append((path, os.path.getmtime(path), len(content)))
        except:
            pass

candidates.sort(key=lambda x: x[1], reverse=True)

for c in candidates[:10]:
    dt = datetime.datetime.fromtimestamp(c[1])
    print(f"{dt} | Size: {c[2]} | Path: {c[0]}")
