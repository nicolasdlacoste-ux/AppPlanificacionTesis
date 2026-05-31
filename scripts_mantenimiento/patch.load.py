import sys

def patch_file():
    with open('webapp/app.js', 'r', encoding='utf-8') as f:
        content = f.read()

    old_load = '''            _eventos = await evRes.json();
            _ots = await otRes.json();'''

    new_load = '''            const newEvents = await evRes.json();
            const merged = newEvents.map(incoming => {
                const local = _eventos.find(e => e.id === incoming.id);
                if (local && local._syncing) return local;
                return incoming;
            });
            _eventos.forEach(local => {
                if (local._syncing && !merged.find(e => e.id === local.id)) merged.push(local);
            });
            _eventos = merged;
            
            _ots = await otRes.json();'''

    if old_load in content:
        content = content.replace(old_load, new_load)
        with open('webapp/app.js', 'w', encoding='utf-8') as f:
            f.write(content)
        print("Patch successful.")
    else:
        print("old_load not found.")

patch_file()
