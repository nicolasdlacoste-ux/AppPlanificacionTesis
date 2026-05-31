
import sys

with open("webapp/right-panel.js", "r", encoding="utf-8") as f:
    js = f.read()

target = """        const btnDelete = document.getElementById('btn-delete-event');
        if (btnDelete) {
            btnDelete.onclick = () => {
                        async () => {
                            try {
                                const r = await fetch(`/api/grupos/${grupo.grupo_id}`, { method: 'DELETE' });
                                if (!r.ok) {
                                    const errText = await r.text();
                                    let errMsg = errText;
                                    try { 
                                        let parsed = JSON.parse(errText);
                                        errMsg = (typeof parsed.detail === 'string') ? parsed.detail : 
JSON.stringify(parsed.detail || parsed);
                                    } catch(_) {}
                                    throw new Error(errMsg);
                                }
                                App.toast('Grupo eliminado ???', 'success');
                                (grupo.event_ids || []).forEach(eid => App.removeSingleEvent(eid));
                                showEmpty();
                            } catch (e) { App.toast(e, 'error'); }
                        }
                    );
                } else {
                    if (confirm(`¿Eliminar "${title}"?`)) App.deleteEvent(ev.google_event_id, ev.calendar_id || 
'primary');
                }
            };
        }"""

# A simpler approach using python string search:
start_idx = js.find("const btnDelete = document.getElementById('btn-delete-event');")
end_idx = js.find("// Duplicar Evento", start_idx)

if start_idx != -1 and end_idx != -1:
    old_block = js[start_idx:end_idx]
    new_block = """const btnDelete = document.getElementById('btn-delete-event');
        if (btnDelete) {
            btnDelete.onclick = () => {
                if (confirm(`¿Eliminar "${title}"?`)) App.deleteEvent(ev.google_event_id, ev.calendar_id || 'primary');
            };
        }

        """
    js = js.replace(old_block, new_block)
    
with open("webapp/right-panel.js", "w", encoding="utf-8") as f:
    f.write(js)
print("btnDelete fixed")

