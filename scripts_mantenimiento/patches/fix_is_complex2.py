# coding=utf-8
import sys

with open("webapp/right-panel.js", "r", encoding="utf-8") as f:
    js = f.read()

# Fix the addOT function back to its normal state
target_addot = """                const isComplex = currentEvent?.extended_props?.is_complex;
                if (isComplex) {
                    App.toast('No se puede editar eventos complejos (multidía/invitados). Individualícelo primero.', 'warning');
                    return;
                }

                if (!otData) {
                    App.toast(`Error: La OT ${val} no fue encontrada en el backlog.`, 'error');
                    return;
                }"""
                
replacement_addot = """                if (!otData) {
                    App.toast(`Error: La OT ${val} no fue encontrada en el backlog.`, 'error');
                    return;
                }"""

if target_addot in js:
    js = js.replace(target_addot, replacement_addot)
    print("Fixed addOT")
else:
    print("addOT target not found")

# Now inject the isComplex validation where it really belongs, inside editEvent block.
target_edit = """            if (isMulti) {
                App.toast('No se puede editar eventos multi-día desde aquí. Ajuste en Google Calendar.', 'warning');
                return;
            }"""
            
replacement_edit = """            if (isComplex) {
                App.toast('No se puede editar eventos complejos (multidía/invitados). Individualícelo primero.', 'warning');
                return;
            }"""

if target_edit in js:
    js = js.replace(target_edit, replacement_edit)
    print("Fixed editEvent")
else:
    print("editEvent target not found")

with open("webapp/right-panel.js", "w", encoding="utf-8") as f:
    f.write(js)

