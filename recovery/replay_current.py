import json
import os

log_path = r'C:\Users\ndiaz_akrimet\.gemini\antigravity\brain\73eb9888-f9cd-47d8-ad38-3ec628feb08b\.system_generated\logs\transcript.jsonl'

with open(log_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

print("Loaded lines:", len(lines))

# Start from the base file
os.system("git checkout poll_manager.py")
with open('poll_manager.py', 'r', encoding='utf-8') as f:
    text = f.read()

edits = 0
for line in lines:
    try:
        data = json.loads(line)
        if 'tool_calls' in data:
            for call in data['tool_calls']:
                func = call.get('function', {})
                name = func.get('name')
                args_str = func.get('arguments', '')
                if 'poll_manager.py' in args_str:
                    args = json.loads(args_str)
                    target = args.get('TargetFile', '')
                    if 'poll_manager.py' in target:
                        if name == 'replace_file_content':
                            tc = args.get('TargetContent', '')
                            rc = args.get('ReplacementContent', '')
                            if tc in text:
                                text = text.replace(tc, rc)
                                edits += 1
                            else:
                                print(f"FAIL: replace_file_content at step {data.get('step_index')}")
                        elif name == 'multi_replace_file_content':
                            for chunk in args.get('ReplacementChunks', []):
                                tc = chunk.get('TargetContent', '')
                                rc = chunk.get('ReplacementContent', '')
                                if tc in text:
                                    text = text.replace(tc, rc)
                                    edits += 1
                                else:
                                    print(f"FAIL: multi_replace_file_content chunk at step {data.get('step_index')}")
    except Exception as e:
        pass

with open('restored_poll_manager.py', 'w', encoding='utf-8') as out:
    out.write(text)
print("Edits applied:", edits)
print("Restored length:", len(text))
