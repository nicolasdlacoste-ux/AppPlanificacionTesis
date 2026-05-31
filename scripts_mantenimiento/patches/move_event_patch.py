
import sys

with open("webapp/app.js", "r", encoding="utf-8") as f:
    js = f.read()

target = """        if (grupoInfo && grupoInfo.tecnico_nombres.length > 1) {
            if (typeof RightPanel !== 'undefined' && RightPanel.showGroupActionModal) {
                RightPanel.showGroupActionModal(
                    `Estás moviendo un evento que forma parte de un grupo de <strong>${grupoInfo.tecnico_nombres.length} técnicos</strong>. ¿A quiénes aplica este movimiento?`,
                    grupoInfo,
                    () => doMove('solo'), 
                    () => doMove('grupo'),
                    () => { 
                        _globalSyncing = false;
                        // Cancelado, forzar render para que FullCalendar descarte el drop visual
                        Scheduler.render(); 
                    }
                );
            } else {
                doMove('solo'); // Fallback de seguridad
            }
        } else {
            doMove('solo');
        }"""

replacement = """        if (grupoInfo) {
            const cambioTecnico = destCorreo && destCorreo !== calendarId;
            const currentDate = currentEvent.inicio ? currentEvent.inicio.substring(0, 10) : "";
            const cambioFecha = nuevaFecha && currentDate && nuevaFecha !== currentDate;
            
            if (cambioTecnico && cambioFecha) {
                toast('No se puede cambiar fecha y técnico a la vez en un evento de grupo.', 'error');
                _globalSyncing = false;
                Scheduler.render();
                return;
            }
            doMove('grupo');
        } else {
            doMove('solo');
        }"""

if target in js:
    js = js.replace(target, replacement)
    with open("webapp/app.js", "w", encoding="utf-8") as f:
        f.write(js)
    print("app.js moveEvent patched for group rule")
else:
    print("target not found in app.js")

