// ════════════════════════════════════════
// APP — Main Orchestrator
// Akrimet Planner v2.0
// ════════════════════════════════════════

const App = (() => {
    let _tecnicos = [];
    let _eventos = [];
    let _ots = [];
    let _patrones = [];
    let _vehiculos = [];
    let _holidays = {};
    let _servicios = [];
    let _patronModalCallback = null;
    let _isBatchMode = false;
    let _batchSelected = new Set();
    let _batchTecnico = null;
    let _localMutationTime = Date.now() / 1000;
    // ─────────────────────────────────
    // TRACEABILITY
    // ─────────────────────────────────
    async function logTrace(eventId, step, detail, calendarId = null) {
        try {
            await fetch('/api/trace', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    event_id: eventId,
                    step: step,
                    detail: detail,
                    calendar_id: calendarId
                })
            });
        } catch (e) {
            console.error("[TRACE] Failed to send trace log", e);
        }
    }

    // ─────────────────────────────────
    // BOOT
    // ─────────────────────────────────
    async function init() {
        console.log("[BOOT] Iniciando App.init()...");
        RightPanel.init();
        Backlog.init();
        bindNavButtons();
        bindPatronModal();
        bindPanelToggles();
        bindEmptySpaceClick();
        console.log("[BOOT] Inicializando ConfigMenu...");
        ConfigMenu.init();
        
        console.log("[BOOT] Inicializando PollManager...");
        PollManager.init();
        
        console.log("[BOOT] Inicializando DriftManager...");
        if (typeof DriftManager !== 'undefined') DriftManager.init();
        
        const scrollArea = document.getElementById('scheduler-scroll-area');
        const techLabels = document.getElementById('tech-labels-col');
        if (scrollArea && techLabels) {
            scrollArea.addEventListener('scroll', () => {
                techLabels.scrollTop = scrollArea.scrollTop;
            });
        }

        initPanelResizer();
        initTarjetaSalida();

        // 1. Identificar usuario (no bloqueante)
        console.log("[BOOT] Llamando a initUserChip()...");
        initUserChip(); 

        // 2. Cargar datos (bloqueante)
        console.log("[BOOT] Llamando a loadAll()...");
        await loadAll();
        console.log("[BOOT] loadAll() completado. Seteando vista...");
        Scheduler.setView('week');
        
        startHeartbeat();
        
        setInterval(() => {
            console.log('[AutoSync] Ejecutando sincronización de 60 minutos...');
        }, 60 * 60 * 1000);
    }

    async function refresh() {
        await loadAll();
        Scheduler.render();
    }

    // ─────────────────────────────────
    // IDENTIDAD DE USUARIO
    // ─────────────────────────────────
    async function initUserChip() {
        console.log("[BOOT] initUserChip: Buscando elementos de identidad...");
        const chip    = document.getElementById('user-chip');
        const avatar  = document.getElementById('user-avatar');
        const emailEl = document.getElementById('user-email');
        const btnOut  = document.getElementById('btn-logout');
        if (!chip) {
            console.warn("[BOOT] initUserChip: No se encontró 'user-chip', abortando identificación visual.");
            return;
        }

        try {
            console.log("[BOOT] initUserChip: Fetching /api/auth/me...");
            // Timeout de 5s para evitar bloqueos en el arranque
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 5000);

            const res = await fetch('/api/auth/me', { signal: controller.signal });
            clearTimeout(timeoutId);
            const profile = await res.json();

            if (profile.email) {
                const parts = (profile.nombre || '').split(' ');
                const initials = parts.length >= 2
                    ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
                    : profile.email.substring(0, 2).toUpperCase();

                if (avatar) avatar.textContent = initials;
                if (emailEl) emailEl.textContent = profile.email;
                chip.title = `Conectado como ${profile.nombre || profile.email}`;

                if (_tecnicos.length === 0) {
                    console.log('[Auth] Usuario detectado.');
                }
            } else {
                if (avatar) avatar.textContent = '?';
                if (emailEl) emailEl.textContent = 'Sin sesión';
                chip.title = 'No autenticado';
            }
        } catch (e) {
            console.warn("[BOOT] initUserChip Error:", e.message);
            if (avatar) avatar.textContent = '?';
            if (emailEl) emailEl.textContent = 'Sin sesión';
        }

        if (btnOut) {
            btnOut.addEventListener('click', async () => {
                if (!confirm('¿Desconectar la cuenta de Google?\nDeberás volver a autenticarte la próxima vez que sincronices.')) return;
                try {
                    await fetch('/api/auth/logout', { method: 'POST' });
                    if (avatar) avatar.textContent = '?';
                    if (emailEl) emailEl.textContent = 'Sin sesión';
                    if (chip) chip.title = '';
                    toast('Cuenta desconectada. Sincronizá para volver a conectar.', 'info');
                } catch (e) {
                    toast('Error al desconectar: ' + e.message, 'error');
                }
            });
        }
    }

    // ─────────────────────────────────
    // SYNC: TARGETED REFRESH HELPERS
    // ─────────────────────────────────

    /** Recarga SOLO los eventos desde SQLite (~1 petición vs 5 del refresh completo). */
    async function refreshEvents() {
        console.trace("[UI_FORENSICS] refreshEvents() invocado - Posible causa de Shadow Events o sobreescritura de cache");
        try {
            const evRes = await fetch(`/api/eventos?t=${Date.now()}`);
            if (!evRes.ok) return;
            const newEvents = await evRes.json();
            console.log("[DIAGNOSTIC] First event from /api/eventos:", newEvents[0]);
            const merged = [];
            for (let i = 0; i < newEvents.length; i++) {
                const incoming = newEvents[i];
                let local = null;
                for (let j = 0; j < _eventos.length; j++) {
                    // [CANONICAL_MIGRATION] ev.id -> ev.google_event_id
                    if (_eventos[j].google_event_id === incoming.google_event_id && _eventos[j].calendar_id === incoming.calendar_id) { local = _eventos[j]; break; }
                }
                
                // Conservar metadatos de UI que no vienen de /api/eventos directamente
                if (local) {
                    if (local._grupo) incoming._grupo = local._grupo;
                    if (local._grupo_tecs) incoming._grupo_tecs = local._grupo_tecs;
                }

                if (local && local._syncing) merged.push(local);
                else merged.push(incoming);
            }
            for (let j = 0; j < _eventos.length; j++) {
                const local = _eventos[j];
                if (local._syncing) {
                    let found = false;
                    for (let k = 0; k < merged.length; k++) {
                        // [CANONICAL_MIGRATION] ev.id -> ev.google_event_id
                        if (merged[k].google_event_id === local.google_event_id && merged[k].calendar_id === local.calendar_id) { found = true; break; }
                    }
                    if (!found) merged.push(local);
                }
            }
            _eventos = merged;
            Scheduler.setState({ tecnicos: _tecnicos, eventos: _eventos, holidays: _holidays });
            Scheduler.render();
            Backlog.render(_ots, _eventos);
            updateFooter();
        } catch (e) {
            console.error('[RefreshEvents]', e);
        }
    }

    /**
     * Actualiza o inserta un evento en memoria y re-renderiza.
     * Evita recargar todos los datos cuando solo cambió un evento.
     */
    function refreshSingleEvent(eventData) {
        console.trace(`[UI_FORENSICS] refreshSingleEvent() invocado para: ${eventData.google_event_id}`);
        console.log("[DIAGNOSTIC] refreshSingleEvent received:", eventData);
        // [CANONICAL_MIGRATION] ev.id -> ev.google_event_id
        const idx = _eventos.findIndex(e => e.google_event_id === eventData.google_event_id && e.calendar_id === eventData.calendar_id);
        if (idx !== -1) {
            const current = _eventos[idx];
            if (eventData.version !== undefined && current.version !== undefined && eventData.version < current.version) {
                console.warn("[Sync] Ignorando update obsoleto para " + eventData.google_event_id);
                return;
            }
            _eventos[idx] = eventData;
        } else {
            // Asegurar que el evento tenga el campo tecnico_nombre para el scheduler
            if (!eventData.tecnico_nombre && (eventData.correo_tecnico || eventData.calendar_id)) {
                const tech = _tecnicos.find(t => t.correo === eventData.correo_tecnico || t.id === eventData.calendar_id);
                if (tech) eventData.tecnico_nombre = tech.nombre;
            }
            _eventos.push(eventData);
        }
        Scheduler.setState({ tecnicos: _tecnicos, eventos: _eventos, holidays: _holidays });
        Scheduler.render();
        Backlog.render(_ots, _eventos);
        updateFooter();
    }

    /**
     * Aplica un group_snapshot proveniente de la respuesta del servidor.
     * Parchea _eventos con los datos actualizados de cada miembro del grupo
     * sin necesidad de un round-trip completo a /api/eventos.
     * 
     * @param {Object} snapshot  - { grupo_id, members: [...], group_version, correlation_id }
     */
    function applyGroupSnapshot(snapshot) {
        if (!snapshot || !snapshot.members || !snapshot.members.length) return;
        console.log(`[GROUP_SNAPSHOT] Aplicando snapshot para grupo ${snapshot.grupo_id}, ${snapshot.members.length} miembros`);

        let changed = false;
        for (const member of snapshot.members) {
            const idx = _eventos.findIndex(e =>
                e.google_event_id === member.google_event_id
                || e.google_event_id === member.id
                || e.id === member.id
            );
            if (idx !== -1) {
                const current = _eventos[idx];
                // Aplicar campos actualizados conservando campos no incluidos en el snapshot
                _eventos[idx] = {
                    ...current,
                    tecnico_nombre: member.tecnico_nombre ?? current.tecnico_nombre,
                    calendar_id:    member.calendar_id    ?? current.calendar_id,
                    inicio:         member.inicio          ?? current.inicio,
                    fin:            member.fin             ?? current.fin,
                    summary:        member.summary         ?? current.summary,
                    sync_status:    member.sync_status     ?? current.sync_status,
                    version:        member.version         ?? current.version,
                    _syncing:       false,
                };
                changed = true;
            }
        }

        if (changed) {
            Scheduler.setState({ tecnicos: _tecnicos, eventos: [..._eventos], holidays: _holidays });
            Scheduler.render();
            Backlog.render(_ots, _eventos);
            updateFooter();
        }
    }

    /** Marca todos los eventos de un grupo como 'sincronizando' para feedback visual inmediato. */
    function setGroupSyncing(grupoId, syncing) {
        if (!grupoId) return;
        let changed = false;
        _eventos.forEach(ev => {
            if (!ev) return;
            // [CANONICAL_MIGRATION] extendedProperties -> extended_props
            const gid = ev.extended_props?.private?.grupo_id || ev._grupo?.grupo_id;
            if (gid === grupoId) {
                ev._syncing = syncing;
                changed = true;
            }
        });
        if (changed) {
            Scheduler.setState({ tecnicos: _tecnicos, eventos: _eventos, holidays: _holidays });
            Scheduler.render();
        }
    }

    /** Elimina un evento de memoria y re-renderiza. Sin round-trip al servidor. */
    function removeSingleEvent(eventId, calendarId) {
        // [CANONICAL_MIGRATION] ev.id -> ev.google_event_id
        _eventos = _eventos.filter(e => !(e.google_event_id === eventId && e.calendar_id === calendarId));
        Scheduler.setState({ tecnicos: _tecnicos, eventos: _eventos, holidays: _holidays });
        Scheduler.render();
        Backlog.render(_ots, _eventos);
        updateFooter();
    }

    /** Inserta múltiples eventos de golpe (ej: tras programar una OT multi-jornada). */
    function batchRefreshEvents(newEvents) {
        console.trace(`[UI_FORENSICS] batchRefreshEvents() invocado para ${newEvents.length} eventos`);
        newEvents.forEach(ev => {
            // [CANONICAL_MIGRATION] ev.id -> ev.google_event_id
            const idx = _eventos.findIndex(e => e.google_event_id === ev.google_event_id && e.calendar_id === ev.calendar_id);
            if (idx !== -1) _eventos[idx] = ev;
            else _eventos.push(ev);
        });
        Scheduler.setState({ tecnicos: _tecnicos, eventos: _eventos, holidays: _holidays });
        Scheduler.render();
        Backlog.render(_ots, _eventos);
        updateFooter();
    }



    function startHeartbeat() {
        const sendPulse = async () => {
            try {
                const res = await fetch('/api/heartbeat', { method: 'POST' });
                if (res.ok) {
                    const data = await res.json();
                    if (data.last_mutation_time && data.last_mutation_time > _localMutationTime) {
                        console.log(`[Heartbeat] Backend mutation detected (Local: ${_localMutationTime}, Server: ${data.last_mutation_time}). Refreshing...`);
                        _localMutationTime = data.last_mutation_time;
                        // Evitar refresh si hay una acción global en curso (para no sobreescribir estados optimistas)
                        if (typeof _globalSyncing === 'undefined' || !_globalSyncing) {
                            refreshEvents();
                            if (window.PollManager && typeof window.PollManager.fetchPollStatus === 'function') {
                                window.PollManager.fetchPollStatus();
                            }
                        }
                    }
                }
            } catch (e) {}
        };

        // Enviar un "latido" al servidor cada 15 segundos
        setInterval(sendPulse, 15000);
        
        // Pulso extra al volver a enfocar la ventana (evita cierres tras hibernación/background)
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible') {
                console.log('[Heartbeat] Ventana activa, enviando pulso de rescate...');
                sendPulse();
            }
        });
        
        sendPulse(); // Primer pulso inmediato
    }

    // ─────────────────────────────────
    // PANEL RESIZER
    // ─────────────────────────────────
    function initPanelResizer() {
        const resizer = document.getElementById('right-resizer');
        const panel = document.getElementById('right-panel');
        let isResizing = false;

        if (!resizer || !panel) return;

        resizer.addEventListener('mousedown', e => {
            isResizing = true;
            document.body.style.cursor = 'col-resize';
            resizer.classList.add('active');
            e.preventDefault();
        });

        document.addEventListener('mousemove', e => {
            if (!isResizing) return;

            const newWidth = window.innerWidth - e.clientX;
            
            // Límites de seguridad
            if (newWidth >= 250 && newWidth <= 600) {
                document.documentElement.style.setProperty('--right-w', newWidth + 'px');
            }
        });

        document.addEventListener('mouseup', () => {
            if (isResizing) {
                isResizing = false;
                document.body.style.cursor = '';
                resizer.classList.remove('active');
            }
        });
    }

    async function loadAll() {
        console.log("[BOOT] loadAll: Iniciando carga masiva de datos...");
        try {
            const endpoints = [
                { id: 'tecnicos', url: `/api/tecnicos?t=${Date.now()}` },
                { id: 'eventos',  url: `/api/eventos?t=${Date.now()}` },
                { id: 'ots',      url: `/api/ots/pendientes?t=${Date.now()}` },
                { id: 'patrones', url: `/api/patrones?t=${Date.now()}` },
                { id: 'vehiculos',url: `/api/vehiculos?t=${Date.now()}` },
                { id: 'config',   url: `/api/config?t=${Date.now()}` }
            ];

            console.log("[BOOT] loadAll: Ejecutando peticiones...");
            const results = await Promise.all(endpoints.map(async (ep) => {
                const start = Date.now();
                try {
                    // Timeout de 15s para cada petición individual
                    const controller = new AbortController();
                    const timeoutId = setTimeout(() => controller.abort(), 15000);

                    const res = await fetch(ep.url, { signal: controller.signal });
                    clearTimeout(timeoutId);
                    
                    if (!res.ok) {
                        console.error(`[NETWORK] ! Error en ${ep.id}: Status ${res.status}`);
                        return { id: ep.id, ok: false, status: res.status };
                    }
                    
                    const data = await res.json();
                    return { id: ep.id, ok: true, data };
                } catch (err) {
                    console.error(`[NETWORK] !! Error en ${ep.id}:`, err.message);
                    return { id: ep.id, ok: false, error: err.message };
                }
            }));

            // Validar críticos (Técnicos y Eventos)
            const tecsRes = results.find(r => r.id === 'tecnicos');
            const evsRes  = results.find(r => r.id === 'eventos');

            if (!tecsRes?.ok || !evsRes?.ok) {
                const reason = !tecsRes?.ok ? 'técnicos' : 'eventos';
                console.error(`[BOOT] loadAll: Fallo crítico en ${reason}`);
                throw new Error(`No se pudo cargar la información de ${reason}`);
            }

            // Asignar datos con fallbacks seguros
            _tecnicos = tecsRes.data || [];
            _eventos  = evsRes.data || [];
            console.log("[DIAGNOSTIC] loadAll _eventos count:", _eventos.length);
            if (_eventos.length > 0) console.log("[DIAGNOSTIC] loadAll sample event:", _eventos[0]);
            
            _ots      = results.find(r => r.id === 'ots')?.data || [];
            _patrones = results.find(r => r.id === 'patrones')?.data || [];
            _vehiculos= results.find(r => r.id === 'vehiculos')?.data || [];
            
            const configRes = results.find(r => r.id === 'config');
            _holidays = (configRes?.ok && configRes.data?.holidays) ? configRes.data.holidays : {};
            _servicios = (configRes?.ok && configRes.data?.services) ? configRes.data.services : [];

            console.log(`[BOOT] loadAll: Datos listos -> Tecs: ${_tecnicos.length}, Evs: ${_eventos.length}`);

            window._tecnicos = _tecnicos;
            
            // Instrumentar logs literal como fue solicitado:
            const scheduler = Scheduler;
            console.log("[DEBUG scheduler object]", scheduler);
            console.log("[DEBUG scheduler keys]", Object.keys(scheduler || {}));
            console.log("[DEBUG setState]", typeof scheduler?.setState);

            if (typeof Scheduler.assignColors === 'function') {
                Scheduler.assignColors(_tecnicos);
            } else {
                console.error("[CRITICAL] Scheduler.assignColors is not a function!", Scheduler);
            }
            
            Scheduler.setState({ tecnicos: _tecnicos, eventos: _eventos, holidays: _holidays });
            Backlog.render(_ots, _eventos);
            updateFooter();
        } catch (e) {
            toast('Error al cargar datos: ' + e.message, 'error');
            console.error(e);
        }
    }

    // ─────────────────────────────────
    // EVENT SELECTION
    // ─────────────────────────────────
    function toggleBatchMode() {
        _isBatchMode = !_isBatchMode;
        _batchSelected.clear();
        _batchTecnico = null;
        
        const btn = document.getElementById('btn-batch-mode');
        if (btn) btn.classList.toggle('active', _isBatchMode);
        if (btn) btn.style.backgroundColor = _isBatchMode ? 'var(--accent)' : '';
        
        if (_isBatchMode) {
            RightPanel.showBatchMode();
        } else {
            RightPanel.showEmpty();
        }
        Scheduler.render();
    }

    function selectEvent(ev, ctrlPressed = false) {
        if (ctrlPressed && !_isBatchMode) {
            toggleBatchMode(); // esto activa el modo batch
            
            // Añadir el evento actual del panel derecho (si hay uno y es del mismo técnico)
            const currentEv = RightPanel.getCurrentEvent ? RightPanel.getCurrentEvent() : null;
            if (currentEv && (currentEv.calendar_id === ev.calendar_id)) {
                let evsToToggle = [currentEv.google_event_id];
                if (currentEv._grupo && currentEv._grupo.event_ids) {
                    evsToToggle = currentEv._grupo.event_ids;
                }
                evsToToggle.forEach(id => _batchSelected.add(id));
                _batchTecnico = currentEv.calendar_id;
            }
        }

        if (_isBatchMode) {
            let myTec = ev.calendar_id;
            if (_batchSelected.size === 0) {
                _batchTecnico = myTec;
                _batchSelected.add(ev.google_event_id);
            } else if (myTec !== _batchTecnico) {
                toast('Solo puedes seleccionar eventos del mismo técnico en Modo Batch.', 'warning');
                return;
            }
            
            let evsToToggle = [ev.google_event_id];
            if (ev._grupo && ev._grupo.event_ids) {
                evsToToggle = ev._grupo.event_ids;
            }
            
            const isSelected = _batchSelected.has(ev.google_event_id);
            if (isSelected) {
                evsToToggle.forEach(id => _batchSelected.delete(id));
                if (_batchSelected.size === 0) _batchTecnico = null;
            } else {
                evsToToggle.forEach(id => _batchSelected.add(id));
            }
            
            RightPanel.updateBatchUI(Array.from(_batchSelected));
            Scheduler.render();
        } else {
            RightPanel.showEventDetail(ev);
        }
    }

    function openQuickCreate(tech, date, hour, otData) {
        RightPanel.showQuickCreate(tech, date, hour, otData);
    }

    async function moveEvent(eventId, calendarId, destCorreo, nuevaFecha, hora) {
        // Consultar si es grupo antes de mover
        let grupoInfo = null;
        try {
            const res = await fetch(`/api/grupos/evento/${eventId}`);
            if (res.ok) {
                const g = await res.json();
                if (g && g.grupo_id) grupoInfo = g;
            }
        } catch (e) {}

        console.log("moveEvent IN:", {eventId, calendarId, destCorreo, nuevaFecha, hora});
        if (_globalSyncing) {
            toast('Operación en curso, por favor espera...', 'warning');
            return;
        }
        const eventIdx = _eventos.findIndex(e => (e.google_event_id === eventId || e.id === eventId) && (e.calendar_id || 'primary') === (calendarId || 'primary'));
        console.log("moveEvent MATCH:", {eventIdx});
        if (eventIdx === -1 || _eventos[eventIdx]._syncing) {
             console.warn("Event not found or syncing", {eventId, calendarId, foundIdx: eventIdx});
             return;
        }
        _globalSyncing = true;
        const currentEvent = _eventos[eventIdx];
        const destTec = _tecnicos.find(t => t.correo === destCorreo);
        const nuevoTecNombre = destTec ? destTec.nombre : currentEvent.tecnico_nombre;

        // [EVENT_MOVE] move_started (Drag & Drop)
        logTrace(eventId, "move_started", {
            origin: "drag_drop",
            old_tecnico: currentEvent.tecnico_nombre,
            new_tecnico: nuevoTecNombre,
            new_calendar: destCorreo,
            new_date: nuevaFecha
        }, calendarId, "EVENT_MOVE");

        // Función interna que hace el trabajo
        const doMove = async (scope) => {
            // Guardar estado original para posible rollback
            const originalEventsCopy = JSON.parse(JSON.stringify(_eventos));

            // --- ACTUALIZACIÓN OPTIMISTA ---
            const applyOptimistic = (evToModify) => {
                const isDraggedMember = evToModify.google_event_id === eventId || evToModify.id === eventId;
                if (isDraggedMember && destCorreo) {
                    evToModify.calendar_id = destCorreo;
                    evToModify.tecnico_nombre = nuevoTecNombre;
                }

                if (nuevaFecha) {
                    const sTime = evToModify.inicio ? evToModify.inicio.substring(10) : 'T08:00:00';
                    const eTime = evToModify.fin ? evToModify.fin.substring(10) : 'T10:00:00';
                    evToModify.inicio = nuevaFecha + sTime;
                    evToModify.fin = nuevaFecha + eTime;
                    evToModify._dayStr = nuevaFecha;
                }
                
                // sh/eh solo aplican al evento arrastrado si vino con hora en vista diaria
                if (hora !== undefined && (evToModify.google_event_id === eventId || evToModify.id === eventId)) {
                    const duration = evToModify._eh - evToModify._sh;
                    evToModify._sh = hora;
                    evToModify._eh = hora + (duration > 0 ? duration : 1);
                    const fmtH = (h) => {
                        const integer = Math.floor(h);
                        const minutes = Math.round((h - integer) * 60);
                        return `T${String(integer).padStart(2,'0')}:${String(minutes).padStart(2,'0')}:00`;
                    };
                    const baseDate = evToModify.inicio ? evToModify.inicio.substring(0, 10) : nuevaFecha;
                    evToModify.inicio = baseDate + fmtH(evToModify._sh);
                    evToModify.fin = baseDate + fmtH(evToModify._eh);
                }
                evToModify._syncing = true;
            };

            if (scope === 'grupo' && grupoInfo) {
                grupoInfo.event_ids.forEach(eid => {
                    const idx = _eventos.findIndex(e => e.google_event_id === eid || e.id === eid);
                    if (idx !== -1) applyOptimistic(_eventos[idx]);
                });
            } else {
                applyOptimistic(_eventos[eventIdx]);
            }

            Scheduler.setState({ tecnicos: _tecnicos, eventos: [..._eventos], holidays: _holidays });
            Scheduler.render();

            // [EVENT_MOVE] local_update_success
            logTrace(eventId, "local_update_success", {
                scope: scope,
                new_tecnico: nuevoTecNombre,
                new_calendar: destCorreo
            }, calendarId, "EVENT_MOVE");

            // --- LLAMADA API ---
            const endpoint = scope === 'grupo' ? 'mover_grupo' : 'mover';

            try {
                const res = await fetch(`/api/eventos/${eventId}/${endpoint}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        event_id: eventId,
                        calendar_id_origen: calendarId,
                        correo_destino: destCorreo,
                        nueva_fecha: nuevaFecha,
                        h_start: hora
                    })
                });
                if (!res.ok) throw new Error(await res.text());
                const data = await res.json();

                // [EVENT_MOVE] mutation_enqueued
                logTrace(eventId, "mutation_enqueued", {
                    endpoint: endpoint,
                    operation: "UPDATE"
                }, calendarId, "EVENT_MOVE");

                toast('Evento movido ✓', 'success');
                
                // Limpiar flag de sincronización inmediatamente
                const clearFlags = () => {
                    const idsToClear = (scope === 'grupo' && grupoInfo)
                        ? grupoInfo.event_ids
                        : [eventId];
                    idsToClear.forEach(eid => {
                        const ev = _eventos.find(e => e.google_event_id === eid || e.id === eid);
                        if (ev) delete ev._syncing;
                    });
                };
                clearFlags();
                
                // [EVENT_MOVE] frontend_state_updated
                logTrace(eventId, "frontend_state_updated", {
                    event_id: eventId
                }, calendarId, "EVENT_MOVE");

                Scheduler.render(); // Refrescar para quitar overlays de syncing

                // Si la API dice que el ID cambió (fallback delete+insert)
                // Forzamos refresh para capturar cambios por auto-agrupación (grupo_id, títulos con tags)
                if (data.event_id && data.event_id !== eventId) {
                    const ev = _eventos.find(e => e.google_event_id === eventId && e.calendar_id === calendarId);
                    if (ev) ev.google_event_id = data.event_id;
                }
                await refreshEvents();
            } catch (e) {
                // --- ROLLBACK ---
                _eventos = originalEventsCopy;
                Scheduler.setState({ tecnicos: _tecnicos, eventos: [..._eventos], holidays: _holidays });
                Scheduler.render();
                toast(`Error al mover: ${e.message}`, 'error');
            } finally {
                _globalSyncing = false;
            }
        };

        if (grupoInfo) {
            const destCorreoL = destCorreo ? destCorreo.toLowerCase() : '';
            const calendarIdL = calendarId ? calendarId.toLowerCase() : '';
            const cambioTecnico = destCorreoL && destCorreoL !== calendarIdL;
            const currentDate = currentEvent.inicio ? currentEvent.inicio.substring(0, 10) : "";
            const cambioFecha = nuevaFecha && currentDate && nuevaFecha !== currentDate;
            
            if (cambioTecnico && cambioFecha) {
                toast('No se puede cambiar fecha y técnico a la vez en un evento de grupo.', 'error');
                _globalSyncing = false;
                Scheduler.render();
                return;
            }
            // Solo técnico: un miembro (mover). Solo fecha: todo el grupo (mover_grupo).
            await doMove(cambioTecnico && !cambioFecha ? 'solo' : 'grupo');
        } else {
            await doMove('solo');
        }
    }

    async function deleteEvent(eventId, calendarId) {
        if (!calendarId) { toast('Sin calendar ID para eliminar', 'error'); return; }
        if (!confirm('¿Estás seguro de que deseas eliminar este evento de Google Calendar?')) return;
        
        _globalSyncing = true;

        // ── Actualización optimista: quitar de memoria ANTES de que responda el servidor
        removeSingleEvent(eventId, calendarId);
        RightPanel.showEmpty();

        try {
            const res = await fetch(
                `/api/eventos/${eventId}?calendar_id=${encodeURIComponent(calendarId)}`,
                { method: 'DELETE' }
            );
            if (!res.ok) throw new Error(await res.text());
            toast('Evento eliminado ✓', 'success');
        } catch (e) {
            // Rollback: recargar eventos desde el servidor
            toast('Error al eliminar: ' + e.message, 'error');
            await refreshEvents();
        } finally {
            _globalSyncing = false;
        }
    }

    async function splitEvent(eventId, calendarId) {
        if (!confirm('¿Deseas individualizar este evento? Se creará uno independiente por cada día.')) return;
        _globalSyncing = true;
        try {
            const res = await fetch(`/api/eventos/${eventId}/split?calendar_id=${encodeURIComponent(calendarId)}`, {
                method: 'POST'
            });
            if (!res.ok) throw new Error(await res.text());
            const data = await res.json();
            toast('Evento individualizado ✓', 'success');
            RightPanel.showEmpty();
            // El split puede generar N nuevos eventos con distintos IDs
            // refreshEvents trae todos desde SQLite (ya están ahí porque el backend es DB-first)
            await refreshEvents();
        } catch (e) {
            toast('Error al dividir: ' + e.message, 'error');
        } finally {
            _globalSyncing = false;
        }
    }

    async function quitarTecnicoDeGrupo(eventId, calendarId) {
        _globalSyncing = true;
        // Borrado optimista local
        removeSingleEvent(eventId, calendarId);
        RightPanel.showEmpty();

        try {
            const res = await fetch(`/api/eventos/${eventId}/quitar_tecnico?calendar_id=${encodeURIComponent(calendarId)}`, {
                method: 'POST'
            });
            if (!res.ok) throw new Error(await res.text());
            toast('Técnico desasignado ✓', 'success');
            // Refresh para asegurar consistencia del título del grupo
            await refreshEvents();
        } catch (e) {
            toast('Error al quitar técnico: ' + e.message, 'error');
        } finally {
            _globalSyncing = false;
        }
    }

    // ─────────────────────────────────
    // NAVIGATION BUTTONS
    // ─────────────────────────────────
    function bindNavButtons() {
        const btnPrev = document.getElementById('btn-prev');
        const btnNext = document.getElementById('btn-next');
        const btnToday = document.getElementById('btn-today');
        const btnViewDay = document.getElementById('btn-view-day');
        const btnViewWeek = document.getElementById('btn-view-week');
        const chkSoloOts = document.getElementById('chk-solo-ots');
        const btnViewRes = document.getElementById('btn-view-resources');
        const chkExpandPats = document.getElementById('chk-expand-pats');

        if (btnPrev) btnPrev.addEventListener('click', () => Scheduler.navigate(-1));
        if (btnNext) btnNext.addEventListener('click', () => Scheduler.navigate(1));
        if (btnToday) btnToday.addEventListener('click', () => Scheduler.goToday());
        
        const btnBatch = document.getElementById('btn-batch-mode');
        if (btnBatch) btnBatch.addEventListener('click', toggleBatchMode);

        if (btnViewDay) btnViewDay.addEventListener('click', () => Scheduler.setView('day'));
        if (btnViewWeek) btnViewWeek.addEventListener('click', () => Scheduler.setView('week'));
        
        if (chkSoloOts) {
            chkSoloOts.addEventListener('change', e => {
                logTrace("SYSTEM", "FILTER_SOLO_OTS", { checked: e.target.checked });
                Scheduler.setState({ soloOTs: e.target.checked });
                Scheduler.render();
            });
        }
        
        if (btnViewRes) {
            btnViewRes.addEventListener('click', () => {
                const isRes = Scheduler.toggleResourceMode();
                btnViewRes.classList.toggle('active-blue', isRes);
                
                // Mostrar toggle de expandir
                const lblExpand = document.getElementById('lbl-expandir-pats');
                if (lblExpand) lblExpand.style.display = isRes ? 'flex' : 'none';
                
                // Auto cerrar/abrir panel izquierdo simulando click para mantener estado
                const lp = document.getElementById('left-panel');
                const leftCol = lp ? lp.classList.contains('collapsed') : false;
                const toggleLeft = document.getElementById('toggle-left');
                
                if (isRes && !leftCol && toggleLeft) {
                    toggleLeft.click();
                } else if (!isRes && leftCol && toggleLeft) {
                    toggleLeft.click();
                }
            });
        }
        
        if (chkExpandPats) {
            chkExpandPats.addEventListener('change', e => {
                Scheduler.setState({ expandPats: e.target.checked });
                Scheduler.render();
            });
        }
    }

    function showConfirmModal(opts) {
        // opts: title, html, onConfirm()
        document.getElementById('confirmModalLabel').textContent = opts.title || 'Confirmar Acción';
        document.getElementById('confirmModalBody').innerHTML = opts.html || '';
        document.getElementById('modal-confirm-overlay').classList.remove('hidden');
        
        const btnConfirm = document.getElementById('btn-confirm-action');
        // Quitar listeners previos
        const newBtn = btnConfirm.cloneNode(true);
        btnConfirm.parentNode.replaceChild(newBtn, btnConfirm);

        newBtn.onclick = () => {
            if (opts.onConfirm) opts.onConfirm();
            document.getElementById('modal-confirm-overlay').classList.add('hidden');
        };
    }

    // ─────────────────────────────────
    // VISIBILITY/EXPORTS
    // ─────────────────────────────────
    function getVehiculos() { return _vehiculos; }
    
    function checkVehicleConflicts(vehiculoNombre, dateStr, sh, eh, evId, techNombre, grupoId = null) {
        if (!vehiculoNombre) return null;
        
        const veh = _vehiculos.find(v => v.nombre === vehiculoNombre);
        if (!veh) return null;
        
        const techInfo = _tecnicos.find(t => t.nombre === techNombre);
        const techCorreo = techInfo ? techInfo.correo : null;
        
        // Si no se pasó grupoId explícitamente, intentar obtenerlo del evento actual
        if (!grupoId && evId) {
            const evTarget = _eventos.find(e => e.google_event_id === evId && e.calendar_id === techCorreo);
            if (evTarget && evTarget.extended_props && evTarget.extended_props.private) {
                grupoId = evTarget.extended_props.private.grupo_id;
            }
        }

        // Formatear dateStr si es Date
        const getStr = d => {
            if (typeof d === 'string') return d.substring(0, 10);
            return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
        };
        const targetDate = getStr(dateStr);
        
        // Todos los eventos del mismo día (excluyendo el propio)
        const sameDayEvents = _eventos.filter(ev => {
            if (ev.google_event_id === evId) return false;
            const props = (ev.extended_props && ev.extended_props.private) || {};
            if (props.app_vehiculo !== vehiculoNombre) return false;
            const evSh = ev.inicio || "";
            const evEh = ev.fin || "";
            if (!evSh || !evEh) return false;
            return getStr(evSh) <= targetDate && getStr(evEh) >= targetDate;
        });

        // Regla NUEVA: Verificar si EL TÉCNICO tiene asignado OTRO vehículo este día
        const techEventsToday = _eventos.filter(ev => {
            if (ev.google_event_id === evId) return false;
            // [CANONICAL_MIGRATION] match by calendar_id (fallback to nombre)
            const matchesTech = (ev.calendar_id && ev.calendar_id === techCorreo) || (!ev.calendar_id && ev.tecnico_nombre === techNombre);
            if (!matchesTech) return false;
            const evSh = ev.inicio || "";
            const evEh = ev.fin || "";
            if (!evSh || !evEh) return false;
            return getStr(evSh) <= targetDate && getStr(evEh) >= targetDate;
        });
        
        for (const e of techEventsToday) {
            const eProps = (e.extended_props && e.extended_props.private) || {};
            const eVeh = eProps.app_vehiculo;
            if (eVeh && eVeh !== vehiculoNombre) {
                return `El técnico ${techNombre} ya tiene asignado el vehículo '${eVeh}' hoy. No puede usar '${vehiculoNombre}'.`;
            }
        }
        
        // Regla Capacidad: contar técnicos únicos usando el vehículo ese día.
        // IMPORTANTE: los miembros del mismo grupo SÍ cuentan como ocupantes del vehículo
        // (comparten el vehículo yendo al mismo trabajo, pero siguen ocupando asientos).
        const uniqueTechs = new Set();
        uniqueTechs.add(techCorreo || techNombre);
        sameDayEvents.forEach(e => {
            if (e.calendar_id || e.tecnico_nombre) uniqueTechs.add(e.calendar_id || e.tecnico_nombre);
        });
        
        if (uniqueTechs.size > veh.asientos) {
            // No bloqueamos — solo advertimos (badge de conflicto en UI)
            return `Capacidad excedida: '${vehiculoNombre}' tiene ${veh.asientos} asiento(s), pero lo usarían ${uniqueTechs.size} técnicos: ${Array.from(uniqueTechs).join(', ')}`;
        }
        
        // Regla Solapamiento: mismos horarios, distinto trabajo (excluir mismo grupo)
        for (const ev of sameDayEvents) {
            // Si pertenecen al mismo grupo → no es conflicto (mismo trabajo, mismo vehículo)
            if (grupoId) {
                const eProps = (ev.extended_props && ev.extended_props.private) || {};
                if (eProps.grupo_id === grupoId) continue;
            }
            
            const getHour = str => {
                if (str.includes('T')) {
                    const match = str.match(/T(\d+):(\d+)/);
                    if (match) return parseInt(match[1]) + parseInt(match[2])/60;
                } else if (str.includes(' ')) {
                    const match = str.split(' ')[1].split(':');
                    if (match) return parseInt(match[0]) + parseInt(match[1])/60;
                }
                return 12;
            };
            
            const evS_time = getHour(ev.inicio);
            const evE_time = getHour(ev.fin);
            
            if (Math.max(sh, evS_time) < Math.min(eh, evE_time)) {
                return `El vehículo '${vehiculoNombre}' ya está asignado a otro trabajo ("${ev.summary}") en ese horario.`;
            }
        }
        
        return null; // OK
    }

    // ─────────────────────────────────
    // COLLAPSIBLE PANELS
    // ─────────────────────────────────
    function bindPanelToggles() {
        const leftPanel = document.getElementById('left-panel');
        const rightPanel = document.getElementById('right-panel');
        const toggleLeft = document.getElementById('toggle-left');
        const toggleRight = document.getElementById('toggle-right');
        const iconLeft = document.getElementById('toggle-left-icon');
        const iconRight = document.getElementById('toggle-right-icon');

        if (!leftPanel || !rightPanel || !toggleLeft || !toggleRight || !iconLeft || !iconRight) {
            console.warn("[BOOT] bindPanelToggles: Faltan elementos para el colapso de paneles.");
            return;
        }

        let leftCollapsed = false;
        let rightCollapsed = false;

        const updateLeftUI = (collapsed) => {
            leftCollapsed = collapsed;
            leftPanel.classList.toggle('collapsed', leftCollapsed);
            toggleLeft.classList.toggle('collapsed', leftCollapsed);
            iconLeft.className = leftCollapsed ? 'fa-solid fa-chevron-right' : 'fa-solid fa-chevron-left';
            toggleLeft.title = leftCollapsed ? 'Mostrar panel' : 'Ocultar panel';
        };

        const updateRightUI = (collapsed) => {
            rightCollapsed = collapsed;
            rightPanel.classList.toggle('collapsed', rightCollapsed);
            toggleRight.classList.toggle('collapsed', rightCollapsed);
            iconRight.className = rightCollapsed ? 'fa-solid fa-chevron-left' : 'fa-solid fa-chevron-right';
            toggleRight.title = rightCollapsed ? 'Mostrar panel' : 'Ocultar panel';
        };

        toggleLeft.addEventListener('click', () => {
            const newState = !leftCollapsed;
            updateLeftUI(newState);
            
            // Regla: Abrir izquierdo -> Abrir derecho
            if (!newState) {
                updateRightUI(false);
            }
            
            setTimeout(() => Scheduler.render(), 270);
        });

        toggleRight.addEventListener('click', () => {
            const newState = !rightCollapsed;
            updateRightUI(newState);
            
            // Regla: Abrir derecho -> Abrir izquierdo
            if (!newState) {
                updateLeftUI(false);
            }
            // Regla: Cerrar derecho -> Cerrar izquierdo
            if (newState) {
                updateLeftUI(true);
            }

            setTimeout(() => Scheduler.render(), 270);
        });
    }

    // ─────────────────────────────────
    // INTERACTION HELPERS
    // ─────────────────────────────────
    function bindEmptySpaceClick() {
        // Clic en el wrapper del scheduler para deseleccionar
        const wrapper = document.getElementById('scheduler-wrapper');
        wrapper.addEventListener('click', (e) => {
            // Si el clic NO fue en un bloque de evento ni sus hijos
            if (!e.target.closest('.ev-block') && !e.target.closest('.ot-card')) {
                RightPanel.showEmpty();
                // Limpiar selección visual en backlog
                document.querySelectorAll('.ot-card').forEach(c => c.classList.remove('selected'));
            }
        });
    }



    // ─────────────────────────────────
    // PATRON MODAL (shared)
    // ─────────────────────────────────
    let _patronOnConfirmCb = null;

    async function openPatronModal(currentSelection, onConfirmCb) {
        const modal = document.getElementById('modal-patrones');
        const list = document.getElementById('patron-list');
        const searchInput = document.getElementById('patron-search');
        const jobFilter = document.getElementById('patron-job-filter');
        const summaryCont = document.getElementById('modal-patron-ot-summary');
        const summaryList = document.getElementById('patron-ot-summary-content');

        // Work on a copy so cancel = no changes
        _patronModalCallback = [...(currentSelection || [])];
        _patronOnConfirmCb = onConfirmCb;
        
        // 1. Población del Filtro de Trabajos
        const jobsSet = new Set();
        _patrones.forEach(p => {
            if (p.trabajos) {
                try {
                    // El dato llega como ["Balanza", "Pesas"] (string JSON)
                    const parsed = JSON.parse(p.trabajos);
                    if (Array.isArray(parsed)) {
                        parsed.forEach(job => jobsSet.add(job.trim()));
                    } else {
                        jobsSet.add(String(parsed).trim());
                    }
                } catch (e) {
                    // Fallback si no es JSON
                    const parts = p.trabajos.split(/[,;|]+/).map(s => s.trim().replace(/[\[\]"']/g, '')).filter(s => s);
                    parts.forEach(job => jobsSet.add(job));
                }
            }
        });
        const sortedJobs = Array.from(jobsSet).sort();
        jobFilter.innerHTML = '<option value="">(Todos los trabajos)</option>' + 
            sortedJobs.map(j => `<option value="${j}">${j}</option>`).join('');

        // 2. Resumen de OT actual
        const currentOTs = RightPanel.getCurrentOTs ? RightPanel.getCurrentOTs() : [];
        if (currentOTs.length > 0) {
            summaryCont.classList.remove('hidden');
            summaryList.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Cargando resumen...';
            try {
                const res = await fetch('/api/ots/batch/partidas', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ nros: currentOTs })
                });
                const data = await res.json();
                if (data.partidas && data.partidas.length > 0) {
                    summaryList.innerHTML = `
                        <table>
                            <thead><tr><th>Trabajo</th><th>Puntos</th><th>Cant.</th></tr></thead>
                            <tbody>${data.partidas.map(p => `<tr><td>${p.trabajo}</td><td>${p.puntos}</td><td>${p.cant}</td></tr>`).join('')}</tbody>
                        </table>`;
                } else {
                    summaryList.innerHTML = '<div style="color:var(--text-muted)">Sin partidas disponibles.</div>';
                }
            } catch {
                summaryList.innerHTML = '<div style="color:var(--danger)">No se pudo cargar el resumen.</div>';
            }
        } else {
            summaryCont.classList.add('hidden');
        }

        searchInput.value = '';
        jobFilter.value = '';
        _renderPatronList(_patrones, _patronModalCallback, '', '');
        document.getElementById('patron-selected-count').textContent = `${_patronModalCallback.length} seleccionados`;
        modal.classList.remove('hidden');
    }

    function _renderPatronList(patrones, selected, query, jobFilterVal) {
        const list = document.getElementById('patron-list');
        const q = (query || '').toLowerCase();
        
        const filtered = patrones.filter(p => {
            const matchQuery = !q || p.nombre.toLowerCase().includes(q);
            
            let matchJob = !jobFilterVal;
            if (jobFilterVal && p.trabajos) {
                try {
                    const parsed = JSON.parse(p.trabajos);
                    if (Array.isArray(parsed)) {
                        matchJob = parsed.some(j => j.trim().toLowerCase() === jobFilterVal.toLowerCase());
                    } else {
                        matchJob = String(parsed).trim().toLowerCase() === jobFilterVal.toLowerCase();
                    }
                } catch (e) {
                    matchJob = p.trabajos.toLowerCase().includes(jobFilterVal.toLowerCase());
                }
            }
            return matchQuery && matchJob;
        });

        // Ordenamiento: 1. Patrón/Medio, 2. Alfabético por Nombre
        filtered.sort((a, b) => {
            const isPriority = (clase) => {
                if (!clase) return false;
                const c = clase.toLowerCase();
                return c.includes('patron') || c.includes('medio');
            };
            const prioA = isPriority(a.clase) ? 1 : 0;
            const prioB = isPriority(b.clase) ? 1 : 0;

            if (prioA !== prioB) return prioB - prioA; // Prioridad descendente
            return a.nombre.localeCompare(b.nombre);   // Nombre ascendente
        });

        list.innerHTML = '';
        if (!filtered.length) {
            list.innerHTML = '<div style="padding:10px;color:var(--text-muted);font-size:12px">Sin resultados</div>';
            return;
        }

        filtered.forEach(p => {
            const isSel = selected.includes(p.nombre);
            const item = document.createElement('div');
            item.className = 'patron-item' + (isSel ? ' selected' : '');
            item.innerHTML = `
                <input type="checkbox" ${isSel ? 'checked' : ''}>
                <div>
                    <div class="patron-item-name">${p.nombre}</div>
                    ${p.rango ? `<div class="patron-item-rango"><i class="fa-solid fa-ruler" style="font-size:9px;margin-right:4px"></i>${p.rango}</div>` : ''}
                </div>`;

            const toggleSelect = () => {
                const idx = selected.indexOf(p.nombre);
                const chk = item.querySelector('input');
                if (idx >= 0) {
                    selected.splice(idx, 1);
                    item.classList.remove('selected');
                    chk.checked = false;
                } else {
                    selected.push(p.nombre);
                    item.classList.add('selected');
                    chk.checked = true;
                }
                document.getElementById('patron-selected-count').textContent = `${selected.length} seleccionados`;
            };
            item.addEventListener('click', toggleSelect);
            list.appendChild(item);
        });
    }

    function bindPatronModal() {
        const searchInput = document.getElementById('patron-search');
        const jobFilter = document.getElementById('patron-job-filter');
        const btnConfirm = document.getElementById('btn-confirmar-patrones');

        if (!searchInput || !jobFilter || !btnConfirm) {
            console.warn("[BOOT] bindPatronModal: Faltan elementos del modal de patrones.");
            return;
        }

        const triggerFilter = () => {
            _renderPatronList(_patrones, _patronModalCallback, searchInput.value, jobFilter.value);
        };

        searchInput.addEventListener('input', triggerFilter);
        jobFilter.addEventListener('change', triggerFilter);

        const btnClear = document.getElementById('btn-clear-patrones');
        if (btnClear) {
            btnClear.addEventListener('click', () => {
                if (_patronModalCallback) {
                    _patronModalCallback.length = 0; // Vaciar el array manteniendo la referencia
                    triggerFilter();
                    document.getElementById('patron-selected-count').textContent = '0 seleccionados';
                }
            });
        }

        btnConfirm.addEventListener('click', () => {
            const modal = document.getElementById('modal-patrones');
            if (modal) modal.classList.add('hidden');
            if (_patronOnConfirmCb) {
                _patronOnConfirmCb([..._patronModalCallback]);
            } else if (_patronModalCallback !== null) {
                RightPanel.onPatronesConfirmed([..._patronModalCallback]);
            }
            _patronModalCallback = null;
            _patronOnConfirmCb = null;
        });

        // Generic modal close handlers
        document.querySelectorAll('.modal-close').forEach(btn => {
            btn.addEventListener('click', () => {
                const id = btn.dataset.modal;
                if (id) document.getElementById(id).classList.add('hidden');
                if (id === 'modal-patrones') _patronModalCallback = null;
            });
        });
        document.querySelectorAll('.modal-overlay').forEach(overlay => {
            overlay.addEventListener('click', e => {
                if (e.target === overlay) {
                    overlay.classList.add('hidden');
                    if (overlay.id === 'modal-patrones') _patronModalCallback = null;
                }
            });
        });
    }

    // ─────────────────────────────────
    // FOOTER
    // ─────────────────────────────────
    function updateFooter() {
        // Calculate week occupancy
        if (_eventos.length === 0) {
            document.getElementById('footer-ocupacion').textContent = '—';
            return;
        }
        const today = new Date();
        const weekStart = new Date(today);
        weekStart.setDate(today.getDate() - ((today.getDay() + 6) % 7));
        weekStart.setHours(0,0,0,0);
        const weekEnd = new Date(weekStart);
        weekEnd.setDate(weekStart.getDate() + 5); // Mon-Fri only

        const thisWeek = _eventos.filter(ev => {
            const d = new Date((ev.inicio || '').substring(0, 10) + 'T12:00:00');
            return d >= weekStart && d < weekEnd;
        });
        document.getElementById('footer-ocupacion').textContent =
            `Esta semana: ${thisWeek.length} evento${thisWeek.length !== 1 ? 's' : ''} · ${_tecnicos.length} técnicos`;
    }

    // ─────────────────────────────────
    // TOAST
    // ─────────────────────────────────
    function toast(msg, type = 'info') {
        const container = document.getElementById('toast-container');
        if (!container) return;
        const el = document.createElement('div');
        el.className = `toast ${type}`;
        const icon = { 
            success: 'fa-circle-check', 
            error: 'fa-circle-xmark', 
            info: 'fa-circle-info',
            warning: 'fa-triangle-exclamation'
        }[type] || 'fa-circle-info';
        
        let messageText = msg;
        if (msg && typeof msg !== 'string') {
            try {
                messageText = (msg instanceof Error) ? msg.message : JSON.stringify(msg);
            } catch (e) {
                messageText = String(msg);
            }
        }

        el.innerHTML = `<i class="fa-solid ${icon}"></i> ${messageText}`;
        container.appendChild(el);
        setTimeout(() => {
            el.style.transition = 'opacity 0.4s';
            el.style.opacity = '0';
            setTimeout(() => el.remove(), 400);
        }, 5000);
    }

    // ─────────────────────────────────
    // TARJETA DE SALIDA
    // ─────────────────────────────────
    function initTarjetaSalida() {
        const btnOpen = document.getElementById('btn-ts-open');
        const inputDate = document.getElementById('ts-date-input');
        const btnRefrescar = document.getElementById('ts-btn-refrescar');
        const btnCopy = document.getElementById('ts-btn-copy');
        const btnWhatsApp = document.getElementById('ts-btn-whatsapp');

        if (!btnOpen) return;

        btnOpen.addEventListener('click', () => {
            // Fecha por defecto: Siguiente día hábil
            if (!inputDate.value) {
                inputDate.value = getNextBusinessDay();
            }
            document.getElementById('modal-tarjeta-salida').classList.remove('hidden');
            refrescarGruposTS();
        });

        // Automatización: Refrescar al cambiar la fecha
        inputDate.addEventListener('change', refrescarGruposTS);
        if (btnRefrescar) btnRefrescar.addEventListener('click', refrescarGruposTS);
        
        if (btnCopy) {
            btnCopy.addEventListener('click', async () => {
                const target = document.getElementById('ts-visualizacion');
                if (!target || !target.value) {
                    toast('No hay texto para copiar.', 'warning');
                    return;
                }
                try {
                    await navigator.clipboard.writeText(target.value);
                    toast('Texto copiado al portapapeles ✓', 'success');
                } catch (err) {
                    toast('Error al copiar al portapapeles.', 'error');
                }
            });
        }
        
        if (btnWhatsApp) {
            btnWhatsApp.addEventListener('click', () => {
                const target = document.getElementById('ts-visualizacion');
                if (!target || !target.value) {
                    toast('No hay texto para compartir.', 'warning');
                    return;
                }
                const text = encodeURIComponent(target.value);
                const whatsappUrl = `https://api.whatsapp.com/send?text=${text}`;
                window.open(whatsappUrl, '_blank');
            });
        }
    }

    function getNextBusinessDay() {
        const next = new Date();
        next.setDate(next.getDate() + 1);
        
        // Domingo -> Lunes (+1) / Sábado -> Lunes (+2)
        if (next.getDay() === 0) next.setDate(next.getDate() + 1);
        else if (next.getDay() === 6) next.setDate(next.getDate() + 2);
        
        const y = next.getFullYear();
        const m = String(next.getMonth() + 1).padStart(2, '0');
        const d = String(next.getDate()).padStart(2, '0');
        return `${y}-${m}-${d}`;
    }

    async function refrescarGruposTS() {
        const date = document.getElementById('ts-date-input').value;
        const listContainer = document.getElementById('ts-grupos-list');
        const viewContainer = document.getElementById('ts-visualizacion');

        listContainer.innerHTML = '<div style="color:var(--text-muted)">Cargando...</div>';
        viewContainer.value = '';
        viewContainer.classList.add('hidden');
        
        const btnCopy = document.getElementById('ts-btn-copy');
        if (btnCopy) btnCopy.classList.add('hidden');
        const btnWhatsApp = document.getElementById('ts-btn-whatsapp');
        if (btnWhatsApp) btnWhatsApp.classList.add('hidden');

        try {
            const res = await fetch(`/api/grupos/tarjeta_salida?fecha=${date}`);
            const grupos = await res.json();

            if (!grupos.length) {
                listContainer.innerHTML = '<div style="grid-column: 1/-1; color:var(--text-muted); text-align:center; padding:20px;">No hay eventos agendados para este día.</div>';
                return;
            }

            listContainer.innerHTML = grupos.map(g => {
                const tag = g.tag || g.tecnicos.map(t => t.split(' ')[0][0]).join('/'); 
                return `
                <div class="ts-grupo-item" onclick="App.renderTarjeta(${JSON.stringify(g).replace(/"/g, '&quot;')})">
                    <div class="ts-tag">${tag}</div>
                    <div class="ts-ot">OT: ${g.ot_nro}</div>
                    <div class="ts-cli">${g.cliente || '---'}</div>
                </div>
                `;
            }).join('');

        } catch (e) {
            listContainer.innerHTML = '<div style="color:var(--danger)">Error al cargar grupos.</div>';
        }
    }

    function renderTarjeta(g) {
        const viewContainer = document.getElementById('ts-visualizacion');
        const btnCopy = document.getElementById('ts-btn-copy');
        const btnWhatsApp = document.getElementById('ts-btn-whatsapp');
        
        const dateRaw = document.getElementById('ts-date-input').value;
        let dateFmt = dateRaw;
        if (dateRaw && dateRaw.includes('-')) {
            const parts = dateRaw.split('-');
            dateFmt = `${parts[2]}/${parts[1]}/${parts[0]}`;
        }
        
        // --- 1. Agrupar Patrones por Magnitud (Trabajos) ---
        const patGroups = {};
        const sinMagnitud = [];
        (g.patrones || []).forEach(pCode => {
            const patData = _patrones.find(x => x.nombre === pCode);
            if (patData && patData.trabajos) {
                try {
                    const parsed = JSON.parse(patData.trabajos);
                    const mag = Array.isArray(parsed) ? parsed[0] : parsed;
                    if (!patGroups[mag]) patGroups[mag] = [];
                    patGroups[mag].push(pCode);
                } catch (e) {
                    const parts = patData.trabajos.split(/[,;|]+/).map(s => s.trim().replace(/[\\[\\]"']/g, '')).filter(s => s);
                    const mag = parts.length > 0 ? parts[0] : 'Otros';
                    if (!patGroups[mag]) patGroups[mag] = [];
                    patGroups[mag].push(pCode);
                }
            } else {
                sinMagnitud.push(pCode);
            }
        });
        
        let patLines = [];
        for (const [mag, codes] of Object.entries(patGroups)) {
            patLines.push(`- ${mag}: ${codes.join(', ')}`);
        }
        if (sinMagnitud.length > 0) {
            patLines.push(`- Otros: ${sinMagnitud.join(', ')}`);
        }
        const patronesTxt = patLines.length > 0 ? patLines.join('\n') : '- Sin patrones asignados';

        // --- 2. Agrupar OTs por Cliente y Dirección ---
        const otGroupsMap = {};
        (g.detalles_ots || []).forEach(dt => {
            const key = `${dt.cliente || '---'}|||${dt.direccion || '---'}`;
            if (!otGroupsMap[key]) {
                otGroupsMap[key] = { cliente: dt.cliente || '---', direccion: dt.direccion || '---', ots: [] };
            }
            otGroupsMap[key].ots.push(dt);
        });
        const otGroups = Object.values(otGroupsMap);

        // --- 3. Generar Texto Plano ---
        let txt = `*TARJETA DE SALIDA - ${dateFmt}*\n\n`;
        txt += `👥 *Equipo:* ${g.tecnicos.join(', ')}\n`;
        txt += `🚐 *Vehículo:* ${g.vehiculo || 'No asignado'}\n`;
        txt += `⚖️ *Patrones:*\n${patronesTxt}\n`;
        
        otGroups.forEach((group, index) => {
            txt += `\n----------------------------------------\n`;
            if (otGroups.length > 1) {
                txt += `📍 *DESTINO ${index + 1}: ${group.cliente}*\n`;
            } else {
                txt += `📍 *DESTINO: ${group.cliente}*\n`;
            }
            txt += `🗺️ _${group.direccion}_\n\n`;
            
            // OTs
            group.ots.forEach(dt => {
                txt += `🔸 *OT ${dt.nro}:* ${dt.asunto}\n`;
                if (dt.fechas_adicionales && dt.fechas_adicionales.length > 0) {
                    txt += `_(Próximas visitas: ${dt.fechas_adicionales.join(', ')})_\n`;
                }
            });
            
            // Resumen de Partidas
            const partidasResumenMap = {};
            group.ots.forEach(dt => {
                if (dt.partidas) {
                    dt.partidas.forEach(p => {
                        const pk = `${p.trabajo}|||${p.puntos}`;
                        if (!partidasResumenMap[pk]) partidasResumenMap[pk] = { trabajo: p.trabajo, puntos: p.puntos, cant: 0 };
                        partidasResumenMap[pk].cant += parseInt(p.cant, 10) || 0;
                    });
                }
            });
            const resumenItems = Object.values(partidasResumenMap);
            if (resumenItems.length > 0) {
                // Calcular anchos dinámicos respetando min y max
                let maxTrabajo = 7; // "TRABAJO" len
                let maxPts = 3;     // "PTS" len
                let maxCant = 4;    // "CANT" len
                
                resumenItems.forEach(p => {
                    const tLen = (p.trabajo || '').length;
                    const pLen = String(p.puntos || '').length;
                    const cLen = String(p.cant).length;
                    if (tLen > maxTrabajo) maxTrabajo = tLen;
                    if (pLen > maxPts) maxPts = pLen;
                    if (cLen > maxCant) maxCant = cLen;
                });
                
                txt += `\n📊 *Partidas:*\n\n`;
                
                resumenItems.forEach(p => {
                    const trabStr = p.trabajo || '---';
                    const ptsStr = p.puntos ? ` (${p.puntos})` : '';
                    const cantStr = p.cant;
                    
                    txt += `▪ *${trabStr}*${ptsStr} ➞ Cant: ${cantStr}\n`;
                });
            } else {
                txt += `\n📊 *Partidas:* _Sin partidas registradas_`;
            }
            txt += `\n`;
        });
        
        viewContainer.value = txt.trim();
        viewContainer.classList.remove('hidden');
        
        if (btnCopy) btnCopy.classList.remove('hidden');
        if (btnWhatsApp) btnWhatsApp.classList.remove('hidden');
    }

    function openSFLink(sfid) {
        if (!sfid) return;
        const url = `https://akribis.lightning.force.com/lightning/r/WorkOrder/${sfid}/view`;
        window.open(url, '_blank');
    }

    function showSFLinksPopup(otsArr) {
        const modal = document.getElementById('modal-sf-links');
        const list = document.getElementById('sf-links-list');
        list.innerHTML = '';

        otsArr.forEach(otNro => {
            const cleanNro = String(otNro).trim();
            const otData = _ots.find(o => String(o.nro).trim() === cleanNro);
            if (otData && otData.sfid) {
                const btn = document.createElement('button');
                btn.className = 'btn-secondary';
                btn.style.justifyContent = 'flex-start';
                btn.innerHTML = `<i class="fa-solid fa-up-right-from-square" style="color:#00a1e0"></i> OT ${otNro} — ${otData.cliente || 'SF'}`;
                btn.onclick = () => {
                    openSFLink(otData.sfid);
                    modal.classList.add('hidden');
                };
                list.appendChild(btn);
            }
        });

        if (list.childElementCount > 0) {
            modal.classList.remove('hidden');
        } else {
            toast('No se encontraron IDs de Salesforce para estas OTs', 'info');
        }
    }

    return { 
        init, refresh, selectEvent, openQuickCreate, 
        deleteEvent, moveEvent, splitEvent,
        toast, openPatronModal,
        getVehiculos, checkVehicleConflicts,
        refreshSingleEvent, removeSingleEvent, batchRefreshEvents, refreshEvents,
        applyGroupSnapshot,
        renderTarjeta, quitarTecnicoDeGrupo, setGroupSyncing,
        openSFLink, showSFLinksPopup,
        logTrace,
        toggleBatchMode, isBatchMode: () => _isBatchMode, isEventSelected: (id) => _batchSelected.has(id), getBatchSelection: () => Array.from(_batchSelected),
        getEventos: () => _eventos,
        getBacklogOTs: () => _ots,
        getServicios: () => _servicios,
        getState: () => ({ _tecnicos, _eventos, _ots, _patrones, _vehiculos, _holidays })
    };
})();

// Exposición global para depuración (F12)
window.APP_DEBUG = { App, Scheduler, Backlog, RightPanel, ConfigMenu, PollManager };

document.addEventListener('DOMContentLoaded', () => App.init());
