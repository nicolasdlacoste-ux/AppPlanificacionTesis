import json

log_path = r'C:\Users\ndiaz_akrimet\.gemini\antigravity\brain\3419deb7-012a-4d98-8d0b-93b386fcaa69\.system_generated\logs\transcript.jsonl'

with open(log_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

for idx, line in enumerate(lines):
    try:
        data = json.loads(line)
        if 'tool_calls' in data:
            for call in data['tool_calls']:
                func = call.get('function', {})
                name = func.get('name')
                args_str = func.get('arguments', '')
                if 'poll_manager.py' in args_str:
                    print(f"Step {data.get('step_index')}: {name} called on poll_manager.py")
        if data.get('type') == 'TOOL_RESPONSE':
            content = data.get('content', '')
            if 'poll_manager.py' in content:
                print(f"Step {data.get('step_index')}: TOOL_RESPONSE mentioned poll_manager.py, length of response {len(content)}")
    except Exception as e:
        pass
