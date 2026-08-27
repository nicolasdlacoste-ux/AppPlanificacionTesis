def fix_app_js():
    with open('webapp/app.js', 'r', encoding='utf-8') as f:
        content = f.read()

    old = '''                if (data.event_id && data.event_id !== eventId) {
                    // Actualizar el ID en memoria antes del refresh para que sea seleccionable/arrastrable
                    const ev = _eventos.find(e => e.id === eventId);
                    if (ev) {
                        ev.id = data.event_id;
                        delete ev._syncing;
                    }
                    await refreshEvents();
                } else {
                    clearFlags();
                    Scheduler.render();
                }'''
    
    new = '''                // Forzamos refresh para capturar cambios por auto-agrupaci\u00f3n (grupo_id, t\u00edtulos con tags)
                if (data.event_id && data.event_id !== eventId) {
                    const ev = _eventos.find(e => e.id === eventId);
                    if (ev) ev.id = data.event_id;
                }
                await refreshEvents();'''

    if old in content:
        content = content.replace(old, new)
        with open('webapp/app.js', 'w', encoding='utf-8') as f:
            f.write(content)
        print("app.js updated to always refresh after move.")
    else:
        print("Could not find old move logic in app.js")

fix_app_js()
