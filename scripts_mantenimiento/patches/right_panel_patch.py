
import sys

with open("webapp/right-panel.js", "r", encoding="utf-8") as f:
    js = f.read()

# Append the new functions before the return block
new_functions = """
    let batchEventsCache = [];

    function showBatchMode() {
        document.querySelectorAll(".ctx-view").forEach(el => el.classList.remove("active"));
        const batchView = document.getElementById("ctx-batch");
        if (batchView) batchView.classList.add("active");
        
        // Populate Tecnico select
        const selTec = document.getElementById("batch-tec");
        if (selTec) {
            selTec.innerHTML = `<option value="">-- Mantener Técnico Actual --</option>` +
                (window._tecnicos || []).map(t => `<option value="${t.correo}">${t.nombre}</option>`).join("");
        }

        // Populate Vehiculo select
        const selVeh = document.getElementById("batch-vehiculo");
        if (selVeh) {
            selVeh.innerHTML = `<option value="">-- Mantener Vehículo --</option>` +
                (window._vehiculos || []).map(v => `<option value="${v.patente}">${v.patente}</option>`).join("");
        }

        updateBatchUI([]);
    }

    function updateBatchUI(selectedIds) {
        const countLabel = document.getElementById("batch-selected-count");
        if (countLabel) countLabel.innerText = `${selectedIds.length} eventos seleccionados`;

        // Calculate earliest date
        let earliestDate = null;
        batchEventsCache = [];
        const allEvs = App.getEventos();
        
        selectedIds.forEach(id => {
            const ev = allEvs.find(e => e.google_event_id === id);
            if (ev) {
                batchEventsCache.push(ev);
                const evDateStr = (ev.inicio || "").substring(0, 10);
                if (evDateStr) {
                    const evDate = new Date(evDateStr + "T12:00:00");
                    if (!earliestDate || evDate < earliestDate.dateObj) {
                        earliestDate = { dateObj: evDate, str: evDateStr };
                    }
                }
            }
        });

        const dateInput = document.getElementById("batch-fecha");
        if (dateInput) {
            if (earliestDate) {
                dateInput.value = earliestDate.str;
                dateInput.dataset.baseDate = earliestDate.str;
            } else {
                dateInput.value = "";
                dateInput.dataset.baseDate = "";
            }
        }
    }

    // Bind Apply and Exit buttons
    setTimeout(() => {
        const btnApply = document.getElementById("btn-batch-apply");
        const btnExit = document.getElementById("btn-batch-exit");
        
        if (btnExit) {
            btnExit.addEventListener("click", () => {
                App.toggleBatchMode();
            });
        }

        if (btnApply) {
            btnApply.addEventListener("click", async () => {
                if (batchEventsCache.length === 0) {
                    App.toast("No hay eventos seleccionados", "warning");
                    return;
                }

                btnApply.disabled = true;
                btnApply.innerText = "Aplicando...";

                try {
                    const tecInput = document.getElementById("batch-tec").value;
                    const otsInput = document.getElementById("batch-ots").value;
                    const patsInput = document.getElementById("batch-patrones").value;
                    const vehInput = document.getElementById("batch-vehiculo").value;
                    const dateInput = document.getElementById("batch-fecha");
                    
                    let delta_dias = 0;
                    if (dateInput && dateInput.value && dateInput.dataset.baseDate) {
                        const baseD = new Date(dateInput.dataset.baseDate + "T12:00:00");
                        const newD = new Date(dateInput.value + "T12:00:00");
                        delta_dias = Math.round((newD - baseD) / (1000 * 60 * 60 * 24));
                    }

                    const payload = {
                        event_ids: batchEventsCache.map(e => e.google_event_id)
                    };

                    if (delta_dias !== 0) payload.delta_dias = delta_dias;
                    if (tecInput) payload.correo_destino = tecInput;
                    if (otsInput.trim()) payload.ots = otsInput.split(",").map(s => s.trim()).filter(s => s);
                    if (patsInput.trim()) payload.patrones = patsInput.split(",").map(s => s.trim()).filter(s => s);
                    if (vehInput) payload.vehiculo = vehInput;

                    const res = await fetch("/api/eventos/batch/editar", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(payload)
                    });

                    if (!res.ok) throw new Error(await res.text());
                    
                    App.toast(`Se actualizaron exitosamente.`, "success");
                    App.toggleBatchMode();
                    App.refreshEvents(); // Reload everything from server
                    
                } catch(e) {
                    App.toast("Error al aplicar cambios: " + e.message, "error");
                } finally {
                    btnApply.disabled = false;
                    btnApply.innerText = "Aplicar Cambios";
                }
            });
        }
    }, 500); // give DOM time to attach
"""

# Insert before the return statement
target_return = "    return {\n        init,"
replacement_return = new_functions + "\n" + target_return

js = js.replace(target_return, replacement_return)

# Expose
target_expose = "showGroupActionModal,"
replacement_expose = "showGroupActionModal, showBatchMode, updateBatchUI,"
js = js.replace(target_expose, replacement_expose)

with open("webapp/right-panel.js", "w", encoding="utf-8") as f:
    f.write(js)
print("right-panel.js patched.")

