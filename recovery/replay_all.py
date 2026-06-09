import json
import os
import glob

brains_dir = r'C:\Users\ndiaz_akrimet\.gemini\antigravity\brain'
transcripts = glob.glob(os.path.join(brains_dir, '*\.system_generated\logs\transcript.jsonl'))

# Base checkout
os.system("git checkout poll_manager.py")
with open('poll_manager.py', 'r', encoding='utf-8') as f:
    text = f.read()

# We will replay all edits in chronological order!
# First we need all edit events from all transcripts, sorted by step_index/time.
events = []

for log_path in transcripts:
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
                        events.append((data.get('created_at'), log_path, data.get('step_index'), name, args_str))
        except Exception as e:
            pass

events.sort(key=lambda x: x[0]) # sort by timestamp

for ev in events:
    created_at, log_path, step, name, args_str = ev
    args = json.loads(args_str)
    
    target = args.get('TargetFile', '')
    if 'poll_manager.py' in target:
        if name == 'replace_file_content':
            tc = args.get('TargetContent', '')
            rc = args.get('ReplacementContent', '')
            if tc in text:
                text = text.replace(tc, rc)
                print(f"Applied replace {created_at}")
        elif name == 'multi_replace_file_content':
            for chunk in args.get('ReplacementChunks', []):
                tc = chunk.get('TargetContent', '')
                rc = chunk.get('ReplacementContent', '')
                if tc in text:
                    text = text.replace(tc, rc)
                    print(f"Applied multi {created_at}")

with open('restored_poll_manager.py', 'w', encoding='utf-8') as out:
    out.write(text)
print("Finished. Length:", len(text))
