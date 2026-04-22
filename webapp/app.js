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
    let _patronModalCallback = null; // temp selected while modal is open

    // ─────────────────────────────────
    // BOOT
    // ─────────────────────────────────
    async function init() {
        RightPanel.init();
        Backlog.init();
        bindNavButtons();
        bindSyncButton();
        bindPatronModal();
        bindPanelToggles();
        bindEmptySpaceClick();
        
        // Sincronizar scroll vertical entre área de eventos y columna de técnicos
        const scrollArea = document.getElementById('scheduler-scroll-area');
        const techLabels = document.getElementById('tech-labels-col');
        scrollArea.addEventListener('scroll', () => {
            techLabels.scrollTop = scrollArea.scrollTop;
        });

        initPanelResizer();

        await loadAll();
        Scheduler.setView('week'); // Sincroniza estado inicial y UI
        
        startHeartbeat();
        triggerBackgroundSync(); // Sync automática en background sin bloquear la UI
        
        // Sincronización automática de eventos cada 60 minutos
        setInterval(() => {
            console.log('[AutoSync] Ejecutando sincronización de 60 minutos...');
            triggerBackgroundSync();
        }, 60 * 60 * 1000);

        initTarjetaSalida();
    }

    async function refresh() {
        await loadAll();
        Scheduler.render();
    }

    // ─────────────────────────────────
    // SYNC: TARGETED REFRESH HELPERS
    // ─────────────────────────────────

    /** Recarga SOLO los eventos desde SQLite (~1 petición vs 5 del refresh completo). */
    async function refreshEvents() {
        try {
            const evRes = await fetch('/api/eventos');
            if (!evRes.ok) return;
            _eventos = await evRes.json();
            Scheduler.setState({ tecnicos: _tecnicos, eventos: _eventos });
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
        const idx = _eventos.findIndex(e => e.id === eventData.id);
        if (idx !== -1) _eventos[idx] = eventData;
        else _eventos.push(eventData);
        Scheduler.setState({ tecnicos: _tecnicos, eventos: _eventos });
        Scheduler.render();
        Backlog.render(_ots, _eventos);
        updateFooter();
    }

    /** Elimina un evento de memoria y re-renderiza. Sin round-trip al servidor. */
    function removeSingleEvent(eventId) {
        _eventos = _eventos.filter(e => e.id !== eventId);
        Scheduler.setState({ tecnicos: _tecnicos, eventos: _eventos });
        Scheduler.render();
        Backlog.render(_ots, _eventos);
        updateFooter();
    }

    /** Inserta múltiples eventos de golpe (ej: tras programar una OT multi-jornada). */
    function batchRefreshEvents(newEvents) {
        newEvents.forEach(ev => {
            const idx = _eventos.findIndex(e => e.id === ev.id);
            if (idx !== -1) _eventos[idx] = ev;
            else _eventos.push(ev);
        });
        Scheduler.setState({ tecnicos: _tecnicos, eventos: _eventos });
        Scheduler.render();
        Backlog.render(_ots, _eventos);
        updateFooter();
    }

    /**
     * Sync automática en background al abrir la app.
     * No bloquea la UI — espera 2s para no interferir con la carga inicial.
     */
    async function triggerBackgroundSync() {
        await new Promise(r => setTimeout(r, 2000));
        const syncFooter = document.getElementById('footer-sync');
        const prevText = syncFooter ? syncFooter.textContent : '';
        try {
            if (syncFooter) syncFooter.textContent = '↻ Actualizando...';
            const controller = new AbortController();
            const tId = setTimeout(() => controller.abort(), 120000);
            const res = await fetch('/api/sync', { signal: controller.signal });
            clearTimeout(tId);
            if (!res.ok) { if (syncFooter) syncFooter.textContent = prevText; return; }
            const data = await res.json();
            if (syncFooter && data.last_sync) {
                syncFooter.textContent = `Última sync: ${data.last_sync}`;
            }
            await loadAll();
            Scheduler.render();
            toast(`✓ Datos actualizados (${data.eventos} eventos)`, 'info');
        } catch (e) {
            if (e.name !== 'AbortError') console.warn('[BgSync]', e.message);
            if (syncFooter) syncFooter.textContent = prevText;
        }
    }

    function startHeartbeat() {
        // Enviar un "latido" al servidor cada 10 segundos para evitar el apagado automático
        setInterval(() => {
            fetch('/api/heartbeat', { method: 'POST' }).catch(() => {
                // Si el servidor ya cerró, no hacemos nada
            });
        }, 10000);
    }

    // ─────────────────────────────────
    // PANEL RESIZER
    // ─────────────────────────────────
    function initPanelResizer() {
        const resizer = document.getElementById('right-resizer');
        const panel = document.getElementById('right-panel');
        let isResizing = false;

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
        try {
            const [tecRes, evRes, otRes, patRes, vehsRes] = await Promise.all([
                fetch('/api/tecnicos'),
                fetch('/api/eventos'),
                fetch('/api/ots/pendientes'),
                fetch('/api/patrones'),
                fetch('/api/vehiculos'),
            ]);

            if (!tecRes.ok || !evRes.ok || !otRes.ok || !patRes.ok || !vehsRes.ok) {
                throw new Error('Error en una o más peticiones de carga inicial');
            }

            _tecnicos = await tecRes.json();
            _eventos = await evRes.json();
            _ots = await otRes.json();
            _patrones = await patRes.json();
            _vehiculos = await vehsRes.json();

            window._tecnicos = _tecnicos;
            Scheduler.assignColors(_tecnicos);
            Scheduler.setState({ tecnicos: _tecnicos, eventos: _eventos });
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
    function selectEvent(ev) {
        RightPanel.showEventDetail(ev);
    }

    function openQuickCreate(tech, date, hour, otData) {
        RightPanel.showQuickCreate(tech, date, hour, otData);
    }

    async function moveEvent(eventId, calendarId, destCorreo, nuevaFecha, hora) {
        // --- ACTUALIZACIÓN OPTIMISTA ---
        const eventIdx = _eventos.findIndex(e => e.id === eventId);
        let originalEvent = null;
        if (eventIdx !== -1) {
            originalEvent = JSON.parse(JSON.stringify(_eventos[eventIdx]));
            const destTec = _tecnicos.find(t => t.correo === destCorreo);
            
            // Actualización local temporal del evento
            _eventos[eventIdx].resourceId = destTec ? destTec.nombre : _eventos[eventIdx].resourceId;
            _eventos[eventIdx]['Técnico'] = destTec ? destTec.nombre : _eventos[eventIdx]['Técnico'];
            
            // Para que el renderizado persista antes de la sincronización de Calendar
            if (nuevaFecha) {
                const sTime = _eventos[eventIdx].start ? _eventos[eventIdx].start.substring(10) : 'T08:00:00';
                const eTime = _eventos[eventIdx].end ? _eventos[eventIdx].end.substring(10) : 'T10:00:00';
                _eventos[eventIdx].start = nuevaFecha + sTime;
                _eventos[eventIdx].end = nuevaFecha + eTime;
                _eventos[eventIdx].Inicio = _eventos[eventIdx].start;
                _eventos[eventIdx].Fin = _eventos[eventIdx].end;
                _eventos[eventIdx]._dayStr = nuevaFecha;
            }
            
            // Sh/Eh se manejan por h_start si la vista es día
            if (hora !== undefined) {
                const duration = _eventos[eventIdx]._eh - _eventos[eventIdx]._sh;
                _eventos[eventIdx]._sh = hora;
                _eventos[eventIdx]._eh = hora + (duration > 0 ? duration : 1);
                
                // Reflejar en strings de Inicio/Fin para que Scheduler.getExpandedEvents no lo sobreescriba
                const fmtH = (h) => {
                    const integer = Math.floor(h);
                    const minutes = Math.round((h - integer) * 60);
                    return `T${String(integer).padStart(2,'0')}:${String(minutes).padStart(2,'0')}:00`;
                };
                const baseDate = _eventos[eventIdx].start ? _eventos[eventIdx].start.substring(0, 10) : nuevaFecha;
                _eventos[eventIdx].start = baseDate + fmtH(_eventos[eventIdx]._sh);
                _eventos[eventIdx].end = baseDate + fmtH(_eventos[eventIdx]._eh);
                _eventos[eventIdx].Inicio = _eventos[eventIdx].start;
                _eventos[eventIdx].Fin = _eventos[eventIdx].end;
            }
            
            Scheduler.setState({ tecnicos: _tecnicos, eventos: [..._eventos] }); // Spread para forzar cambio de ref
            Scheduler.render();
        }

        try {
            const destTec = _tecnicos.find(t => t.correo === destCorreo);
            const res = await fetch(`/api/eventos/${eventId}/mover`, {
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
            toast('Evento movido ✓', 'success');
            // Si el ID cambió (fallback delete+insert), eliminar el viejo del estado local
            if (data.event_id && data.event_id !== eventId) {
                removeSingleEvent(eventId);
            }
            await refreshEvents();
        } catch (e) {
            toast('Error al mover: ' + e.message, 'error');
            // Al fallar, volvemos a la versión previa descargando todo
            await refreshEvents();
        }
    }

    async function deleteEvent(eventId, calendarId) {
        if (!calendarId) { toast('Sin calendar ID para eliminar', 'error'); return; }
        try {
            const res = await fetch(
                `/api/eventos/${eventId}?calendar_id=${encodeURIComponent(calendarId)}`,
                { method: 'DELETE' }
            );
            if (!res.ok) throw new Error(await res.text());
            toast('Evento eliminado ✓', 'success');
            RightPanel.showEmpty();
            await refreshEvents(); // Recargar para ver cambios en posibles compañeros de grupo
        } catch (e) {
            toast('Error al eliminar: ' + e.message, 'error');
        }
    }

    async function splitEvent(eventId, calendarId) {
        if (!confirm('¿Deseas individualizar este evento? Se creará uno independiente por cada día.')) return;
        try {
            const res = await fetch(`/api/eventos/${eventId}/split?calendar_id=${encodeURIComponent(calendarId)}`, {
                method: 'POST'
            });
            if (!res.ok) throw new Error(await res.text());
            toast('Evento individualizado ✓', 'success');
            RightPanel.showEmpty();
            await refreshEvents(); // Solo recargar eventos
        } catch (e) {
            toast('Error al dividir: ' + e.message, 'error');
        }
    }

    async function quitarTecnicoDeGrupo(eventId, calendarId) {
        try {
            const res = await fetch(`/api/eventos/${eventId}/quitar_tecnico?calendar_id=${encodeURIComponent(calendarId)}`, {
                method: 'POST'
            });
            if (!res.ok) throw new Error(await res.text());
            toast('Técnico desasignado ✓', 'success');
            RightPanel.showEmpty();
            await refreshEvents();
        } catch (e) {
            toast('Error al quitar técnico: ' + e.message, 'error');
        }
    }

    // ─────────────────────────────────
    // NAVIGATION BUTTONS
    // ─────────────────────────────────
    function bindNavButtons() {
        document.getElementById('btn-prev').addEventListener('click', () => Scheduler.navigate(-1));
        document.getElementById('btn-next').addEventListener('click', () => Scheduler.navigate(1));
        document.getElementById('btn-today').addEventListener('click', () => Scheduler.goToday());
        document.getElementById('btn-view-day').addEventListener('click', () => Scheduler.setView('day'));
        document.getElementById('btn-view-week').addEventListener('click', () => Scheduler.setView('week'));
        document.getElementById('chk-solo-ots').addEventListener('change', e => {
            Scheduler.setState({ soloOTs: e.target.checked });
            Scheduler.render();
        });
        
        document.getElementById('btn-view-resources').addEventListener('click', () => {
            const isRes = Scheduler.toggleResourceMode();
            document.getElementById('btn-view-resources').classList.toggle('active-blue', isRes);
            
            // Mostrar toggle de expandir
            document.getElementById('lbl-expandir-pats').style.display = isRes ? 'flex' : 'none';
            // Auto cerrar/abrir panel izquierdo simulando click para mantener estado
            const leftCol = document.getElementById('left-panel').classList.contains('collapsed');
            if (isRes && !leftCol) {
                document.getElementById('toggle-left').click();
            } else if (!isRes && leftCol) {
                document.getElementById('toggle-left').click();
            }
        });
        
        document.getElementById('chk-expand-pats').addEventListener('change', e => {
            Scheduler.setState({ expandPats: e.target.checked });
            Scheduler.render();
        });
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
    
    function checkVehicleConflicts(vehiculoNombre, dateStr, sh, eh, evId, techNombre) {
        if (!vehiculoNombre) return null;
        
        const veh = _vehiculos.find(v => v.nombre === vehiculoNombre);
        if (!veh) return null;
        
        // Formatear dateStr si es Date
        const getStr = d => {
            if (typeof d === 'string') return d.substring(0, 10);
            return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
        };
        const targetDate = getStr(dateStr);
        
        // Filtrar eventos del mismo día que usen el mismo vehículo
        const sameDayEvents = _eventos.filter(ev => {
            const props = (ev.extendedProperties && ev.extendedProperties.private) || {};
            if (props.app_vehiculo !== vehiculoNombre) return false;
            
            // Ver si toca el targetDate
            const evSh = ev.start || ev.Inicio || "";
            const evEh = ev.end || ev.Fin || "";
            if (!evSh || !evEh) return false;
            return getStr(evSh) <= targetDate && getStr(evEh) >= targetDate;
        });
        
        // Regla NUEVA: Verificar si EL TÉCNICO tiene asignado OTRO vehículo en este mismo día
        const techEventsToday = _eventos.filter(ev => {
            if (ev.id === evId) return false; // Mismo evento
            if ((ev.resourceId || ev["Técnico"]) !== techNombre) return false;
            const evSh = ev.start || ev.Inicio || "";
            const evEh = ev.end || ev.Fin || "";
            if (!evSh || !evEh) return false;
            return getStr(evSh) <= targetDate && getStr(evEh) >= targetDate;
        });
        
        for (const e of techEventsToday) {
            const eProps = (e.extendedProperties && e.extendedProperties.private) || {};
            const eVeh = eProps.app_vehiculo;
            if (eVeh && eVeh !== vehiculoNombre) {
                return `El técnico ${techNombre} ya tiene asignado el vehículo '${eVeh}' hoy. No puede usar '${vehiculoNombre}'.`;
            }
        }
        
        // 1. Regla Capacidad: Contar técnicos únicos usando el vehículo ese día
        const uniqueTechs = new Set();
        uniqueTechs.add(techNombre); // Se suma el técnico actual que intenta asignar
        sameDayEvents.forEach(e => {
            if (e.resourceId || e["Técnico"]) uniqueTechs.add(e.resourceId || e["Técnico"]);
        });
        
        if (uniqueTechs.size > veh.asientos) {
            return `Límite de capacidad excedido: El vehículo '${vehiculoNombre}' solo tiene ${veh.asientos} asientos. Técnicos para hoy: ${Array.from(uniqueTechs).join(', ')}`;
        }
        
        // 2. Regla Solapamiento (distintos eventos (ev.id distinto) al mismo tiempo)
        for (const ev of sameDayEvents) {
            if (ev.id === evId) continue; // Mismo evento, OK
            
            // Calcular horas simples
            const getHour = str => {
                if (str.includes('T')) {
                    const match = str.match(/T(\d+):(\d+)/);
                    if (match) return parseInt(match[1]) + parseInt(match[2])/60;
                } else if (str.includes(' ')) {
                    const match = str.split(' ')[1].split(':');
                    if (match) return parseInt(match[0]) + parseInt(match[1])/60;
                }
                return 12; // all-day default
            };
            
            const evS_time = getHour(ev.start || ev.Inicio);
            const evE_time = getHour(ev.end || ev.Fin);
            
            // Solapamiento de tiempo?
            if (Math.max(sh, evS_time) < Math.min(eh, evE_time)) {
                return `El vehículo '${vehiculoNombre}' ya está asignado al evento "${ev.title || ev.Evento}" en ese horario.`;
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
    // SYNC BUTTON (with timeout)
    // ─────────────────────────────────
    function bindSyncButton() {
        const btn = document.getElementById('btn-sync');
        btn.addEventListener('click', async () => {
            btn.disabled = true;
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Sincronizando...';
            try {
                // 90 second timeout — sync can take time with many calendars
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 90000);

                const res = await fetch('/api/sync', { signal: controller.signal });
                clearTimeout(timeoutId);

                if (!res.ok) {
                    const errText = await res.text();
                    throw new Error(`HTTP ${res.status}: ${errText}`);
                }
                const data = await res.json();
                toast(`Sincronizado: ${data.eventos} eventos, ${data.tecnicos} técnicos`, 'success');
                document.getElementById('footer-sync').textContent = `Última sync: ${data.last_sync}`;
                await refresh();
            } catch (e) {
                if (e.name === 'AbortError') {
                    toast('La sincronización tardó demasiado (timeout 90s)', 'error');
                } else {
                    toast('Error de sincronización: ' + e.message, 'error');
                }
                console.error('Sync error:', e);
            } finally {
                btn.disabled = false;
                btn.innerHTML = '<i class="fa-solid fa-rotate"></i> Sincronizar';
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

        const triggerFilter = () => {
            _renderPatronList(_patrones, _patronModalCallback, searchInput.value, jobFilter.value);
        };

        searchInput.addEventListener('input', triggerFilter);
        jobFilter.addEventListener('change', triggerFilter);

        document.getElementById('btn-confirmar-patrones').addEventListener('click', () => {
            document.getElementById('modal-patrones').classList.add('hidden');
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
            const d = new Date((ev.start || '').substring(0, 10) + 'T12:00:00');
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
        const el = document.createElement('div');
        el.className = `toast ${type}`;
        const icon = { success: 'fa-circle-check', error: 'fa-circle-xmark', info: 'fa-circle-info' }[type] || 'fa-circle-info';
        el.innerHTML = `<i class="fa-solid ${icon}"></i> ${msg}`;
        container.appendChild(el);
        setTimeout(() => {
            el.style.transition = 'opacity 0.4s';
            el.style.opacity = '0';
            setTimeout(() => el.remove(), 400);
        }, 4500);
    }

    // ─────────────────────────────────
    // TARJETA DE SALIDA
    // ─────────────────────────────────
    function initTarjetaSalida() {
        const btnOpen = document.getElementById('btn-ts-open');
        const inputDate = document.getElementById('ts-date-input');
        const btnRefrescar = document.getElementById('ts-btn-refrescar');
        const btnPrint = document.getElementById('ts-btn-print');

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
        btnRefrescar.addEventListener('click', refrescarGruposTS);
        
        if (btnPrint) {
            btnPrint.addEventListener('click', () => {
                const content = document.getElementById('ts-visualizacion').innerHTML;
                const printWindow = window.open('', '_blank');
                printWindow.document.write(`
                    <html>
                    <head><title>Tarjeta de Salida - Akrimet</title>
                    <style>
                        body { font-family: 'Courier New', Courier, monospace; padding: 20px; white-space: pre-wrap; font-size: 14px; }
                        .card-header { border-bottom: 2px solid #000; margin-bottom: 15px; padding-bottom: 5px; font-weight: bold; font-size: 18px; }
                        .section-label { font-weight: bold; text-decoration: underline; margin-top: 15px; display: block; }
                    </style>
                    </head>
                    <body>${content}</body>
                    </html>
                `);
                printWindow.document.close();
                printWindow.focus();
                setTimeout(() => { printWindow.print(); }, 500);
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
        const btnPrint = document.getElementById('ts-btn-print');

        listContainer.innerHTML = '<div style="color:var(--text-muted)">Cargando...</div>';
        viewContainer.innerHTML = '';
        viewContainer.classList.add('hidden');
        if (btnPrint) btnPrint.classList.add('hidden');

        try {
            const res = await fetch(`/api/grupos/tarjeta_salida?fecha=${date}`);
            const grupos = await res.json();

            if (!grupos.length) {
                listContainer.innerHTML = '<div style="grid-column: 1/-1; color:var(--text-muted); text-align:center; padding:20px;">No hay eventos agendados para este día.</div>';
                return;
            }

            listContainer.innerHTML = grupos.map(g => {
                const tag = g.tecnicos.map(t => t.split(' ')[0][0]).join('/'); // Iniciales simples
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
        const btnPrint = document.getElementById('ts-btn-print');
        
        const date = document.getElementById('ts-date-input').value;
        
        // El 'g.tag' contiene las iniciales concatenadas (ej: ND/LR)
        const tag = g.tag || g.tecnicos.map(t => t.split(' ')[0][0]).join('/');

        let html = `
<div class="card-header">AKRIMET - TARJETA DE SALIDA - ${date} [${tag}]</div>
<span class="section-label">DATOS DEL SERVICIO</span>
OT:        ${g.ot_nro}
CLIENTE:   ${g.cliente || '---'}
DIRECCION: ${g.direccion || '---'}
SERVICIO:  ${g.servicio || '---'}

<span class="section-label">GRUPO DE TRABAJO</span>
${g.tecnicos.map((t, i) => `[${i+1}] ${t}`).join('\n')}

<span class="section-label">RECURSOS ASIGNADOS</span>
VEHICULO:  ${g.vehiculo || 'No asignado'}
PATRONES:
${g.patrones.length ? g.patrones.map(p => ` - ${p}`).join('\n') : ' - Sin patrones registrados'}

<span class="section-label">OBSERVACIONES</span>
____________________________________________________________
____________________________________________________________
____________________________________________________________
`;
        
        viewContainer.innerHTML = html.replace(/\n/g, '<br>');
        viewContainer.classList.remove('hidden');
        if (btnPrint) btnPrint.classList.remove('hidden');
    }

    return { 
        init, refresh, selectEvent, openQuickCreate, 
        deleteEvent, moveEvent, splitEvent,
        toast, openPatronModal,
        getVehiculos, checkVehicleConflicts,
        refreshSingleEvent, removeSingleEvent, batchRefreshEvents, refreshEvents,
        renderTarjeta, quitarTecnicoDeGrupo
    };
})();

document.addEventListener('DOMContentLoaded', () => App.init());
