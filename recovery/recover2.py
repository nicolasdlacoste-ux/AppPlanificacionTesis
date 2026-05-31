import json
import re

log_path = r"C:\Users\ndiaz_akrimet\.gemini\antigravity\brain\c5ea0f7a-8894-4861-8c27-260c3a613bd9\.system_generated\logs\transcript.jsonl"
lines_dict = {}

try:
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            if data.get("source") == "MODEL" and data.get("type") == "VIEW_FILE":
                # Wait, tool responses are from source SYSTEM and type TOOL_RESPONSE?
                pass
            if data.get("source") == "SYSTEM" and data.get("type") == "TOOL_RESPONSE":
                content = data.get("content", "")
                if "api_server.py" in content and "Showing lines" in content:
                    # Parse the lines
                    # The format is `<line_number>: <original_line>`
                    parts = content.split("The following code has been modified")
                    if len(parts) > 1:
                        code_part = parts[1].split("\nThe above content does NOT show")[0]
                        for c_line in code_part.split("\n"):
                            match = re.match(r"^(\d+):\s(.*)$", c_line)
                            if match:
                                num = int(match.group(1))
                                lines_dict[num] = match.group(2)

except Exception as e:
    print("Error:", e)

# Also check the current conversation's transcript for view_file
log_path2 = r"C:\Users\ndiaz_akrimet\.gemini\antigravity\brain\3419deb7-012a-4d98-8d0b-93b386fcaa69\.system_generated\logs\transcript.jsonl"
try:
    with open(log_path2, "r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            if data.get("source") == "SYSTEM" and data.get("type") == "TOOL_RESPONSE":
                content = data.get("content", "")
                if "api_server.py" in content and "Showing lines" in content:
                    parts = content.split("The following code has been modified")
                    if len(parts) > 1:
                        code_part = parts[1].split("\nThe above content does NOT show")[0]
                        for c_line in code_part.split("\n"):
                            match = re.match(r"^(\d+):\s(.*)$", c_line)
                            if match:
                                num = int(match.group(1))
                                # Only add if missing, or overwrite?
                                # Older views have the base file, newer views have patched lines.
                                lines_dict[num] = match.group(2)
except Exception as e:
    pass

print(f"Recovered {len(lines_dict)} unique lines.")
with open("reconstructed_api_server.py", "w", encoding="utf-8") as f:
    max_line = max(lines_dict.keys()) if lines_dict else 0
    for i in range(1, max_line + 1):
        f.write(lines_dict.get(i, f"# MISSING LINE {i}") + "\n")
