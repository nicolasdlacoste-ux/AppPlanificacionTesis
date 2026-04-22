// ════════════════════════════════════════
// RIGHT PANEL — Akrimet Planner v2.0
// ════════════════════════════════════════

const RightPanel = (() => {
    let currentOT = null;
    let currentEvent = null;
    let selectedOption = null;
    let pivotDate = null;
    let selectedPatrones = [];
    let editPatrones = [];
    let patronModalCaller = 'ot'; // 'ot' | 'edit'

    // ─────────────────────────────────
    // CONTEXT SWITCHING
    // ─────────────────────────────────
    function showContext(id) {
        document.querySelectorAll('.ctx-view').forEach(v => v.classList.remove('active'));
        document.getElementById(id).classList.add('active');
    }

    function showEmpty() { showContext('ctx-empty'); currentEvent = null; currentOT = null; }

    // ─────────────────────────────────
    // CONTEXT B: EVENT DETAIL
    // ─────────────────────────────────
    function showEventDetail(ev) {
        currentEvent = ev;
        showContext('ctx-event');

        // Reset to view mode
        setEditMode(false);

        const title = ev.title || 'Sin título';
        document.getElementById('ev-title').textContent = title;
        document.getElementById('ev-tecnico').textContent = ev.resourceId || '—';

        // Horario
        const sh = parseHour(ev.start);
        const eh = parseHour(ev.end);
        const dateStr = (ev.start || '').substring(0, 10);
        const dateFmt = dateStr ? new Date(dateStr + 'T12:00:00').toLocaleDateString('es-ES', {
            weekday: 'short', day: 'numeric', month: 'short'
        }) : '—';
        document.getElementById('ev-horario').textContent =
            `${dateFmt} · ${fmtH(sh)} – ${fmtH(eh)}`;

        // Técnico(s)
        const tecDiv = document.getElementById('ev-tecnicos-list');
        tecDiv.innerHTML = `<span class="tag">${ev.resourceId || '—'}</span>`;

        // Patrones desde extendedProperties
        const patronDiv = document.getElementById('ev-patrones');
        try {
            const props = ev.extendedProperties || {};
            const privateProps = props.private || {};
            let rawPats = privateProps.app_patrones || props.app_patrones || '[]';
            
            let pats = [];
            if (Array.isArray(rawPats)) {
                pats = rawPats;
            } else if (typeof rawPats === 'string') {
                try {
                    pats = JSON.parse(rawPats);
                } catch { pats = []; }
            }

            patronDiv.innerHTML = pats.length
                ? pats.map(p => `<span class="tag">${p}</span>`).join('')
                : '<span style="color:var(--text-muted);font-size:11px">Sin patrones</span>';
        } catch (e) { 
            console.error("Error parsing patterns:", e);
            patronDiv.innerHTML = '—'; 
        }

        // Vehiculo
        const vehDiv = document.getElementById('ev-vehiculo');
        try {
            const props = ev.extendedProperties || {};
            const privateProps = props.private || {};
            const veh = privateProps.app_vehiculo || props.app_vehiculo || null;
            const req = (privateProps.app_requiere_vehiculo || props.app_requiere_vehiculo) === 'true';
            if (veh) {
                vehDiv.innerHTML = `<span class="tag" style="background:var(--accent);color:white">${veh}</span>` + 
                                   (req ? ` <span style="font-size:10px; color:var(--text-muted); margin-left:4px">[x] Requiere</span>` : '');
            } else {
                vehDiv.innerHTML = '<span style="color:var(--text-muted);font-size:11px">Sin vehículo</span>';
            }
        } catch { vehDiv.innerHTML = '—'; }

        // OTs vinculadas — extraer del título
        const otsDiv = document.getElementById('ev-ots');
        const ots = Scheduler.extractOTsFromTitle(title);
        currentEvent.ots = ots; // Guardar para modal de equipos
        if (ots.length > 0) {
            otsDiv.innerHTML = ots.map(o => `<span class="tag">${o}</span>`).join('');
            loadPartidasEv(ots, document.getElementById('ev-partidas-table'));
        } else {
            otsDiv.innerHTML = '<span style="color:var(--text-muted);font-size:11px">Sin OT asociada</span>';
            document.getElementById('ev-partidas-table').innerHTML =
                '<span style="padding:8px;display:block;color:var(--text-muted);font-size:11px">—</span>';
        }

        // Edit mode: pre-fill fields
        prefillEditFields(ev);

        // Multi-day warning and split button
        const sRaw = ev.start || '';
        const eRaw = ev.end || '';
        const dStartStr = sRaw.substring(0, 10);
        const dEndStr = eRaw.substring(0, 10);
        
        let isMulti = false;
        if (dStartStr && dEndStr && dStartStr !== dEndStr) {
            // Check if it's more than 1 day (date is exclusive in Google for all-day)
            const d1 = new Date(dStartStr + 'T12:00:00');
            const d2 = new Date(dEndStr + 'T12:00:00');
            const diffDays = Math.round((d2 - d1) / (1000 * 60 * 60 * 24));
            if (diffDays > 1 || (diffDays === 1 && sRaw.includes('T'))) {
                isMulti = true;
            }
        }
        
        document.getElementById('ev-multi-warning').classList.toggle('hidden', !isMulti);
        document.getElementById('btn-split-event').classList.toggle('hidden', !isMulti);

        // Re-vincular botón Individualizar con el evento actual
        const btnSplit = document.getElementById('btn-split-event');
        btnSplit.onclick = () => {
            const calId = ev.calendarId || ev.calendar_id || 'primary';
            App.splitEvent(ev.id, calId);
        };

        // Delete
        document.getElementById('btn-delete-event').onclick = () => {
            if (confirm(`¿Eliminar "${title}"?`)) App.deleteEvent(ev.id, ev.calendarId || 'primary');
        };

        // --- GESTIÓN DE GRUPOS: AGREGAR TÉCNICO ---
        document.getElementById('btn-add-tech').onclick = () => {
            currentEvent = ev;
            const sel = document.getElementById('st-tech-select');
            const tecs = window._tecnicos || [];
            // Filtrar los que ya están en el grupo
            const currentTecs = ev._grupo_tecs || [ev.resourceId];
            const filtered = tecs.filter(t => !currentTecs.includes(t.nombre));
            
            sel.innerHTML = filtered.map(t => `<option value="${t.correo}">${t.nombre}</option>`).join('');
            document.getElementById('modal-select-tech').classList.remove('hidden');
        };

        // Cargar información de grupo si existe
        loadGroupInfo(ev.id);
    }

    async function loadGroupInfo(eventId) {
        const tecDiv = document.getElementById('ev-tecnicos-list');
        try {
            const res = await fetch(`/api/grupos/evento/${eventId}`);
            const grupo = await res.json();
            
            if (grupo && grupo.grupo_id) {
                currentEvent._grupo_tecs = grupo.tecnico_nombres;
                tecDiv.innerHTML = grupo.tecnico_nombres.map((name, i) => {
                    const eid = grupo.event_ids[i];
                    // Si es el evento actual, no mostramos el botón 'quitar' si queremos que use Borrar
                    // O mostramos 'quitar' para todos. Usaremos 'quitar' para todos.
                    const isSelf = eid === currentEvent.id;
                    const tecMail = (window._tecnicos || []).find(t => t.nombre === name)?.correo;
                    
                    return `
                    <div class="tec-group-item">
                        <span class="tag ${isSelf ? 'self' : ''}">${name}</span>
                        ${tecMail ? `<button class="btn-remove-tech" onclick="App.quitarTecnicoDeGrupo('${eid}', '${tecMail}')" title="Quitar del grupo"><i class="fa-solid fa-xmark"></i></button>` : ''}
                    </div>`;
                }).join('');
            }
        } catch (e) {
            console.warn('[LoadGroup] No se pudo cargar info de grupo:', e);
        }
    }

    async function handleAddTechConfirm() {
        console.log('[RightPanel] Intentando agregar técnico...', currentEvent);
        if (!currentEvent) {
            console.error('[RightPanel] No hay evento seleccionado');
            return;
        }
        
        const sel = document.getElementById('st-tech-select');
        const correo = sel.value;
        if (!correo) {
            console.warn('[RightPanel] No se seleccionó técnico');
            return;
        }

        console.log('[RightPanel] Enviando solicitud para técnico:', correo);
        const btn = document.getElementById('btn-confirm-add-tech');
        const originalHtml = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Agregando...';

        try {
            const calId = currentEvent.calendarId || currentEvent.calendar_id || 'primary';
            const res = await fetch(`/api/eventos/${currentEvent.id}/agregar_tecnico?tecnico_correo=${encodeURIComponent(correo)}&calendar_id=${encodeURIComponent(calId)}`, {
                method: 'POST'
            });
            
            if (!res.ok) {
                const errText = await res.text();
                throw new Error(errText || 'Error del servidor');
            }
            
            console.log('[RightPanel] Éxito al agregar técnico');
            App.toast('Técnico agregado ✓ (Sync en progreso)', 'success');
            document.getElementById('modal-select-tech').classList.add('hidden');
            
            // Refrescar para ver los cambios
            setTimeout(() => App.refresh(), 1000); 
        } catch (e) {
            console.error('[RightPanel] Error:', e);
            App.toast('Error: ' + e.message, 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = originalHtml;
        }
    }

    function prefillEditFields(ev) {
        // Título y Descrip
        document.getElementById('edit-titulo').value = ev.title || '';
        document.getElementById('edit-descripcion').value = ev.description || '';

        // Técnico selector
        const sel = document.getElementById('edit-tecnico');
        sel.innerHTML = (window._tecnicos || []).map(t =>
            `<option value="${t.nombre}" data-correo="${t.correo}" ${t.nombre === ev.resourceId ? 'selected' : ''}>${t.nombre}</option>`
        ).join('');

        // Fecha
        document.getElementById('edit-fecha').value = (ev.start || '').substring(0, 10);

        // Horas
        const sh = parseHour(ev.start);
        const eh = parseHour(ev.end);
        document.getElementById('edit-hstart').value = fmtH(sh);
        document.getElementById('edit-hend').value = fmtH(eh);

        // Patrones
        try {
            const props = ev.extendedProperties || {};
            const privateProps = props.private || {};
            let rawPats = privateProps.app_patrones || props.app_patrones || '[]';
            if (typeof rawPats === 'string' && rawPats.startsWith('[')) {
                rawPats = JSON.parse(rawPats);
            }
            editPatrones = Array.isArray(rawPats) ? rawPats : [];
        } catch { editPatrones = []; }
        updateEditPatronBadge();

        // Vehiculos
        const selVeh = document.getElementById('edit-vehiculo');
        const vehiculos = App.getVehiculos() || [];
        selVeh.innerHTML = '<option value="">Sin vehículo</option>' + vehiculos.map(v => `<option value="${v.nombre}">${v.nombre}</option>`).join('');
        try {
            const props = ev.extendedProperties || {};
            const privateProps = props.private || {};
            selVeh.value = privateProps.app_vehiculo || props.app_vehiculo || '';
            document.getElementById('edit-req-vehiculo').checked = (privateProps.app_requiere_vehiculo || props.app_requiere_vehiculo) === 'true';
        } catch {}
    }

    function setEditMode(on) {
        document.getElementById('ev-view-mode').classList.toggle('hidden', on);
        document.getElementById('ev-edit-mode').classList.toggle('hidden', !on);
        document.getElementById('ev-footer-view').classList.toggle('hidden', on);
        document.getElementById('ev-footer-edit').classList.toggle('hidden', !on);
    }

    async function loadPartidasEv(ots, container) {
        if (!ots || ots.length === 0) return;
        container.innerHTML = '<div style="padding:8px;color:var(--text-muted);font-size:11px">Cargando...</div>';
        try {
            const res = await fetch('/api/ots/batch/partidas', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ nros: ots })
            });
            if (!res.ok) throw new Error('no data');
            const data = await res.json();
            if (data.partidas?.length > 0) {
                container.innerHTML = `
                    <table class="data-table">
                        <thead><tr><th>Trabajo</th><th>Puntos</th><th>Cant.</th></tr></thead>
                        <tbody>${data.partidas.map(p => `
                            <tr><td>${p.trabajo}</td><td>${p.puntos}</td><td style="text-align:center">${p.cant}</td></tr>`
                        ).join('')}</tbody>
                    </table>`;
            } else {
                container.innerHTML = '<div style="padding:8px;color:var(--text-muted);font-size:11px">Sin partidas registradas</div>';
            }
        } catch {
            container.innerHTML = '<div style="padding:8px;color:var(--text-muted);font-size:11px">No hay datos de partidas</div>';
        }
    }

    // Save event edits
    async function saveEventEdit() {
        if (!currentEvent) return;
        const btn = document.getElementById('btn-save-edit');
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';

        const sel = document.getElementById('edit-tecnico');
        const selectedOpt = sel.options[sel.selectedIndex];
        const newTecnico = sel.value;
        const correoDest = selectedOpt.dataset.correo || newTecnico;
        const newDate = document.getElementById('edit-fecha').value;
        const newHstart = document.getElementById('edit-hstart').value;
        const newHend = document.getElementById('edit-hend').value;
        const newTitulo = document.getElementById('edit-titulo').value.trim();
        const newDesc = document.getElementById('edit-descripcion').value.trim();

        const [sh, sm] = newHstart.split(':').map(Number);
        const [eh, em] = newHend.split(':').map(Number);
        const hStartF = sh + sm / 60;
        const hEndF = eh + em / 60;

        try {
            const oldCalId = currentEvent.calendarId || correoDest;

            // Recoger vehículo
            const selVehiculo = document.getElementById('edit-vehiculo').value || null;
            const reqVehiculo = document.getElementById('edit-req-vehiculo').checked;

            // Validar vehículo (Muestra alerta, pero no bloquea el guardado según indicaciones)
            const conflict = App.checkVehicleConflicts(selVehiculo, newDate, hStartF, hEndF, currentEvent.id, selectedOpt.text);
            if (conflict) {
                App.toast(conflict, 'warning');
            }

        function _formatDescriptionLocal(base, patrones, vehiculo) {
            let cleanBase = base || "";
            if (cleanBase.includes("──────────")) {
                cleanBase = cleanBase.split("──────────")[0].trim();
            }
            let meta = [];
            if (patrones && patrones.length) meta.push(`🛠️ Patrones: ${patrones.join(', ')}`);
            if (vehiculo) meta.push(`🚐 Vehículo: ${vehiculo}`);
            if (!meta.length) return cleanBase;
            return `${cleanBase}\n\n─────────────────────────────────────────────\n${meta.join('\n')}\n─────────────────────────────────────────────`.trim();
        }

            // First: update time/date/tech
            const moveRes = await fetch(`/api/eventos/${currentEvent.id}/mover`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    event_id: currentEvent.id,
                    calendar_id_origen: oldCalId,
                    correo_destino: correoDest,
                    nueva_fecha: newDate,
                    h_start: hStartF,
                    h_dur: hEndF - hStartF,
                    titulo: newTitulo,
                    descripcion: newDesc,
                    patrones: editPatrones,
                    vehiculo: selVehiculo,
                    requiere_vehiculo: reqVehiculo
                })
            });
            if (!moveRes.ok) throw new Error(await moveRes.text());
            App.toast('Evento actualizado ✓', 'success');
            setEditMode(false);
            // Actualizar evento en memoria al instante, sin recargar todo
            const _ph = (h) => `${String(Math.floor(h)).padStart(2,'0')}:${String(Math.round((h%1)*60)).padStart(2,'0')}:00`;
            const origPrivate = ((currentEvent.extendedProperties || {}).private) || {};
            const newPrivate = {
                ...origPrivate,
                app_patrones: JSON.stringify(editPatrones),
                app_vehiculo: selVehiculo || '',
                app_requiere_vehiculo: reqVehiculo ? 'true' : 'false',
            };
            App.refreshSingleEvent({
                ...currentEvent,
                resourceId: newTecnico,
                title: newTitulo,
                start: `${newDate}T${_ph(hStartF)}-03:00`,
                end:   `${newDate}T${_ph(hEndF)}-03:00`,
                description: _formatDescriptionLocal(newDesc, editPatrones, selVehiculo),
                extendedProperties: { ...(currentEvent.extendedProperties || {}), private: newPrivate },
                calendarId: correoDest,
            });
        } catch (e) {
            App.toast('Error al guardar: ' + e.message, 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Guardar';
        }
    }

    // ─────────────────────────────────
    // CONTEXT C: OT SCHEDULER
    // ─────────────────────────────────
    function showOTScheduler(ot) {
        currentOT = ot;
        selectedOption = null;
        showContext('ctx-ot-scheduler');

        const vehiculos = App.getVehiculos() || [];
        const selVeh = document.getElementById('p-vehiculo');
        selVeh.innerHTML = '<option value="">Sin vehículo</option>' + vehiculos.map(v => `<option value="${v.nombre}">${v.nombre}</option>`).join('');
        document.getElementById('p-req-vehiculo').checked = false;

        document.getElementById('sched-ot-title').textContent = `OT ${ot.nro}`;
        document.getElementById('sched-ot-cliente').textContent = ot.cliente;
        document.getElementById('sched-results').classList.add('hidden');
        document.getElementById('btn-confirmar-prog').disabled = true;
        selectedPatrones = [];
        updatePatronBadge();

        loadPartidas(ot.nro, document.getElementById('sched-partidas-table'))
            .then(data => {
                if (data) {
                    document.getElementById('sched-partidas-total').textContent =
                        `Total: ${data.total_partidas} partida${data.total_partidas !== 1 ? 's' : ''}`;
                }
            });
    }

    async function loadPartidas(nro, container) {
        container.innerHTML = '<div style="padding:8px;color:var(--text-muted);font-size:11px">Cargando...</div>';
        try {
            const res = await fetch(`/api/ots/${nro}/partidas`);
            const data = await res.json();
            if (data.partidas?.length > 0) {
                container.innerHTML = `
                    <table class="data-table">
                        <thead><tr><th>Trabajo</th><th>Puntos</th><th>Cant.</th></tr></thead>
                        <tbody>${data.partidas.map(p =>
                            `<tr><td>${p.trabajo}</td><td>${p.puntos}</td><td style="text-align:center">${p.cant}</td></tr>`
                        ).join('')}</tbody>
                    </table>`;
            } else {
                container.innerHTML = '<div style="padding:8px;color:var(--text-muted);font-size:11px">Sin partidas</div>';
            }
            return data;
        } catch {
            container.innerHTML = '<div style="padding:8px;color:var(--danger);font-size:11px">Error al cargar</div>';
            return null;
        }
    }

    // Buscar disponibilidad
    async function buscarDisponibilidad(pivot = null) {
        if (!currentOT) return;
        const btn = document.getElementById('btn-buscar-disp');
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Buscando...';

        const params = {
            ots_seleccionadas: [currentOT.nro],
            n_tec: parseInt(document.getElementById('p-ntec').value) || 1,
            jornadas: parseFloat(document.getElementById('p-jornadas').value) || 1.0,
            consecutivo: document.getElementById('p-cons').checked,
            viaje: document.getElementById('p-viaje').checked,
            patrones_requeridos: [...selectedPatrones],
            excluir_conflictos_pats: document.getElementById('p-excl-pats').checked,
        };

        const startDate = document.getElementById('p-start-date').value;
        if (startDate && !pivot) {
            params.pivot_date = startDate;
        }

        if (pivot) params.pivot_date = pivot;

        try {
            const endpoint = pivot ? '/api/engine/buscar_siguientes' : '/api/engine/buscar';
            const res = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(params)
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
            const data = await res.json();
            renderResults(data);
            document.getElementById('sched-results').classList.remove('hidden');

            const allOps = [...(data.estrictas || []), ...(data.flexibles || [])];
            if (allOps.length > 0) {
                const lastOp = allOps[allOps.length - 1];
                pivotDate = lastOp.fechas?.[lastOp.fechas.length - 1]?.date || null;
            }
        } catch (e) {
            App.toast('Error al buscar: ' + e.message, 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-magnifying-glass-chart"></i> Buscar Disponibilidad';
        }
    }

    function renderResults(data) {
        selectedOption = null;
        document.getElementById('btn-confirmar-prog').disabled = true;
        renderResultList(document.getElementById('result-list-est'), data.estrictas || [], 'est');
        renderResultList(document.getElementById('result-list-flex'), data.flexibles || [], 'flex');
    }

    function renderResultList(container, opciones, tipo) {
        container.innerHTML = '';
        if (!opciones.length) {
            container.innerHTML = '<div style="font-size:11px;color:var(--text-muted);padding:8px 0">Sin opciones</div>';
            return;
        }
        opciones.forEach((op, i) => {
            const card = document.createElement('div');
            card.className = 'result-card';
            const tecnicos = op.tecnicos.map(t => t.iniciales || t.nombre).join(' · ');
            const fechas = op.fechas.map(f => {
                const d = new Date(f.date + 'T12:00:00');
                return `${d.toLocaleDateString('es-ES', {weekday:'short',day:'numeric',month:'numeric'})} ${fmtH(f.h_start)}–${fmtH(f.h_start + f.h_dur)}`;
            }).join('<br>');
            let alerts = '';
            if (op.tiene_conflictos) alerts += '<span class="alert-badge"><i class="fa-solid fa-triangle-exclamation"></i> Cal.</span>';
            if (op.tiene_conf_patrones) alerts += '<span class="alert-badge pat"><i class="fa-solid fa-tools"></i> Pat.</span>';

            card.innerHTML = `
                <div class="rc-tec"><i class="fa-solid fa-user" style="color:var(--accent);margin-right:5px;font-size:9px"></i>${tecnicos}</div>
                <div class="rc-fecha">${fechas}</div>
                ${alerts ? `<div class="rc-alerts">${alerts}</div>` : ''}`;

            card.addEventListener('click', () => {
                document.querySelectorAll('.result-card').forEach(c => c.classList.remove('selected'));
                card.classList.add('selected');
                selectedOption = { tipo, index: i, op };
                document.getElementById('btn-confirmar-prog').disabled = false;
            });
            container.appendChild(card);
        });
    }

    function fmtH(h) {
        if (h === undefined || h === null || isNaN(h)) return '—';
        return `${String(Math.floor(h)).padStart(2,'0')}:${String(Math.round((h % 1) * 60)).padStart(2,'0')}`;
    }

    // Confirm modal
    function openConfirmModal() {
        if (!selectedOption || !currentOT) return;
        const op = selectedOption.op;
        const serv = document.getElementById('p-serv').value.trim();
        const desc = document.getElementById('p-desc').value.trim();
        const titulo = formatTitle(currentOT, serv);
        const tecnicos = op.tecnicos.map(t => t.nombre).join(', ');

        document.getElementById('modal-confirm-body').innerHTML = `
            <div class="confirm-section">
                <h4>OT a Programar</h4>
                <div class="confirm-row"><span class="label">N° OT</span><strong>OT ${currentOT.nro}</strong></div>
                <div class="confirm-row"><span class="label">Cliente</span>${currentOT.cliente}</div>
            </div>
            <div class="confirm-section">
                <h4>Programación</h4>
                <div class="confirm-row"><span class="label">Técnico(s)</span>${tecnicos}</div>
                ${op.fechas.map(f => {
                    const d = new Date(f.date + 'T12:00:00');
                    const dl = d.toLocaleDateString('es-ES', {weekday:'long',day:'numeric',month:'long'});
                    return `<div class="confirm-row"><span class="label">${dl}</span>${fmtH(f.h_start)} – ${fmtH(f.h_start + f.h_dur)}</div>`;
                }).join('')}
            </div>
            <div class="confirm-section">
                <h4>Evento Calendar</h4>
                <div class="confirm-row"><span class="label">Título</span><strong>${titulo}</strong></div>
                <div class="confirm-row"><span class="label">Patrones</span>${selectedPatrones.join(', ') || 'Ninguno'}</div>
                <div class="confirm-row"><span class="label">Vehículo</span>${document.getElementById('p-vehiculo').value || 'Ninguno'} ${document.getElementById('p-req-vehiculo').checked ? '(Requiere)' : ''}</div>
                <div class="confirm-row"><span class="label">Descripción</span>${desc || '(vacía)'}</div>
            </div>
            ${op.tiene_conflictos ? '<div class="alert-badge" style="display:inline-block;margin-top:6px"><i class="fa-solid fa-triangle-exclamation"></i> Hay solapamientos con eventos no-OT</div>' : ''}`;

        document.getElementById('modal-confirm').classList.remove('hidden');
    }

    async function executeProgramar() {
        if (!selectedOption || !currentOT) return;
        const op = selectedOption.op;
        const serv = document.getElementById('p-serv').value.trim();
        const desc = document.getElementById('p-desc').value.trim();
        const titulo = formatTitle(currentOT, serv);

        const btn = document.getElementById('btn-exec-programar');
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Creando...';
        
        const selVehiculo = document.getElementById('p-vehiculo').value || null;
        const reqVehiculo = document.getElementById('p-req-vehiculo').checked;

        try {
            const createdEvents = [];
            const resultsByDate = {}; // { "YYYY-MM-DD": { event_ids: [], tech_names: [] } }

            // 1. Pre-calcular Tag de iniciales si hay varios técnicos
            const groupInits = op.tecnicos.length > 1 
                ? op.tecnicos.map(t => t.iniciales).sort().join('/') 
                : null;
            const finalTitle = groupInits ? `${titulo} - ${groupInits}` : titulo;

            for (const fdata of op.fechas) {
                if (!resultsByDate[fdata.date]) resultsByDate[fdata.date] = { ids: [], names: [] };

                for (const tec of op.tecnicos) {
                    const techInfo = (window._tecnicos || []).find(t => t.nombre === tec.nombre);
                    if (!techInfo?.correo) { console.warn('Técnico sin correo:', tec.nombre); continue; }
                    
                    const r = await fetch('/api/eventos/crear', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            correo_tecnico: techInfo.correo,
                            titulo: finalTitle,
                            descripcion: desc,
                            fecha: fdata.date,
                            h_start: fdata.h_start,
                            h_dur: fdata.h_dur,
                            patrones: selectedPatrones,
                            ots: [currentOT.nro],
                            vehiculo: selVehiculo,
                            requiere_vehiculo: reqVehiculo
                        })
                    });
                    if (!r.ok) throw new Error(await r.text());
                    
                    const cData = await r.json();
                    if (cData.event) {
                        createdEvents.push(cData.event);
                        resultsByDate[fdata.date].ids.push(cData.event.id);
                        resultsByDate[fdata.date].names.push(tec.nombre);
                    }
                }
            }

            // 2. Registrar Grupos en SQLite si corresponde
            if (op.tecnicos.length > 1) {
                for (const date in resultsByDate) {
                    const g = resultsByDate[date];
                    await fetch('/api/grupos/registrar', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            grupo_id: `backlog-${date}-${currentOT.nro}`,
                            ot_nro: currentOT.nro,
                            fecha: date,
                            event_ids: g.ids,
                            tecnicos: g.names,
                            patrones: selectedPatrones,
                            vehiculo: selVehiculo
                        })
                    });
                }
            }

            document.getElementById('modal-confirm').classList.add('hidden');
            App.toast('✓ Eventos creados y vinculados como grupo', 'success');
            // Actualizar scheduler sin recargar todo
            if (createdEvents.length > 0) App.batchRefreshEvents(createdEvents);
            else App.refresh();
        } catch (e) {
            App.toast('Error al programar: ' + e.message, 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-check"></i> Programar en Calendar';
        }
    }

    function formatTitle(ot, serv) {
        let t = `${ot.nro} (${ot.cliente.substring(0, 22)})`;
        if (serv) t += ` - ${serv}`;
        return t;
    }

    // ─────────────────────────────────
    // CONTEXT D: QUICK CREATE
    // ─────────────────────────────────
    function showQuickCreate(tech, date, hour, otData) {
        showContext('ctx-quick-create');
        const dl = date.toLocaleDateString('es-ES', {weekday:'short', day:'numeric', month:'short'});
        document.getElementById('qc-tech-date').textContent = `${tech.nombre} · ${dl}`;
        document.getElementById('qc-hstart').value = fmtH(hour);
        document.getElementById('qc-hend').value = '16:00';
        document.getElementById('qc-ot').value = otData?.nro || '';
        document.getElementById('qc-client').value = otData?.cliente || '';
        document.getElementById('qc-desc').value = '';

        document.getElementById('btn-create-quick').onclick = async () => {
            const nro = document.getElementById('qc-ot').value.trim();
            const client = document.getElementById('qc-client').value.trim();
            const [sh, sm] = document.getElementById('qc-hstart').value.split(':').map(Number);
            const [eh, em] = document.getElementById('qc-hend').value.split(':').map(Number);
            const hStart = sh + sm / 60;
            const hDur = Math.max(0.5, (eh + em / 60) - hStart);
            const desc = document.getElementById('qc-desc').value.trim();

            const techInfo = (window._tecnicos || []).find(t => t.nombre === tech.nombre);
            if (!techInfo?.correo) { App.toast('Técnico sin correo', 'error'); return; }

            const titulo = nro ? `${nro}${client ? ` (${client.substring(0,20)})` : ''}` : (client || 'Evento sin OT');
            const r = await fetch('/api/eventos/crear', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    correo_tecnico: techInfo.correo,
                    titulo,
                    descripcion: desc,
                    fecha: fmtLocalDate(date),
                    h_start: hStart,
                    h_dur: hDur,
                    patrones: [],
                    ots: nro ? [nro] : []
                })
            });
            if (r.ok) {
                App.toast('Evento creado ✓', 'success');
                const cData = await r.json();
                if (cData?.event) App.refreshSingleEvent(cData.event);
                else App.refresh();
            } else {
                App.toast('Error al crear evento', 'error');
            }
        };
    }

    // ─────────────────────────────────
    // PATRON BADGE HELPERS
    // ─────────────────────────────────
    function updatePatronBadge() {
        const b = document.getElementById('patron-count-badge');
        b.textContent = selectedPatrones.length;
        b.style.display = selectedPatrones.length > 0 ? '' : 'none';
    }

    function updateEditPatronBadge() {
        const b = document.getElementById('edit-patron-count');
        b.textContent = editPatrones.length;
        b.style.display = editPatrones.length > 0 ? '' : 'none';
    }

    // ─────────────────────────────────
    // HELPERS
    // ─────────────────────────────────
    function parseHour(str) {
        if (!str) return 7;
        if (str.includes('T')) {
            const clean = str.replace(/([+-]\d{2}:\d{2}|Z)$/, '');
            const d = new Date(clean);
            return d.getHours() + d.getMinutes() / 60;
        }
        // Día completo: por defecto 07:00
        return 7;
    }

    function fmtLocalDate(d) {
        const y = d.getFullYear();
        const m = String(d.getMonth()+1).padStart(2,'0');
        const day = String(d.getDate()).padStart(2,'0');
        return `${y}-${m}-${day}`;
    }

    // ─────────────────────────────────
    // INIT
    // ─────────────────────────────────
    function init() {
        // Viaje fuerza consecutivos
        document.getElementById('p-viaje').addEventListener('change', e => {
            if (e.target.checked) document.getElementById('p-cons').checked = true;
        });
        document.getElementById('p-cons').addEventListener('change', e => {
            if (!e.target.checked) document.getElementById('p-viaje').checked = false;
        });

        // Buscar disponibilidad
        document.getElementById('btn-buscar-disp').addEventListener('click', () => buscarDisponibilidad());
        document.getElementById('btn-buscar-sig').addEventListener('click', () => buscarDisponibilidad(pivotDate));
        document.getElementById('btn-confirmar-prog').addEventListener('click', openConfirmModal);
        document.getElementById('btn-exec-programar').addEventListener('click', executeProgramar);

        // Edit event
        document.getElementById('btn-edit-event').addEventListener('click', () => {
            if (currentEvent) setEditMode(true);
        });
        document.getElementById('btn-cancel-edit').addEventListener('click', () => setEditMode(false));
        document.getElementById('btn-save-edit').addEventListener('click', saveEventEdit);

        // Gestión de Grupos: Confirmar agregar técnico
        document.getElementById('btn-confirm-add-tech').addEventListener('click', handleAddTechConfirm);

        // Patron modal from edit
        document.getElementById('edit-btn-patrones').addEventListener('click', () => {
            patronModalCaller = 'edit';
            App.openPatronModal(editPatrones);
        });

        // Patron modal from OT scheduler
        document.getElementById('btn-open-patrones').addEventListener('click', () => {
            patronModalCaller = 'ot';
            App.openPatronModal(selectedPatrones);
        });

        // Ver equipos (desde el programador de OTs)
        document.getElementById('btn-ver-equipos').addEventListener('click', () => {
            let ots = [];
            let headerTitle = "Equipos";
            if (currentOT) {
                ots = [currentOT.nro];
                headerTitle = `Equipos — OT ${currentOT.nro}`;
            }
            if (ots.length > 0) showEquiposModal(ots, headerTitle);
        });

        // Ver equipos (desde el detalle del evento)
        const btnDetallesEvent = document.getElementById('ev-btn-detalles');
        if (btnDetallesEvent) {
            btnDetallesEvent.onclick = () => {
                let ots = [];
                let headerTitle = "Equipos";
                if (currentEvent && currentEvent.ots) {
                    ots = currentEvent.ots;
                    headerTitle = `Equipos — OTs ${ots.join(', ')}`;
                } else if (currentEvent) {
                    const fromTitle = (currentEvent.title || '').match(/\d{4,}/g) || [];
                    ots = fromTitle;
                    headerTitle = `Equipos — OTs ${ots.join(', ')}`;
                }
                if (ots.length > 0) showEquiposModal(ots, headerTitle);
            };
        }

        // Individualizar (Split)
        const btnSplit = document.getElementById('btn-split-event');
        if (btnSplit) {
            btnSplit.onclick = () => {
                if (currentEvent) {
                    const calId = currentEvent.calendarId || currentEvent.calendar_id || 'primary';
                    App.splitEvent(currentEvent.id, calId);
                }
            };
        }

        // Modals close
        document.querySelectorAll('.modal-close').forEach(btn => {
            btn.addEventListener('click', () => {
                const id = btn.dataset.modal;
                if (id) document.getElementById(id).classList.add('hidden');
            });
        });
        document.querySelectorAll('.modal-overlay').forEach(overlay => {
            overlay.addEventListener('click', e => {
                if (e.target === overlay) overlay.classList.add('hidden');
            });
        });
    }

    async function showEquiposModal(ots, headerTitle) {
        document.getElementById('modal-equipos-title').textContent = headerTitle;
        document.getElementById('equipos-tbody').innerHTML = '<tr><td colspan="6" style="text-align:center">Cargando...</td></tr>';
        document.getElementById('modal-equipos').classList.remove('hidden');

        try {
            const res = await fetch('/api/ots/batch/partidas', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ nros: ots })
            });
            const data = await res.json();
            document.getElementById('equipos-tbody').innerHTML = (data.equipos || []).map(e =>
                `<tr><td>${e.id}</td><td>${e.serie}</td><td>${e.marca}</td><td>${e.modelo}</td><td>${e.trabajo}</td><td>${e.puntos}</td></tr>`
            ).join('');
        } catch (e) {
            document.getElementById('equipos-tbody').innerHTML = '<tr><td colspan="6" style="text-align:center">Error al cargar datos</td></tr>';
        }
    }

    // Called by app.js when patron modal confirms
    function onPatronesConfirmed(pats) {
        if (patronModalCaller === 'ot') {
            selectedPatrones = pats;
            updatePatronBadge();
        } else {
            editPatrones = pats;
            updateEditPatronBadge();
        }
    }

    return {
        init,
        showEmpty,
        showEventDetail,
        showOTScheduler,
        showQuickCreate,
        onPatronesConfirmed,
        getSelectedPatrones: () => selectedPatrones,
        getCurrentOTs: () => {
            if (currentOT) return [currentOT.nro];
            if (currentEvent && currentEvent.ots) return currentEvent.ots;
            return [];
        }
    };
})();
