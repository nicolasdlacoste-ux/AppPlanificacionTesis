import json
import sys

log_path = r"C:\Users\ndiaz_akrimet\.gemini\antigravity\brain\3419deb7-012a-4d98-8d0b-93b386fcaa69\.system_generated\logs\transcript.jsonl"
patches = []

try:
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            if data.get("source") == "MODEL" and data.get("tool_calls"):
                for tc in data["tool_calls"]:
                    fn = tc.get("function", {})
                    name = fn.get("name", "")
                    args = fn.get("arguments", "{}")
                    try:
                        args_dict = json.loads(args)
                    except:
                        continue
                    
                    if "replace_file_content" in name or "write_to_file" in name:
                        tf = args_dict.get("TargetFile", "")
                        if "api_server.py" in tf:
                            patches.append({
                                "step": data.get("step_index"),
                                "name": name,
                                "args": args_dict
                            })
except Exception as e:
    print("Error reading:", e)

print(f"Found {len(patches)} patches for api_server.py")
for p in patches:
    print(f"Step: {p['step']}, Tool: {p['name']}")
