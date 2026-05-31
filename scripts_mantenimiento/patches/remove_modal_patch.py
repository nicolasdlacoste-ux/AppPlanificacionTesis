
import sys

with open("webapp/right-panel.js", "r", encoding="utf-8") as f:
    js = f.read()

target1 = """            if (cambioTecnico && esDeGrupo) {
                // Cambio de técnico en grupo ? siempre individual, reconfigura grupo
                btn.disabled = false;
                btn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Guardar';
                showGroupActionModal(
                    `Este evento pertenece a un grupo de <strong>${grupo.tecnico_nombres.length} técnicos</strong>.<br>
                    <small style="color:var(--text-muted)">Cambiar de técnico solo aplica a este evento. El grupo se reconfigurará automáticamente.</small>`,
                    grupo,
                    () => _doMove('mover'),   // Solo este técnico (disuelve/reconfigura el grupo)
                    null,                      // No hay opción "Todo el grupo" para cambio de técnico
                    () => { btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Guardar'; }
                );
            } else if (cambioFechaHora && esDeGrupo) {
                btn.disabled = false;
                btn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Guardar';
                showGroupActionModal(
                    `Este evento pertenece a un grupo de <strong>${grupo.tecnico_nombres.length} técnicos</strong>. ¿A quiénes aplica el cambio de fecha/hora?`,
                    grupo,
                    () => _doMove('mover'),
                    () => _doMoveGrupo(),
                    () => { btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Guardar'; }
                );
            } else if (cambioTecnico) {
                await _doMove('mover');
            } else {
                await _doMove('mover');
            }"""

replacement1 = """            await _doMove("mover");"""

if target1 in js:
    js = js.replace(target1, replacement1)
else:
    print("Warning: target1 not found")

with open("webapp/right-panel.js", "w", encoding="utf-8") as f:
    f.write(js)
print("removed group modal logic.")

