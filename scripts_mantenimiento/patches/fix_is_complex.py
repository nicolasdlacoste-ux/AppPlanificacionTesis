
import sys

with open("webapp/right-panel.js", "r", encoding="utf-8") as f:
    js = f.read()

target = """                const isComplex = currentEvent && ( (currentEvent.attendees && currentEvent.attendees.length > 0) || (currentEvent.start && currentEvent.end && (new Date(currentEvent.end) - new Date(currentEvent.start) > 86400000)) );
                if (isComplex) {
                    App.toast('No se puede editar eventos complejos (multidía/invitados). Individualícelo primero.', 'warning');
                    return;
                }"""
                
replacement = """                if (!otData) {
                    App.toast(`Error: La OT ${val} no fue encontrada en el backlog.`, 'error');
                    return;
                }"""
                
if target in js:
    js = js.replace(target, replacement)
    
target2 = """            if (isMulti) {
                App.toast('No se puede editar eventos multi-día desde aquí. Ajuste en Google Calendar.', 'warning');
                return;
            }"""
replacement2 = """            if (isComplex) {
                App.toast('No se puede editar eventos complejos (multidía/invitados). Individualícelo primero.', 'warning');
                return;
            }"""

if target2 in js:
    js = js.replace(target2, replacement2)

with open("webapp/right-panel.js", "w", encoding="utf-8") as f:
    f.write(js)
print("Fixed isComplex replace")

