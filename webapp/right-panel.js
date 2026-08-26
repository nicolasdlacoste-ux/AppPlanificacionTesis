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
        console.log("[DIAGNOSTIC] showEventDetail: displaying event", ev);
        currentEvent = ev;
        App.logTrace(ev.google_event_id || ev.id, "RIGHTPANEL_SHOW_DETAIL", {
            summary: ev.summary,
            sync_status: ev.sync_status,
            pending_sync: ev.pending_sync,
            extended_props: ev.extended_props
        }, ev.calendar_id);
        showContext('ctx-event');

        // Reset to view mode
        setEditMode(false);

        const title = ev.summary || 'Sin título';
        const elTitle = document.getElementById('ev-title');
        if (elTitle) elTitle.textContent = title;
        const elTec = document.getElementById('ev-tecnico');
        if (elTec) elTec.textContent = ev.tecnico_nombre || '—';

        // Horario
        const sh = parseHour(ev.inicio);
        const eh = parseHour(ev.fin);
        const dateStr = (ev.inicio || '').substring(0, 10);
        const dateFmt = dateStr ? new Date(dateStr + 'T12:00:00').toLocaleDateString('es-ES', {
            weekday: 'short', day: 'numeric', month: 'short'
        }) : '—';
        const elHorario = document.getElementById('ev-horario');
        if (elHorario) elHorario.textContent = `${dateFmt} · ${fmtH(sh)} – ${fmtH(eh)}`;
        
        const direccion = ev.ubicacion || '';
        const elDir = document.getElementById('ev-direccion');
        if (elDir) elDir.textContent = direccion || '—';

        const mapLink = document.getElementById('ev-map-link');
        if (mapLink) {
            if (direccion && direccion !== '—') {
                mapLink.href = `https://www.google.com/maps/dir/?api=1&origin=Mexico+932+CABA&destination=${encodeURIComponent(direccion)}`;
                mapLink.classList.remove('hidden');
            } else {
                mapLink.href = '#';
                mapLink.classList.add('hidden');
            }
        }

        // Técnico(s)
        const tecDiv = document.getElementById('ev-tecnicos-list');
        if (tecDiv) tecDiv.innerHTML = `<span class="tag">${ev.tecnico_nombre || '—'}</span>`;

        // Patrones desde extended_props
        const patronDiv = document.getElementById('ev-patrones');
        try {
            const props = ev.extended_props || {};
            console.log("[DIAGNOSTIC] extended_props in RightPanel:", props);
            const privateProps = props.private || {};
            let rawPats = privateProps.app_patrones || props.app_patrones || [];
            
            let pats = [];
            if (Array.isArray(rawPats)) {
                pats = rawPats;
            } else if (typeof rawPats === 'string') {
                try {
                    pats = JSON.parse(rawPats);
                } catch(e) { pats = []; }
            }

            if (patronDiv) {
                patronDiv.innerHTML = (pats && pats.length)
                    ? pats.map(p => `<span class="tag">${p}</span>`).join('')
                    : '<span style="color:var(--text-muted);font-size:11px">Sin patrones</span>';
            }
        } catch (e) { 
            console.error("Error parsing patterns:", e);
            if (patronDiv) patronDiv.innerHTML = '—'; 
        }

        // Vehiculo
        const vehDiv = document.getElementById('ev-vehiculo');
        try {
            const props = ev.extended_props || {};
            const privateProps = props.private || {};
            const veh = privateProps.app_vehiculo || props.app_vehiculo || null;
            const req = (privateProps.app_requiere_vehiculo || props.app_requiere_vehiculo) === true;
            if (vehDiv) {
                if (veh) {
                    vehDiv.innerHTML = `<span class="tag" style="background:var(--accent);color:white">${veh}</span>` + 
                                       (req ? ` <span style="font-size:10px; color:var(--text-muted); margin-left:4px">[x] Requiere</span>` : '');
                } else {
                    vehDiv.innerHTML = '<span style="color:var(--text-muted);font-size:11px">Sin vehículo</span>';
                }
            }
        } catch(e) { if (vehDiv) vehDiv.innerHTML = '—'; }

        // OTs vinculadas — usar campo canónico
        const otsDiv = document.getElementById('ev-ots');
        let ots = ev.app_ots || [];
        if (typeof ots === 'string') {
            try { ots = JSON.parse(ots); } catch(e) { ots = []; }
        }
        if (!Array.isArray(ots)) ots = [];

        currentEvent.ots = ots; // Guardar para modal de equipos
        
        const btnSF = document.getElementById('btn-ev-sf');
        const partidasTable = document.getElementById('ev-partidas-table');

        if (ots.length > 0) {
            if (otsDiv) otsDiv.innerHTML = ots.map(o => `<span class="tag">${o}</span>`).join('');
            if (partidasTable) loadPartidasEv(ots, partidasTable);
            
            // Lógica botón Salesforce
            if (btnSF) {
                btnSF.classList.remove('hidden');
                btnSF.onclick = () => {
                    if (ots.length === 1) {
                        const backlog = App.getBacklogOTs();
                        const otData = backlog.find(o => o.nro === ots[0]);
                        if (otData && otData.sfid) App.openSFLink(otData.sfid);
                        else App.toast('ID de Salesforce no encontrado', 'info');
                    } else {
                        App.showSFLinksPopup(ots);
                    }
                };
            }
        } else {
            if (otsDiv) otsDiv.innerHTML = '<span style="color:var(--text-muted);font-size:11px">Sin OT asociada</span>';
            if (partidasTable) {
                partidasTable.innerHTML = '<span style="padding:8px;display:block;color:var(--text-muted);font-size:11px">—</span>';
            }
            if (btnSF) btnSF.classList.add('hidden');
        }

        // Edit mode: pre-fill fields
        prefillEditFields(ev);

        // Multi-day warning and split button
        const sRaw = ev.inicio || '';
        const eRaw = ev.fin || '';
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
        
        const hasGuests = ev.extended_props?.private?.has_guests === "true";
        const isComplex = hasGuests;
        
        const elWarning = document.getElementById('ev-multi-warning');
        if (elWarning) {
            elWarning.classList.toggle('hidden', !isComplex);
            if (isComplex) {
                elWarning.innerHTML = `⚠️ Evento complejo (${hasGuests ? "invitados" : "multidía"}). Para editar/mover se recomienda individualizarlo.`;
            }
        }
        const btnSplit = document.getElementById('btn-split-event');
        if (btnSplit) {
            btnSplit.classList.toggle('hidden', !isComplex);
            // Re-vincular botón Individualizar con el evento actual
            btnSplit.onclick = () => {
                const calId = ev.calendar_id || 'primary';
                App.splitEvent(ev.google_event_id, calId);
            };
        }

        // Delete — group-aware
        const btnDelete = document.getElementById('btn-delete-event');
        if (btnDelete) {
            btnDelete.onclick = () => {
                if (confirm(`¿Eliminar "${title}"?`)) App.deleteEvent(ev.google_event_id, ev.calendar_id || 'primary');
            };
        }

        // Duplicar Evento
        const btnDuplicate = document.getElementById('btn-duplicate-event');
        if (btnDuplicate) {
            btnDuplicate.onclick = () => {
                showClonePanel(ev);
            };
        }

        // Edit event - Eventos multidía ahora se pueden editar
        const btnEditEv = document.getElementById('btn-edit-event');
        if (btnEditEv) {
            btnEditEv.classList.remove('hidden');
        }

        // --- GESTIÓN DE GRUPOS: AGREGAR TÉCNICO ---
        const btnAddTech = document.getElementById('btn-add-tech');
        if (btnAddTech) {
            btnAddTech.onclick = () => {
                currentEvent = ev;
                const sel = document.getElementById('st-tech-select');
                const modal = document.getElementById('modal-select-tech');
                if (!sel || !modal) return;
                
                const tecs = window._tecnicos || [];
                // Filtrar los que ya están en el grupo
                const currentTecs = ev._grupo_tecs || [ev.tecnico_nombre];
                const filtered = tecs.filter(t => !currentTecs.includes(t.nombre));
                
                sel.innerHTML = filtered.map(t => `<option value="${t.correo}">${t.nombre}</option>`).join('');
                modal.classList.remove('hidden');
            };
        }

        // Cargar información de grupo si existe
        loadGroupInfo(ev.google_event_id);
    }

    async function loadGroupInfo(eventId) {
        console.log("[DIAGNOSTIC] loadGroupInfo for eventId:", eventId);
        const tecDiv = document.getElementById('ev-tecnicos-list');
        try {
            const res = await fetch(`/api/grupos/evento/${eventId}`);
            const grupo = await res.json();
            console.log("[DIAGNOSTIC] group data received:", grupo);
            
            if (grupo && grupo.grupo_id) {
                // Guardar referencia completa en el evento actual
                if (currentEvent) currentEvent._grupo = grupo;
                currentEvent._grupo_tecs = grupo.calendar_ids || grupo.tecnico_nombres;

                tecDiv.innerHTML = (grupo.calendar_ids || grupo.tecnico_nombres || []).map((idOrName, i) => {
                    const eid = grupo.event_ids[i];
                    const isSelf = eid === currentEvent.google_event_id;
                    const techObj = (window._tecnicos || []).find(t => t.correo === idOrName || t.nombre === idOrName);
                    const name = techObj ? techObj.nombre : idOrName;
                    const tecMail = techObj ? techObj.correo : null;
                    
                    return `
                    <div class="tec-group-item">
                        <span class="tag ${isSelf ? 'self' : 'other'}" ${!isSelf ? `onclick="window.App.flashEvent('${eid}')"` : ''} title="${tecMail||name}">${name}</span>
                        ${tecMail ? `<button class="btn-remove-tech" 
                            onclick="if(confirm('¿Quitar a ${name} de este grupo? Se eliminará su evento de Google Calendar.')) App.quitarTecnicoDeGrupo('${eid}', '${tecMail}')" 
                            title="Quitar del grupo"><i class="fa-solid fa-xmark"></i></button>` : ''}
                    </div>`;
                }).join('');
            } else {
                if (currentEvent) currentEvent._grupo = null;
            }
        } catch (e) {
            if (currentEvent) currentEvent._grupo = null;
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
            const calId = currentEvent.calendar_id || 'primary';
            const res = await fetch(`/api/eventos/${currentEvent.google_event_id}/agregar_tecnico?tecnico_correo=${encodeURIComponent(correo)}&calendar_id=${encodeURIComponent(calId)}`, {
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
            await App.refreshEvents(); 
        } catch (e) {
            console.error('[RightPanel] Error:', e);
            App.toast(e, 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = originalHtml;
        }
    }

    function prefillEditFields(ev) {
        // Título y Descrip
        document.getElementById('edit-titulo').value = ev.summary || '';
        document.getElementById('edit-descripcion').value = ev.descripcion || '';
        document.getElementById('edit-direccion').value = ev.ubicacion || '';

        // Técnico selector
        const sel = document.getElementById('edit-tecnico');
        sel.innerHTML = (window._tecnicos || []).map(t =>
            `<option value="${t.nombre}" data-correo="${t.correo}" ${t.nombre === ev.tecnico_nombre ? 'selected' : ''}>${t.nombre}</option>`
        ).join('');

        // Fecha
        document.getElementById('edit-fecha').value = (ev.inicio || '').substring(0, 10);
        let endVal = (ev.fin || '').substring(0, 10);
        
        // Google Calendar exclusive end dates adjustment
        if (ev._isMultiDay && ev.fin && !ev.fin.includes("T")) {
            const d = new Date(endVal + "T00:00:00");
            d.setDate(d.getDate() - 1); // For display, show the actual last day of the event
            endVal = d.toISOString().substring(0, 10);
        }
        const editFechaFinEl = document.getElementById('edit-fecha-fin');
        if (editFechaFinEl) editFechaFinEl.value = endVal;

        // OTs
        let otsList = ev.app_ots || [];
        if (typeof otsList === 'string') {
            try { otsList = JSON.parse(otsList); } catch(e) { otsList = []; }
        }
        window._editOts = Array.isArray(otsList) ? [...otsList] : [];
        if (typeof renderEditOts === 'function') renderEditOts();

        // Horas
        const sh = parseHour(ev.inicio);
        const eh = parseHour(ev.fin);
        document.getElementById('edit-hstart').value = fmtH(sh);
        document.getElementById('edit-hend').value = fmtH(eh);

        // Patrones
        try {
            const props = ev.extended_props || {};
            const privateProps = props.private || {};
            let rawPats = privateProps.app_patrones || props.app_patrones || [];
            
            // [FIX] Si viene como string JSON (estándar de Google), parsear
            if (typeof rawPats === 'string') {
                try { rawPats = JSON.parse(rawPats); } catch(e) { rawPats = []; }
            }
            editPatrones = Array.isArray(rawPats) ? rawPats : [];
        } catch(e) { editPatrones = []; }
        updateEditPatronBadge();

        // Vehiculos
        const selVeh = document.getElementById('edit-vehiculo');
        if (selVeh) {
            const vehiculos = App.getVehiculos() || [];
            selVeh.innerHTML = '<option value="">Sin vehículo</option>' + vehiculos.map(v => `<option value="${v.nombre}">${v.nombre}</option>`).join('');
            try {
                const props = ev.extended_props || {};
                const privateProps = props.private || {};
                selVeh.value = privateProps.app_vehiculo || props.app_vehiculo || '';
                const elReq = document.getElementById('edit-req-vehiculo');
                if (elReq) elReq.checked = (privateProps.app_requiere_vehiculo || props.app_requiere_vehiculo) === true;
            } catch(e) {}
        }
    }

    function setEditMode(on) {
        const elView = document.getElementById('ev-view-mode');
        const elEdit = document.getElementById('ev-edit-mode');
        const elFooterView = document.getElementById('ev-footer-view');
        const elFooterEdit = document.getElementById('ev-footer-edit');

        if (elView) elView.classList.toggle('hidden', on);
        if (elEdit) elEdit.classList.toggle('hidden', !on);
        if (elFooterView) elFooterView.classList.toggle('hidden', on);
        if (elFooterEdit) elFooterEdit.classList.toggle('hidden', !on);
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
        } catch(e) {
            container.innerHTML = '<div style="padding:8px;color:var(--text-muted);font-size:11px">No hay datos de partidas</div>';
        }
    }

    // ─────────────────────────────────────────────────────────
    // HELPER: Modal confirmación de acción de grupo
    // ─────────────────────────────────────────────────────────
    function showGroupActionModal(msg, grupo, onSolo, onAll, onCancel) {
        const elMsg = document.getElementById('modal-group-msg');
        if (elMsg) elMsg.innerHTML = msg;
        
        // Mostrar miembros del grupo
        const membersDiv = document.getElementById('modal-group-members');
        if (membersDiv) {
            membersDiv.innerHTML = (grupo.calendar_ids || grupo.tecnico_nombres || []).map(idOrName => {
                const name = ((window._tecnicos || []).find(t => t.correo === idOrName || t.nombre === idOrName) || {}).nombre || idOrName;
                return `<span class="tag" style="background:var(--surface-alt);font-size:11px;">${name}</span>`;
            }).join(' ');
        }

        const modal = document.getElementById('modal-group-action');
        if (!modal) return;

        const btnSolo = document.getElementById('btn-group-solo');
        const btnAll  = document.getElementById('btn-group-all');
        if (!btnSolo || !btnAll) return;

        // Mostrar/ocultar botón "Todo el grupo" según contexto
        btnAll.classList.toggle('hidden', !onAll);

        // Limpiar handlers anteriores clonando los botones
        const newSolo = btnSolo.cloneNode(true);
        const newAll  = btnAll.cloneNode(true);
        btnSolo.parentNode.replaceChild(newSolo, btnSolo);
        btnAll.parentNode.replaceChild(newAll, btnAll);

        let resolved = false;

        newSolo.addEventListener('click', () => {
            resolved = true;
            modal.classList.add('hidden');
            if (onSolo) onSolo();
        });
        if (onAll) {
            newAll.addEventListener('click', () => {
                resolved = true;
                modal.classList.add('hidden');
                onAll();
            });
        }

        const cancelBtns = modal.querySelectorAll('.modal-close');
        cancelBtns.forEach(btn => {
            const newBtn = btn.cloneNode(true);
            btn.parentNode.replaceChild(newBtn, btn);
            newBtn.addEventListener('click', () => {
                if (!resolved) {
                    resolved = true;
                    modal.classList.add('hidden');
                    if (onCancel) onCancel();
                }
            });
        });

        // Click on overlay to cancel
        modal.onclick = (e) => {
            if (e.target === modal && !resolved) {
                resolved = true;
                modal.classList.add('hidden');
                if (onCancel) onCancel();
            }
        };

        modal.classList.remove('hidden');
    }


    // Save event edits — group-aware
    async function saveEventEdit() {
        if (!currentEvent) return;
        
        const priv = currentEvent.extended_props ? currentEvent.extended_props.private : {};
        const isComplex = priv && priv.has_guests === "true";
        if (isComplex) {
            App.toast("No se puede editar eventos con invitados externos. Individualice primero.", "warning");
            return;
        }
        
        const btn = document.getElementById('btn-save-edit');
        if (!btn) return;

        try {
            btn.disabled = true;
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';

            const sel = document.getElementById('edit-tecnico');
            const selectedOpt = sel ? sel.options[sel.selectedIndex] : null;
            const newTecnico = sel ? sel.value : '';
            const correoDest = (selectedOpt && selectedOpt.dataset.correo) || newTecnico;
            const newDate = document.getElementById('edit-fecha')?.value || '';
            const newHstart = document.getElementById('edit-hstart')?.value || '07:00';
            const newHend = document.getElementById('edit-hend')?.value || '16:00';
            const newTitulo = document.getElementById('edit-titulo')?.value.trim() || '';
            const newDesc = document.getElementById('edit-descripcion')?.value.trim() || '';
            const newDireccion = document.getElementById('edit-direccion')?.value.trim() || '';

            const [sh, sm] = newHstart.split(':').map(Number);
            const [eh, em] = newHend.split(':').map(Number);
            const hStartF = sh + sm / 60;
            const hEndF = eh + em / 60;

            const oldCalId = currentEvent.calendar_id || correoDest;
            const selVehiculo = document.getElementById('edit-vehiculo')?.value;
            const reqVehiculo = document.getElementById('edit-req-vehiculo')?.checked || false;
            const editFechaFinEl = document.getElementById('edit-fecha-fin');
            const newDateEnd = editFechaFinEl ? editFechaFinEl.value : '';

            // Validar vehículo
            const gid = currentEvent.extended_props?.private?.grupo_id || null;
            const techName = selectedOpt ? selectedOpt.text : 'Técnico';
            const conflict = App.checkVehicleConflicts(selVehiculo, newDate, hStartF, hEndF, currentEvent.google_event_id, techName, gid);
            if (conflict) App.toast(conflict, 'warning');

            function _formatDescriptionLocal(base, patrones, vehiculo) {
                let cleanBase = base || "";
                if (cleanBase.includes("──────────")) cleanBase = cleanBase.split("──────────")[0].trim();
                let meta = [];
                if (patrones && patrones.length) meta.push(`🛠️ Patrones: ${patrones.join(', ')}`);
                if (vehiculo) meta.push(`🚐 Vehículo: ${vehiculo}`);
                if (!meta.length) return cleanBase;
                return `${cleanBase}\n\n─────────────────────────────────────────────\n${meta.join('\n')}\n─────────────────────────────────────────────`.trim();
            }

            const origDate = (currentEvent.inicio || '').substring(0, 10);
            const origStart = parseHour(currentEvent.inicio);
            const origEnd   = parseHour(currentEvent.fin);

            const correoDestL = correoDest ? correoDest.toLowerCase() : '';
            const oldCalIdL = oldCalId ? oldCalId.toLowerCase() : '';
            const cambioTecnico = correoDestL && correoDestL !== oldCalIdL;
            let origDateEnd = (currentEvent.fin || '').substring(0, 10);
            if (currentEvent._isMultiDay && currentEvent.fin && !currentEvent.fin.includes('T')) {
                const d = new Date(origDateEnd + 'T00:00:00');
                d.setDate(d.getDate() - 1);
                origDateEnd = d.toISOString().substring(0, 10);
            }

            const cambioFechaHora = (newDate !== origDate) || (newDateEnd !== origDateEnd) ||
                Math.abs(hStartF - origStart) > 0.01 ||
                Math.abs(hEndF   - origEnd)   > 0.01;

            const grupo = currentEvent._grupo;
            const esDeGrupo = grupo && grupo.grupo_id;

            const payload = {
                event_id: currentEvent.google_event_id,
                calendar_id_origen: oldCalId,
                correo_destino: correoDest,
                nueva_fecha: newDate,
                nueva_fecha_fin: newDateEnd || null,
                h_start: hStartF,
                h_dur: hEndF - hStartF,
                titulo: newTitulo,
                descripcion: newDesc,
                direccion: newDireccion,
                patrones: editPatrones || [],
                ots: window._editOts || [],
                vehiculo: selVehiculo,
                requiere_vehiculo: reqVehiculo
            };

            const _ph = (h) => `${String(Math.floor(h)).padStart(2,'0')}:${String(Math.round((h%1)*60)).padStart(2,'0')}:00`;
            const origPrivate = ((currentEvent.extended_props || {}).private) || {};
            const newPrivate = {
                ...origPrivate,
                app_patrones: JSON.stringify(editPatrones || []),
                app_vehiculo: selVehiculo || '',
                app_requiere_vehiculo: reqVehiculo ? 'true' : 'false',
            };

            async function _doMove(endpoint) {
                btn.disabled = true;
                let _apiSuccess = false;  // [BUG1-FIX] Track if API call succeeded
                if (currentEvent) {
                    currentEvent._syncing = true;
                    const gid = currentEvent.extended_props?.private?.grupo_id || currentEvent._grupo?.grupo_id;
                    if (gid) App.setGroupSyncing(gid, true);
                    else App.refreshSingleEvent(currentEvent);
                }
                try {
                    // [EVENT_MOVE] move_started
                    App.logTrace(currentEvent.google_event_id || currentEvent.id, "move_started", {
                        endpoint: endpoint,
                        old_tecnico: currentEvent.tecnico_nombre,
                        new_tecnico: techName,
                        new_calendar: correoDest
                    }, currentEvent.calendar_id, "EVENT_MOVE");

                    App.logTrace(currentEvent.google_event_id || currentEvent.id, "RIGHTPANEL_SAVE_START", {
                        endpoint: endpoint,
                        payload: payload
                    }, currentEvent.calendar_id);

                    const eid = currentEvent.google_event_id || currentEvent.id;
                    const r = await fetch(`/api/eventos/${eid}/${endpoint}`, {
                        method: 'PATCH',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });

                    App.logTrace(currentEvent.google_event_id || currentEvent.id, "RIGHTPANEL_SAVE_RESPONSE", {
                        ok: r.ok,
                        status: r.status
                    }, currentEvent.calendar_id);

                    if (!r.ok) {
                        const errText = await r.text();
                        let errMsg = errText;
                        try { 
                            let parsed = JSON.parse(errText);
                            errMsg = (typeof parsed.detail === 'string') ? parsed.detail : JSON.stringify(parsed.detail || parsed);
                        } catch(_) {}
                        throw new Error(errMsg);
                    }

                    const rData = await r.json();
                    _apiSuccess = true;
                    App.toast('Evento actualizado ✓', 'success');
                    setEditMode(false);

                    // [BUG1-FIX] Aplicar cambios desde el servidor, no desde el objeto stale.
                    // Si el response incluye group_snapshot (operaciones grupales), usarlo.
                    // Si no, actualizar el evento individual con los datos que conocemos + los del server.
                    if (rData.group_snapshot) {
                        App.applyGroupSnapshot(rData.group_snapshot);
                        // Auto-refresh grupal para capturar cualquier cambio residual
                        await App.refreshEvents();
                    } else {
                        const newId = rData.event_id || currentEvent.id;
                        if (newId !== currentEvent.id) {
                            App.removeSingleEvent(currentEvent.id);
                        }
                        let finalInicio = `${newDate}T${_ph(hStartF)}-03:00`;
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
                            descripcion: _formatDescriptionLocal(newDesc, editPatrones, selVehiculo),
                            ubicacion: newDireccion,
                            extended_props: { ...(currentEvent.extended_props || {}), private: newPrivate },
                            _syncing: false
                        });
                        if (esDeGrupo) {
                            await App.refreshEvents();
                        }
                    }

                    App.logTrace(currentEvent.google_event_id || currentEvent.id, "frontend_state_updated", {
                        event_id: currentEvent.google_event_id,
                        used_snapshot: !!rData.group_snapshot
                    }, currentEvent.calendar_id, "EVENT_MOVE");

                } catch (e) {
                    App.toast(e, 'error');
                } finally {
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Guardar';
                    try {
                        if (currentEvent) {
                            const gid = currentEvent.extended_props?.private?.grupo_id || currentEvent._grupo?.grupo_id;
                            // [BUG1-FIX] Solo limpiar flags. NO llamar refreshSingleEvent con currentEvent (datos stale).
                            // El refresh visual ya fue hecho en el try block exitoso.
                            if (gid) App.setGroupSyncing(gid, false);
                            currentEvent._syncing = false;
                            if (!_apiSuccess) {
                                // Solo si falló la API: limpiar el flag de syncing sin actualizar datos
                                const evInList = App.getEventos().find(e => e.google_event_id === currentEvent.google_event_id);
                                if (evInList) {
                                    evInList._syncing = false;
                                    App.refreshSingleEvent(evInList);
                                }
                            }
                        }
                    } catch (err) { console.error(err); }
                }
            }

            async function _doMoveGrupo() {
                btn.disabled = true;
                let _apiSuccess = false;  // [BUG1-FIX]
                if (currentEvent) {
                    currentEvent._syncing = true;
                    const gid = currentEvent.extended_props?.private?.grupo_id || currentEvent._grupo?.grupo_id;
                    if (gid) App.setGroupSyncing(gid, true);
                    else App.refreshSingleEvent(currentEvent);
                }
                try {
                    const r = await fetch(`/api/eventos/${currentEvent.google_event_id}/mover_grupo`, {
                        method: 'PATCH',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });
                    if (!r.ok) {
                        const errText = await r.text();
                        let errMsg = errText;
                        try { 
                            let parsed = JSON.parse(errText);
                            errMsg = (typeof parsed.detail === 'string') ? parsed.detail : JSON.stringify(parsed.detail || parsed);
                        } catch(_) {}
                        throw new Error(errMsg);
                    }
                    const rData = await r.json();
                    _apiSuccess = true;
                    const count = (grupo && grupo.tecnico_nombres) ? grupo.tecnico_nombres.length : '?';
                    App.toast(`Grupo actualizado ✓ (${count} eventos)`, 'success');
                    setEditMode(false);

                    // [BUG1-FIX + AUTO-REFRESH] Aplicar snapshot y hacer refresh completo.
                    // El snapshot aplica inmediatamente (sin esperar /api/eventos completo).
                    if (rData.group_snapshot) {
                        App.applyGroupSnapshot(rData.group_snapshot);
                    }
                    // Refresh completo para capturar títulos actualizados y cualquier cambio residual
                    await App.refreshEvents();
                } catch (e) {
                    App.toast(e, 'error');
                } finally {
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Guardar';
                    try {
                        if (currentEvent) {
                            const gid = currentEvent.extended_props?.private?.grupo_id || currentEvent._grupo?.grupo_id;
                            // [BUG1-FIX] Solo limpiar flags. NO refreshSingleEvent con datos stale.
                            if (gid) App.setGroupSyncing(gid, false);
                            currentEvent._syncing = false;
                        }
                    } catch (err) { console.error(err); }
                }
            }

            // ── ROUTING DE LA ACCIÓN ─────────────────────────────────────────
            const cambioDia = newDate !== origDate;
            if (esDeGrupo && cambioTecnico && cambioDia) {
                App.toast('No se puede cambiar fecha y técnico a la vez en un evento de grupo.', 'error');
                btn.disabled = false;
                btn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Guardar';
                return;
            }
            // Cambio de técnico: solo el miembro editado (aunque cambie la hora el mismo día).
            if (esDeGrupo && cambioTecnico) {
                await _doMove('mover');
            } else if (esDeGrupo) {
                await _doMoveGrupo();
            } else {
                await _doMove('mover');
            }


        } catch (error) {
            console.error('[saveEventEdit] Critical error:', error);
            App.toast('Error inesperado al iniciar el guardado: ' + error.message, 'error');
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

        const servicios = App.getServicios() || [];
        const selSrv = document.getElementById('p-restringir-servicio');
        if (selSrv) {
            selSrv.innerHTML = '<option value="">Todos los servicios (Sin filtro)</option>' + 
                servicios.map(s => `<option value="${s}">${s}</option>`).join('');
            
            // Valor por defecto
            if (servicios.includes('Calibraciones')) {
                selSrv.value = 'Calibraciones';
            }
        }

        const tecnicos = App.getState()._tecnicos || [];
        const selTecFiltro = document.getElementById('p-tec-filtro');
        if (selTecFiltro) {
            selTecFiltro.innerHTML = '<option value="">-- Sin preferencia --</option>' + 
                tecnicos.map(t => `<option value="${t.nombre}">${t.nombre}</option>`).join('');
            document.getElementById('p-tec-op').value = 'Contiene';
        }

        document.getElementById('sched-ot-title').textContent = `OT ${ot.nro}`;
        document.getElementById('sched-ot-cliente').textContent = ot.cliente;
        
        const dirText = ot.direccion || '';
        const elDir = document.getElementById('sched-ot-direccion');
        if (elDir) elDir.textContent = dirText || '—';
        
        const mapLink = document.getElementById('sched-ot-map-link');
        if (mapLink) {
            if (dirText && dirText !== '—') {
                mapLink.href = `https://www.google.com/maps/dir/?api=1&origin=Mexico+932+CABA&destination=${encodeURIComponent(dirText)}`;
                mapLink.classList.remove('hidden');
            } else {
                mapLink.href = '#';
                mapLink.classList.add('hidden');
            }
        }

        const btnSF = document.getElementById('btn-ot-sf');
        if (ot.sfid) {
            btnSF.classList.remove('hidden');
            btnSF.onclick = () => App.openSFLink(ot.sfid);
        } else {
            btnSF.classList.add('hidden');
        }
        document.getElementById('sched-results').classList.add('hidden');
        document.getElementById('btn-confirmar-prog').disabled = true;
        selectedPatrones = [];
        updatePatronBadge();

        loadPartidas(ot.nro, document.getElementById('sched-partidas-table'))
            .then(data => {
                if (data) {
                    const elTotal = document.getElementById('sched-partidas-total');
                    if (elTotal) {
                        elTotal.textContent = `Total: ${data.total_partidas} partida${data.total_partidas !== 1 ? 's' : ''}`;
                    }
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
        } catch(e) {
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
            servicio_requerido: document.getElementById('p-restringir-servicio') ? document.getElementById('p-restringir-servicio').value : null,
            tecnico_op: document.getElementById('p-tec-op') ? document.getElementById('p-tec-op').value : null,
            tecnico_filtro: document.getElementById('p-tec-filtro') ? document.getElementById('p-tec-filtro').value : null
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
            // Auto-scroll a resultados
            setTimeout(() => {
                document.getElementById('sched-results').scrollIntoView({ behavior: 'smooth', block: 'start' });
            }, 100);
        } catch (e) {
            App.toast(e, 'error');
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
        const direccion = currentOT.direccion || '';
        const titulo = formatTitle(currentOT, serv);
        const tecnicos = op.tecnicos.map(t => t.nombre).join(', ');

        document.getElementById('modal-confirm-body').innerHTML = `
            <div class="confirm-section">
                <h4>OT a Programar</h4>
                <div class="confirm-row">
                    <span class="label">N° OT</span>
                    <strong>OT ${currentOT.nro}</strong>
                    ${currentOT.sfid ? `<a href="https://akribis.lightning.force.com/lightning/r/WorkOrder/${currentOT.sfid}/view" target="_blank" style="margin-left:10px; color:#00a1e0; font-size:11px; text-decoration:none;"><i class="fa-solid fa-up-right-from-square"></i> Abrir SF</a>` : ''}
                </div>
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
                <div class="confirm-row"><span class="label">Dirección</span>${direccion || '(vacía)'}</div>
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
        const direccion = currentOT.direccion || '';
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

            const pCons = document.getElementById('p-cons');
            const pViaje = document.getElementById('p-viaje');
            const isConsecutivo = (pCons && pCons.checked) || (pViaje && pViaje.checked);
            let groupedFechas = op.fechas;
            if (isConsecutivo && op.fechas.length > 1) {
                const first = op.fechas[0];
                const last = op.fechas[op.fechas.length - 1];
                groupedFechas = [{
                    date: first.date,
                    fecha_fin: last.date,
                    h_start: first.h_start,
                    h_dur: first.h_dur
                }];
            }

            for (const fdata of groupedFechas) {
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
                            direccion: direccion,
                            fecha: fdata.date,
                            fecha_fin: fdata.fecha_fin || null,
                            h_start: fdata.h_start,
                            h_dur: fdata.h_dur,
                            patrones: selectedPatrones,
                            ots: [currentOT.nro],
                            vehiculo: selVehiculo,
                            requiere_vehiculo: reqVehiculo
                        })
                    });
                    if (!r.ok) {
                        const errText = await r.text();
                        let errMsg = errText;
                        try { 
                            let parsed = JSON.parse(errText);
                            errMsg = (typeof parsed.detail === 'string') ? parsed.detail : JSON.stringify(parsed.detail || parsed);
                        } catch(_) {}
                        throw new Error(errMsg);
                    }
                    
                    const cData = await r.json();
                    // La API devuelve los campos en el root (id, event_id, title, start, end...)
                    const eventPayload = cData.event || cData;
                    if (eventPayload?.google_event_id) {
                        createdEvents.push(eventPayload);
                        resultsByDate[fdata.date].ids.push(eventPayload.google_event_id);
                        resultsByDate[fdata.date].names.push(techInfo.correo);
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
            else await App.refreshEvents();
        } catch (e) {
            App.toast(e, 'error');
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
        document.getElementById('qc-direccion').value = otData?.direccion || '';
        document.getElementById('qc-desc').value = '';

        document.getElementById('btn-create-quick').onclick = async () => {
            const btn = document.getElementById('btn-create-quick');
            if (btn.disabled) return;
            btn.disabled = true;
            const origHtml = btn.innerHTML;
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Creando...';
            
            const nro = document.getElementById('qc-ot').value.trim();
            const client = document.getElementById('qc-client').value.trim();
            const [sh, sm] = document.getElementById('qc-hstart').value.split(':').map(Number);
            const [eh, em] = document.getElementById('qc-hend').value.split(':').map(Number);
            const hStart = sh + sm / 60;
            const hDur = Math.max(0.5, (eh + em / 60) - hStart);
            const desc = document.getElementById('qc-desc').value.trim();
            const direccion = document.getElementById('qc-direccion').value.trim();
            const dateEndInput = document.getElementById('qc-date-end').value;

            const techInfo = (window._tecnicos || []).find(t => t.nombre === tech.nombre);
            if (!techInfo?.correo) { App.toast('Técnico sin correo', 'error'); return; }

            const titulo = nro ? `${nro}${client ? ` (${client.substring(0,20)})` : ''}` : (client || 'Evento sin OT');
            
            const payload = {
                correo_tecnico: techInfo.correo,
                titulo,
                descripcion: desc,
                direccion: direccion,
                fecha: fmtLocalDate(date),
                h_start: hStart,
                h_dur: hDur,
                patrones: [],
                ots: nro ? [nro] : []
            };
            
            if (dateEndInput) {
                payload.fecha_fin = dateEndInput;
            }

            const r = await fetch('/api/eventos/crear', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (r.ok) {
                App.toast('Evento creado ✓', 'success');
                const cData = await r.json();
                // La API devuelve los campos en el root (id, event_id, title, start, end...)
                const eventPayload = cData.event || cData;
                if (eventPayload?.google_event_id) App.refreshSingleEvent(eventPayload);
                else await App.refreshEvents();
                showContext('ctx-empty');
            } else {
                const errText = await r.text();
                let errMsg = errText;
                try { 
                    let parsed = JSON.parse(errText);
                    errMsg = (typeof parsed.detail === 'string') ? parsed.detail : JSON.stringify(parsed.detail || parsed);
                } catch(_) {}
                App.toast('Error al crear evento: ' + errMsg, 'error');
            }
            
            btn.disabled = false;
            btn.innerHTML = origHtml;
        };
    }

    function showClonePanel(ev) {
        showContext('ctx-clone');
        
        let tituloSinTag = ev.summary || ev.evento || '';
        tituloSinTag = tituloSinTag.replace(/\s*-\s*[A-Z0-9/]+\s*$/, '').trim();
        
        document.getElementById('clone-subtitle').textContent = `Clonando: ${tituloSinTag.substring(0,25)}...`;
        document.getElementById('clone-titulo').value = tituloSinTag;
        
        // Fecha = mañana
        const nextDay = new Date();
        nextDay.setDate(nextDay.getDate() + 1);
        document.getElementById('clone-fecha').value = fmtLocalDate(nextDay);
        
        document.getElementById('clone-hstart').value = parseHour(ev.inicio) ? fmtH(parseHour(ev.inicio)) : '07:00';
        document.getElementById('clone-hend').value = parseHour(ev.fin) ? fmtH(parseHour(ev.fin)) : '16:00';
        document.getElementById('clone-direccion').value = ev.ubicacion || '';
        document.getElementById('clone-ots').value = (ev.ots || []).join(', ');
        
        // Clean description from metadata appended by backend
        let desc = ev.descripcion || '';
        if (desc.includes('──────────')) desc = desc.split('──────────')[0].trim();
        document.getElementById('clone-desc').value = desc;

        document.getElementById('btn-cancel-clone').onclick = () => {
            showContext('ctx-empty');
        };

        document.getElementById('btn-save-clone').onclick = async () => {
            const btn = document.getElementById('btn-save-clone');
            if (btn.disabled) return;
            btn.disabled = true;
            const origHtml = btn.innerHTML;
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Guardando...';
            
            try {
                const titulo = document.getElementById('clone-titulo').value.trim();
                const fecha = document.getElementById('clone-fecha').value;
                const [sh, sm] = document.getElementById('clone-hstart').value.split(':').map(Number);
                const [eh, em] = document.getElementById('clone-hend').value.split(':').map(Number);
                const hStart = sh + sm / 60;
                const hDur = Math.max(0.5, (eh + em / 60) - hStart);
                const direccion = document.getElementById('clone-direccion').value.trim();
                const otsInput = document.getElementById('clone-ots').value;
                const descInput = document.getElementById('clone-desc').value.trim();

                const ots = otsInput ? otsInput.split(',').map(s => s.trim()).filter(s => s) : [];

                const payload = {
                    correo_tecnico: ev.calendar_id, // mantemos al mismo técnico
                    titulo: titulo || 'Evento Clonado',
                    descripcion: descInput,
                    direccion: direccion,
                    fecha: fecha,
                    h_start: hStart,
                    h_dur: hDur,
                    patrones: [], // Desestimar metadata compleja según requerimiento
                    ots: ots
                };

                const r = await fetch('/api/eventos/crear', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                
                if (r.ok) {
                    App.toast('Evento clonado exitosamente ✓', 'success');
                    const cData = await r.json();
                    const eventPayload = cData.event || cData;
                    if (eventPayload?.google_event_id) App.refreshSingleEvent(eventPayload);
                    else await App.refreshEvents();
                    showContext('ctx-empty');
                } else {
                    const errText = await r.text();
                    let errMsg = errText;
                    try { 
                        let parsed = JSON.parse(errText);
                        errMsg = (typeof parsed.detail === 'string') ? parsed.detail : JSON.stringify(parsed.detail || parsed);
                    } catch(_) {}
                    App.toast('Error al clonar evento: ' + errMsg, 'error');
                }
            } catch (error) {
                App.toast('Error de red: ' + error.message, 'error');
            } finally {
                btn.disabled = false;
                btn.innerHTML = origHtml;
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
        const pViaje = document.getElementById('p-viaje');
        const pCons = document.getElementById('p-cons');
        if (pViaje && pCons) {
            pViaje.addEventListener('change', e => {
                if (e.target.checked) pCons.checked = true;
            });
            pCons.addEventListener('change', e => {
                if (!e.target.checked) pViaje.checked = false;
            });
        }

        // Buscar disponibilidad
        const btnBuscarDisp = document.getElementById('btn-buscar-disp');
        if (btnBuscarDisp) btnBuscarDisp.addEventListener('click', () => buscarDisponibilidad());
        const btnBuscarSig = document.getElementById('btn-buscar-sig');
        if (btnBuscarSig) btnBuscarSig.addEventListener('click', () => buscarDisponibilidad(pivotDate));
        const btnConfirmar = document.getElementById('btn-confirmar-prog');
        if (btnConfirmar) btnConfirmar.addEventListener('click', openConfirmModal);
        const btnExec = document.getElementById('btn-exec-programar');
        if (btnExec) btnExec.addEventListener('click', executeProgramar);

        // Edit event
        const btnEditEv = document.getElementById('btn-edit-event');
        if (btnEditEv) {
            btnEditEv.addEventListener('click', () => {
                if (currentEvent) setEditMode(true);
            });
        }
        const btnCancelEdit = document.getElementById('btn-cancel-edit');
        if (btnCancelEdit) btnCancelEdit.addEventListener('click', () => setEditMode(false));
        const btnSaveEdit = document.getElementById('btn-save-edit');
        if (btnSaveEdit) btnSaveEdit.addEventListener('click', saveEventEdit);

        const btnAddOt = document.getElementById('btn-add-ot');
        if (btnAddOt) {
            btnAddOt.addEventListener('click', () => {
                const input = document.getElementById('edit-new-ot');
                if (!input) return;
                let val = input.value.trim().toUpperCase();
                if (!val) return;
                
                // Si el usuario pega algo como "OT 12345" o "12345 (Cliente)", extraemos el número
                const match = val.match(/\b([0-9]{4,})\b/);
                if (match) val = match[1];

                const backlog = App.getBacklogOTs() || [];
                const otData = backlog.find(o => o.nro === val);

                if (!otData) {
                    App.toast(`Error: La OT ${val} no fue encontrada en el backlog.`, 'error');
                    return;
                }

                // Validar que el cliente coincida si ya hay OTs
                if (window._editOts && window._editOts.length > 0 && otData && otData.cliente) {
                    const firstOtData = backlog.find(o => o.nro === window._editOts[0]);
                    const existingClient = firstOtData ? firstOtData.cliente : null;
                    
                    if (existingClient && otData.cliente !== existingClient) {
                        App.toast(`Error: La OT ${val} es de "${otData.cliente}", pero el evento pertenece a "${existingClient}".`, 'error');
                        return;
                    }
                }

                input.value = '';

                if (!window._editOts.includes(val)) {
                    window._editOts.push(val);
                    if (typeof renderEditOts === 'function') renderEditOts();
                    if (typeof updateTitleFromOts === 'function') updateTitleFromOts();
                }
            });
        }

        // Validación de conflictos en vivo
        ['edit-vehiculo', 'edit-fecha', 'edit-hstart', 'edit-hend', 'edit-tecnico'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('change', validateEditConflicts);
        });

        // Gestión de Grupos: Confirmar agregar técnico
        const btnConfirmAddTech = document.getElementById('btn-confirm-add-tech');
        if (btnConfirmAddTech) btnConfirmAddTech.addEventListener('click', handleAddTechConfirm);

        // Patron modal from edit
        const btnEditPats = document.getElementById('edit-btn-patrones');
        if (btnEditPats) {
            btnEditPats.addEventListener('click', () => {
                patronModalCaller = 'edit';
                App.openPatronModal(editPatrones);
            });
        }

        // Patron modal from OT scheduler
        const btnOpenPats = document.getElementById('btn-open-patrones');
        if (btnOpenPats) {
            btnOpenPats.addEventListener('click', () => {
                patronModalCaller = 'ot';
                App.openPatronModal(selectedPatrones);
            });
        }

        // Ver equipos (desde el programador de OTs)
        const btnVerEquipos = document.getElementById('btn-ver-equipos');
        if (btnVerEquipos) {
            btnVerEquipos.addEventListener('click', () => {
                let ots = [];
                let headerTitle = "Equipos";
                if (currentOT) {
                    ots = [currentOT.nro];
                    headerTitle = `Equipos — OT ${currentOT.nro}`;
                }
                if (ots.length > 0) showEquiposModal(ots, headerTitle);
            });
        }

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
                    const fromTitle = (currentEvent.summary || '').match(/\d{4,}/g) || [];
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
                    const calId = currentEvent.calendar_id || 'primary';
                    App.splitEvent(currentEvent.google_event_id, calId);
                }
            };
        }

        // Modals close
        document.querySelectorAll('.modal-close').forEach(btn => {
            btn.addEventListener('click', () => {
                const id = btn.dataset.modal;
                if (id) {
                    const modal = document.getElementById(id);
                    if (modal) modal.classList.add('hidden');
                }
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
            validateEditConflicts();
        }
    }

    function validateEditConflicts() {
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
    }

    window.removeEditOt = function(val) {
        if (!window._editOts) return;
        window._editOts = window._editOts.filter(o => o !== val);
        if (typeof renderEditOts === 'function') renderEditOts();
        if (typeof updateTitleFromOts === 'function') updateTitleFromOts();
    };

    function updateTitleFromOts() {
        const tituloInput = document.getElementById('edit-titulo');
        if (!tituloInput) return;

        if (!window._editOts || window._editOts.length === 0) {
            // Si no hay OTs, no limpiamos el título, pero podríamos dejar solo las iniciales.
            return;
        }

        const backlog = App.getBacklogOTs() || [];
        
        let clienteFinal = null;
        for (let otNro of window._editOts) {
            let d = backlog.find(o => o.nro === otNro);
            if (d && d.cliente) {
                clienteFinal = d.cliente;
                break;
            }
        }

        const joinedOts = window._editOts.join(' / ');
        let titleBase = clienteFinal ? `${joinedOts} (${clienteFinal})` : joinedOts;

        let currentTitle = tituloInput.value.trim();
        if (currentTitle.includes(" - ")) {
            const lastDashIdx = currentTitle.lastIndexOf(" - ");
            const iniciales = currentTitle.substring(lastDashIdx);
            tituloInput.value = `${titleBase}${iniciales}`;
        } else {
            tituloInput.value = titleBase;
        }
    }

    function renderEditOts() {
        const container = document.getElementById('edit-ots-list');
        if (!container) return;
        if (!window._editOts || window._editOts.length === 0) {
            container.innerHTML = '<span style="color:var(--text-muted);font-size:11px">Sin OT vinculada</span>';
            return;
        }
        container.innerHTML = window._editOts.map(o => `
            <span class="tag" style="background:var(--accent);color:white">
                ${o}
                <button onclick="removeEditOt('${o}')" style="background:none;border:none;color:white;margin-left:5px;cursor:pointer;">
                    <i class="fa-solid fa-xmark"></i>
                </button>
            </span>
        `).join('');
    }

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
    }, 500);

    return {
        init,
        showEmpty,
        showEventDetail,
        showOTScheduler,
        showQuickCreate,
        showGroupActionModal,
        showBatchMode, updateBatchUI,
        onPatronesConfirmed,
        renderEditOts, // Expuesta por si acaso
        getSelectedPatrones: () => selectedPatrones,
        getCurrentEvent: () => currentEvent,
        getCurrentOTs: () => {
            if (currentOT) return [currentOT.nro];
            if (currentEvent && currentEvent.ots) return currentEvent.ots;
            return [];
        }
    };
})();