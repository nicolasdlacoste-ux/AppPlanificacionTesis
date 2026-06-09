import json
import os

log_path = r'C:\Users\ndiaz_akrimet\.gemini\antigravity\brain\3419deb7-012a-4d98-8d0b-93b386fcaa69\.system_generated\logs\transcript.jsonl'

# Get base file
os.system("git checkout poll_manager.py")
with open('poll_manager.py', 'r', encoding='utf-8') as f:
    text = f.read()

with open(log_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

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
                    
                    if name == 'replace_file_content':
                        tc = args.get('TargetContent', '')
                        rc = args.get('ReplacementContent', '')
                        if tc in text:
                            text = text.replace(tc, rc)
                        else:
                            print("COULD NOT FIND TARGET CONTENT FOR replace_file_content")
                    elif name == 'multi_replace_file_content':
                        for chunk in args.get('ReplacementChunks', []):
                            tc = chunk.get('TargetContent', '')
                            rc = chunk.get('ReplacementContent', '')
                            if tc in text:
                                text = text.replace(tc, rc)
                            else:
                                print("COULD NOT FIND TARGET CONTENT FOR multi_replace_file_content chunk")
    except Exception as e:
        pass

with open('restored_poll_manager.py', 'w', encoding='utf-8') as out:
    out.write(text)
print("Restored file length:", len(text))
