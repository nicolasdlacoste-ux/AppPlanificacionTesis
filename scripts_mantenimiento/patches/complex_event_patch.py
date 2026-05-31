
import sys

with open("webapp/right-panel.js", "r", encoding="utf-8") as f:
    js = f.read()

target = """        let isMulti = false;
        if (dStartStr && dEndStr && dStartStr !== dEndStr) {
            // Check if it's more than 1 day (date is exclusive in Google for all-day)
            const d1 = new Date(dStartStr + 'T12:00:00');
            const d2 = new Date(dEndStr + 'T12:00:00');
            const diffDays = Math.round((d2 - d1) / (1000 * 60 * 60 * 24));
            if (diffDays > 1 || (diffDays === 1 && sRaw.includes('T'))) {
                isMulti = true;
            }
        }
        
        const elWarning = document.getElementById('ev-multi-warning');
        if (elWarning) elWarning.classList.toggle('hidden', !isMulti);
        const btnSplit = document.getElementById('btn-split-event');
        if (btnSplit) {
            btnSplit.classList.toggle('hidden', !isMulti);"""

replacement = """        let isMulti = false;
        if (dStartStr && dEndStr && dStartStr !== dEndStr) {
            const d1 = new Date(dStartStr + 'T12:00:00');
            const d2 = new Date(dEndStr + 'T12:00:00');
            const diffDays = Math.round((d2 - d1) / (1000 * 60 * 60 * 24));
            if (diffDays > 1 || (diffDays === 1 && sRaw.includes('T'))) {
                isMulti = true;
            }
        }
        
        const hasGuests = ev.extended_props?.private?.has_guests === "true";
        const isComplex = isMulti || hasGuests;
        
        const elWarning = document.getElementById('ev-multi-warning');
        if (elWarning) {
            elWarning.classList.toggle('hidden', !isComplex);
            if (isComplex) {
                elWarning.innerHTML = `?? Evento complejo (${hasGuests ? "invitados" : "multidía"}). 
Para editar/mover se recomienda individualizarlo.`;
            }
        }
        const btnSplit = document.getElementById('btn-split-event');
        if (btnSplit) {
            btnSplit.classList.toggle('hidden', !isComplex);"""

if target in js:
    js = js.replace(target, replacement)
    
    # Block edition target
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
    print("Complex event logic added to right-panel.js")
else:
    print("Target not found.")

