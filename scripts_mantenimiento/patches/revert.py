import sys

def revert_file():
    with open('webapp/app.js', 'r', encoding='utf-8') as f:
        content = f.read()

    new_refresh = '''    async function refreshEvents() {
        try {
            const evRes = await fetch(/api/eventos?t=);
            if (!evRes.ok) return;
            const newEvents = await evRes.json();
            
            // Merge respetando optimistic updates (_syncing)
            const merged = newEvents.map(incoming => {
                const local = _eventos.find(e => e.id === incoming.id);
                // Si la UI lo está editando, gana la UI (hasta que termine de guardar)
                if (local && local._syncing) return local;
                return incoming;
            });
            // Preservar eventos optimistas que aún no llegaron al server (ej: creados pero no confirmados)
            _eventos.forEach(local => {
                if (local._syncing && !merged.find(e => e.id === local.id)) merged.push(local);
            });
            
            _eventos = merged;
            Scheduler.setState({ tecnicos: _tecnicos, eventos: _eventos, holidays: _holidays });'''

    old_refresh = '''    async function refreshEvents() {
        try {
            const evRes = await fetch(/api/eventos?t=);
            if (!evRes.ok) return;
            _eventos = await evRes.json();
            Scheduler.setState({ tecnicos: _tecnicos, eventos: _eventos, holidays: _holidays });'''

    if new_refresh in content:
        content = content.replace(new_refresh, old_refresh)

    new_single = '''    function refreshSingleEvent(eventData) {
        const idx = _eventos.findIndex(e => e.id === eventData.id);
        if (idx !== -1) {
            const current = _eventos[idx];
            if (eventData.version !== undefined && current.version !== undefined && eventData.version < current.version) {
                console.warn([Sync] Ignorando update obsoleto para . Local v, Incoming v);
                return;
            }
            _eventos[idx] = eventData;
        } else {
            _eventos.push(eventData);
        }'''

    old_single = '''    function refreshSingleEvent(eventData) {
        const idx = _eventos.findIndex(e => e.id === eventData.id);
        if (idx !== -1) _eventos[idx] = eventData;
        else _eventos.push(eventData);'''

    if new_single in content:
        content = content.replace(new_single, old_single)


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

    old_load = '''            _eventos = await evRes.json();
            _ots = await otRes.json();'''

    if new_load in content:
        content = content.replace(new_load, old_load)

    with open('webapp/app.js', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Revert successful.")

revert_file()
