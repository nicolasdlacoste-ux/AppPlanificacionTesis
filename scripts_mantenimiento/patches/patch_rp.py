import re

rp = open('webapp/right-panel.js', encoding='utf-8').read()

old_val = '''    function validateEditConflicts() {
        if (!currentEvent) return;
        const selVehiculo = document.getElementById('edit-vehiculo').value;
        const newDate = document.getElementById('edit-fecha').value;
        const hStartF = parseHour(document.getElementById('edit-hstart').value);
        const hEndF = parseHour(document.getElementById('edit-hend').value);
        const selTec = document.getElementById('edit-tecnico');
        const tecNombre = selTec.options[selTec.selectedIndex]?.text || '';
        const gid = currentEvent.extended_props?.private?.grupo_id || null;

        const conflict = App.checkVehicleConflicts(selVehiculo, newDate, hStartF, hEndF, currentEvent.google_event_id, tecNombre, gid);
        if (conflict) {
            App.toast(conflict, 'warning');
        }
    }'''

new_val = '''    function validateEditConflicts() {
        if (!currentEvent) return;
        const selVehiculo = document.getElementById('edit-vehiculo').value;
        const newDate = document.getElementById('edit-fecha').value;
        const hStartF = parseHour(document.getElementById('edit-hstart').value);
        const hEndF = parseHour(document.getElementById('edit-hend').value);
        const selTec = document.getElementById('edit-tecnico');
        const tecNombre = selTec.options[selTec.selectedIndex]?.text || '';
        const gid = currentEvent.extended_props?.private?.grupo_id || null;
        
        let newDateEnd = null;
        const editFechaFinEl = document.getElementById('edit-fecha-fin');
        if (editFechaFinEl && editFechaFinEl.parentElement && !editFechaFinEl.parentElement.classList.contains('hidden')) {
            newDateEnd = editFechaFinEl.value;
        }

        const conflict = App.checkVehicleConflicts(selVehiculo, newDate, hStartF, hEndF, currentEvent.google_event_id, tecNombre, gid, newDateEnd);
        if (conflict) {
            App.toast("Vehículo: " + conflict, 'warning');
        }
        
        // Check patterns too!
        if (App.checkPatternConflicts) {
            const ots = window._editOts || [];
            const patConflict = App.checkPatternConflicts(editPatrones, newDate, newDateEnd, currentEvent.google_event_id, ots);
            if (patConflict) {
                App.toast("Patrones: " + patConflict, 'warning');
            }
        }
    }'''

rp = rp.replace(old_val, new_val)

old_save = '''        const conflict = App.checkVehicleConflicts(selVehiculo, newDate, hStartF, hEndF, currentEvent.google_event_id, tecNombre, gid);
        if (conflict) {
            App.toast(conflict, 'warning');
            // No bloqueamos el guardado, es solo warning
        }'''

new_save = '''        const conflict = App.checkVehicleConflicts(selVehiculo, newDate, hStartF, hEndF, currentEvent.google_event_id, tecNombre, gid, newDateEnd);
        if (conflict) {
            App.toast("Vehículo: " + conflict, 'warning');
            // No bloqueamos el guardado, es solo warning
        }
        
        if (App.checkPatternConflicts) {
            const ots = window._editOts || [];
            const patConflict = App.checkPatternConflicts(editPatrones, newDate, newDateEnd, currentEvent.google_event_id, ots);
            if (patConflict) {
                App.toast("Patrones: " + patConflict, 'warning');
            }
        }'''

rp = rp.replace(old_save, new_save)
open('webapp/right-panel.js', 'w', encoding='utf-8').write(rp)
print("Patched right-panel.js")
