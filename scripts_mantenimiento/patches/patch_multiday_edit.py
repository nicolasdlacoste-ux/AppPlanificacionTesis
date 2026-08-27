import os, re

# PATCH BACKEND (api_server.py)
text = open('api_server.py', encoding='utf-8').read()

old_backend = r'''        if params\.h_start is not None:
            dur = params\.h_dur
            if dur is None:'''

new_backend = '''        if params.h_start is not None and "T" in start_orig:
            dur = params.h_dur
            if dur is None:'''

if re.search(old_backend, text):
    text = re.sub(old_backend, new_backend, text)
    open('api_server.py', 'w', encoding='utf-8').write(text)
    print("Patched api_server.py (h_start logic)!")
else:
    print("Could not find old_backend in api_server.py")

# PATCH FRONTEND (webapp/right-panel.js)
js_text = open('webapp/right-panel.js', encoding='utf-8').read()

old_js = r'''                        App\.refreshSingleEvent\(\{
                            \.\.\.currentEvent,
                            summary: newTitulo,
                            calendar_id: correoDest,
                            tecnico_nombre: techName,
                            inicio: `\$\{newDate\}T\$\{\_ph\(hStartF\)\}-03:00`,
                            fin:   `\$\{newDate\}T\$\{\_ph\(hEndF\)\}-03:00`,
                            descripcion: _formatDescriptionLocal\(newDesc, editPatrones, selVehiculo\),'''

new_js = '''                        let finalInicio = `${newDate}T${_ph(hStartF)}-03:00`;
                        let finalFin = `${newDate}T${_ph(hEndF)}-03:00`;
                        if (!currentEvent.inicio.includes("T")) {
                            finalInicio = newDate;
                            let endD = newDateEnd || newDate;
                            let d = new Date(endD + "T00:00:00");
                            d.setDate(d.getDate() + 1);
                            finalFin = d.toISOString().substring(0, 10);
                        }

                        App.refreshSingleEvent({
                            ...currentEvent,
                            summary: newTitulo,
                            calendar_id: correoDest,
                            tecnico_nombre: techName,
                            inicio: finalInicio,
                            fin: finalFin,
                            descripcion: _formatDescriptionLocal(newDesc, editPatrones, selVehiculo),'''

if re.search(old_js, js_text):
    js_text = re.sub(old_js, new_js, js_text)
    open('webapp/right-panel.js', 'w', encoding='utf-8').write(js_text)
    print("Patched right-panel.js (visual refresh logic)!")
else:
    print("Could not find old_js in right-panel.js")

# BUMP VERSION
html = open('webapp/index.html', encoding='utf-8').read()
html = html.replace('v=2.10', 'v=2.11')
open('webapp/index.html', 'w', encoding='utf-8').write(html)
print("Bumped version to 2.11")
