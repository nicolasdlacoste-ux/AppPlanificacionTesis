import os

with open('poll_manager.py', 'r', encoding='utf-8') as f:
    lines = f.read().split('\n')

for i, line in enumerate(lines):
    if "local = self.db.find_by_google_event_id(gid)" in line:
        lines[i] = line.replace("find_by_google_event_id(gid)", "find_by_google_event_id(gid, calendar_id)")
    if "local_for_move = self.db.find_by_google_event_id(gid)" in line:
        lines[i] = line.replace("find_by_google_event_id(gid)", "find_by_google_event_id(gid, calendar_id)")
    if "local = self.db.find_by_google_event_id(event_id)" in line:
        lines[i] = line.replace("find_by_google_event_id(event_id)", "find_by_google_event_id(event_id, calendar_id)")

with open('poll_manager.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print("Done")
