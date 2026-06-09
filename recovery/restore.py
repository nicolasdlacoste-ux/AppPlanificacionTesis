import json
log_path = r'C:\Users\ndiaz_akrimet\.gemini\antigravity\brain\3419deb7-012a-4d98-8d0b-93b386fcaa69\.system_generated\logs\transcript.jsonl'

with open(log_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

for line in lines[::-1]:
    try:
        data = json.loads(line)
        if 'tool_calls' in data:
            for call in data['tool_calls']:
                args = call.get('function', {}).get('arguments', '')
                if 'poll_manager.py' in args and call['function']['name'] == 'write_to_file':
                    print("Found write_to_file!")
                    args_dict = json.loads(args)
                    with open('restored_poll_manager.py', 'w', encoding='utf-8') as out:
                        out.write(args_dict.get('CodeContent', ''))
                    exit(0)
    except Exception as e:
        pass

print("Not found write_to_file for poll_manager")
