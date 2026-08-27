import re

def patch_file():
    with open('webapp/app.js', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Patch refreshEvents
    pattern_refresh = r"(_eventos\s*=\s*await\s*evRes\.json\(\);\s*Scheduler\.setState\(\{)"
    
    replacement_refresh = '''const newEvents = await evRes.json();
            const merged = [];
            for (let i = 0; i < newEvents.length; i++) {
                const incoming = newEvents[i];
                let local = null;
                for (let j = 0; j < _eventos.length; j++) {
                    if (_eventos[j].id === incoming.id) { local = _eventos[j]; break; }
                }
                if (local && local._syncing) merged.push(local);
                else merged.push(incoming);
            }
            for (let j = 0; j < _eventos.length; j++) {
                const local = _eventos[j];
                if (local._syncing) {
                    let found = false;
                    for (let k = 0; k < merged.length; k++) {
                        if (merged[k].id === local.id) { found = true; break; }
                    }
                    if (!found) merged.push(local);
                }
            }
            _eventos = merged;
            Scheduler.setState({'''
            
    content, count = re.subn(pattern_refresh, replacement_refresh, content, count=1)
    if count > 0:
        print("refreshEvents patched.")
    else:
        print("refreshEvents NOT found.")

    # 2. Patch refreshSingleEvent
    pattern_single = r"(function\s+refreshSingleEvent\(eventData\)\s*\{\s*const\s+idx\s*=\s*_eventos\.findIndex\(e\s*=>\s*e\.id\s*===\s*eventData\.id\);\s*)if\s*\(idx\s*!==\s*-1\)\s*_eventos\[idx\]\s*=\s*eventData;\s*else\s*_eventos\.push\(eventData\);"
    
    replacement_single = r'''\1if (idx !== -1) {
            const current = _eventos[idx];
            if (eventData.version !== undefined && current.version !== undefined && eventData.version < current.version) {
                console.warn("[Sync] Ignorando update obsoleto para " + eventData.id);
                return;
            }
            _eventos[idx] = eventData;
        } else {
            _eventos.push(eventData);
        }'''
        
    content, count = re.subn(pattern_single, replacement_single, content, count=1)
    if count > 0:
        print("refreshSingleEvent patched.")
    else:
        print("refreshSingleEvent NOT found.")

    with open('webapp/app.js', 'w', encoding='utf-8') as f:
        f.write(content)

patch_file()
