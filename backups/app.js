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
    let _patronModalCallback = null;
    let _globalSyncing = false;

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
        try {
            const evRes = await fetch(`/api/eventos?t=${Date.now()}`);
            if (!evRes.ok) return;
            const newEvents = await evRes.json();
            const merged = [];
            for (let i = 0; i < newEvents.length; i++) {
                const incoming = newEvents[i];
                let local = null;
                for (let j = 0; j < _eventos.length; j++) {
                    if (_eventos[j].id === incoming.id) { local = _eventos[j]; break; }
                }
                if (local && local._syncing) merged.push(local);
                else merged.push(incoming);
            }
            for (let j = 0; j < _eventos.length; j++) {
                const local = _eventos[j];
                if (local._syncing) {
                    let found = false;
                    for (let k = 0; k < merged.length; k++) {
                        if (merged[k].id === local.id) { found = true; break; }
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
        const idx = _eventos.findIndex(e => e.id === eventData.id);
        if (idx !== -1) {
            const current = _eventos[idx];
            if (eventData.version !== undefined && current.version !== undefined && eventData.version < current.version) {
                console.warn("[Sync] Ignorando update obsoleto para " + eventData.id);
                return;
            }
            _eventos[idx] = eventData;
        } else {
            // Asegurar que el evento tenga el campo resourceId para el scheduler
            if (!eventData.resourceId && (eventData.correo_tecnico || eventData.tecnico_id)) {
                const tech = _tecnicos.find(t => t.correo === eventData.correo_tecnico || t.id === eventData.tecnico_id);
                if (tech) eventData.resourceId = tech.nombre;
            }
            _eventos.push(eventData);
        }
        Scheduler.setState({ tecnicos: _tecnicos, eventos: _eventos, holidays: _holidays });
        Scheduler.render();
        Backlog.render(_ots, _eventos);
        updateFooter();
    }

    /** Marca todos los eventos de un grupo como 'sincronizando' para feedback visual inmediato. */
    function setGroupSyncing(grupoId, syncing) {
        if (!grupoId) return;
        let changed = false;
        _eventos.forEach(ev => {
            if (!ev) return;
            const gid = ev.extendedProperties?.private?.grupo_id || ev._grupo?.grupo_id;
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
    function removeSingleEvent(eventId) {
        _eventos = _eventos.filter(e => e.id !== eventId);
        Scheduler.setState({ tecnicos: _tecnicos, eventos: _eventos, holidays: _holidays });
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
        Scheduler.setState({ tecnicos: _tecnicos, eventos: _eventos, holidays: _holidays });
        Scheduler.render();
        Backlog.render(_ots, _eventos);
        updateFooter();
    }



    function startHeartbeat() {
        const sendPulse = () => {
            fetch('/api/heartbeat', { method: 'POST' }).catch(() => {});
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
            _ots      = results.find(r => r.id === 'ots')?.data || [];
            _patrones = results.find(r => r.id === 'patrones')?.data || [];
            _vehiculos= results.find(r => r.id === 'vehiculos')?.data || [];
            
            const configRes = results.find(r => r.id === 'config');
            _holidays = (configRes?.ok && configRes.data?.holidays) ? configRes.data.holidays : {};

            console.log(`[BOOT] loadAll: Datos listos -> Tecs: ${_tecnicos.length}, Evs: ${_eventos.length}`);

            window._tecnicos = _tecnicos;
            Scheduler.assignColors(_tecnicos);
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
    function selectEvent(ev) {
        RightPanel.showEventDetail(ev);
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

        if (_globalSyncing) {
            toast('Operación en curso, por favor espera...', 'warning');
            return;
        }
        const eventIdx = _eventos.findIndex(e => e.id === eventId);
        if (eventIdx === -1 || _eventos[eventIdx]._syncing) return;
        _globalSyncing = true;
        const currentEvent = _eventos[eventIdx];
        const destTec = _tecnicos.find(t => t.correo === destCorreo);
        const nuevoTecNombre = destTec ? destTec.nombre : currentEvent.resourceId;

        // Función interna que hace el trabajo
        const doMove = async (scope) => {
            // Guardar estado original para posible rollback
            const originalEventsCopy = JSON.parse(JSON.stringify(_eventos));

            // --- ACTUALIZACIÓN OPTIMISTA ---
            const applyOptimistic = (evToModify) => {
                evToModify.resourceId = (scope === 'grupo' && destCorreo !== calendarId) ? nuevoTecNombre : 
                                        (evToModify.id === eventId ? nuevoTecNombre : evToModify.resourceId);
                evToModify['Técnico'] = evToModify.resourceId;
                
                // IMPORTANTE: Actualizar el ID del calendario para que el próximo drag sea correcto
                if (destCorreo) {
                    evToModify.calendarId = destCorreo;
                    evToModify.calendar_id = destCorreo;
                }

                if (nuevaFecha) {
                    const sTime = evToModify.start ? evToModify.start.substring(10) : 'T08:00:00';
                    const eTime = evToModify.end ? evToModify.end.substring(10) : 'T10:00:00';
                    evToModify.start = nuevaFecha + sTime;
                    evToModify.end = nuevaFecha + eTime;
                    evToModify.Inicio = evToModify.start;
                    evToModify.Fin = evToModify.end;
                    evToModify._dayStr = nuevaFecha;
                }
                
                // sh/eh solo aplican al evento arrastrado si vino con hora en vista diaria
                if (hora !== undefined && evToModify.id === eventId) {
                    const duration = evToModify._eh - evToModify._sh;
                    evToModify._sh = hora;
                    evToModify._eh = hora + (duration > 0 ? duration : 1);
                    const fmtH = (h) => {
                        const integer = Math.floor(h);
                        const minutes = Math.round((h - integer) * 60);
                        return `T${String(integer).padStart(2,'0')}:${String(minutes).padStart(2,'0')}:00`;
                    };
                    const baseDate = evToModify.start ? evToModify.start.substring(0, 10) : nuevaFecha;
                    evToModify.start = baseDate + fmtH(evToModify._sh);
                    evToModify.end = baseDate + fmtH(evToModify._eh);
                    evToModify.Inicio = evToModify.start;
                    evToModify.Fin = evToModify.end;
                }
                evToModify._syncing = true;
            };

            if (scope === 'grupo' && grupoInfo) {
                grupoInfo.event_ids.forEach(eid => {
                    const idx = _eventos.findIndex(e => e.id === eid);
                    if (idx !== -1) applyOptimistic(_eventos[idx]);
                });
            } else {
                applyOptimistic(_eventos[eventIdx]);
            }

            Scheduler.setState({ tecnicos: _tecnicos, eventos: [..._eventos], holidays: _holidays });
            Scheduler.render();

            // --- LLAMADA API ---
            let endpoint = scope === 'grupo' ? 'mover_grupo' : 'mover';
            if (scope === 'grupo' && destCorreo !== calendarId && destCorreo) {
                endpoint = 'reasignar_tecnico_grupo';
            }

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
                toast('Evento movido ✓', 'success');
                
                // Limpiar flag de sincronización inmediatamente
                const clearFlags = () => {
                    if (scope === 'grupo' && grupoInfo) {
                        grupoInfo.event_ids.forEach(eid => {
                            const ev = _eventos.find(e => e.id === eid);
                            if (ev) delete ev._syncing;
                        });
                    } else {
                        const ev = _eventos.find(e => e.id === eventId);
                        if (ev) delete ev._syncing;
                    }
                };
                clearFlags();

                // Si la API dice que el ID cambió (fallback delete+insert)
                // Forzamos refresh para capturar cambios por auto-agrupación (grupo_id, títulos con tags)
                if (data.event_id && data.event_id !== eventId) {
                    const ev = _eventos.find(e => e.id === eventId);
                    if (ev) ev.id = data.event_id;
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

        if (grupoInfo && grupoInfo.tecnico_nombres.length > 1) {
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
        }
    }

    async function deleteEvent(eventId, calendarId) {
        if (!calendarId) { toast('Sin calendar ID para eliminar', 'error'); return; }
        if (!confirm('¿Estás seguro de que deseas eliminar este evento de Google Calendar?')) return;
        
        _globalSyncing = true;

        // ── Actualización optimista: quitar de memoria ANTES de que responda el servidor
        removeSingleEvent(eventId);
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
        if (btnViewDay) btnViewDay.addEventListener('click', () => Scheduler.setView('day'));
        if (btnViewWeek) btnViewWeek.addEventListener('click', () => Scheduler.setView('week'));
        
        if (chkSoloOts) {
            chkSoloOts.addEventListener('change', e => {
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
        
        // Si no se pasó grupoId explícitamente, intentar obtenerlo del evento actual
        if (!grupoId && evId) {
            const evTarget = _eventos.find(e => e.id === evId);
            if (evTarget && evTarget.extendedProperties && evTarget.extendedProperties.private) {
                grupoId = evTarget.extendedProperties.private.grupo_id;
            }
        }

        // Formatear dateStr si es Date
        const getStr = d => {
            if (typeof d === 'string') return d.substring(0, 10);
            return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
        };
        const targetDate = getStr(dateStr);
        
        // Filtrar eventos del mismo día que usen el mismo vehículo
        const sameDayEvents = _eventos.filter(ev => {
            if (ev.id === evId) return false;
            
            const props = (ev.extendedProperties && ev.extendedProperties.private) || {};
            if (props.app_vehiculo !== vehiculoNombre) return false;

            // REGLA CLAVE: Si pertenecen al mismo grupo, NO es conflicto
            if (grupoId && props.grupo_id === grupoId) return false;
            
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
        renderTarjeta, quitarTecnicoDeGrupo, setGroupSyncing,
        openSFLink, showSFLinksPopup,
        getBacklogOTs: () => _ots,
        getState: () => ({ _tecnicos, _eventos, _ots, _patrones, _vehiculos, _holidays })
    };
})();

// Exposición global para depuración (F12)
window.APP_DEBUG = { App, Scheduler, Backlog, RightPanel, ConfigMenu, PollManager };

document.addEventListener('DOMContentLoaded', () => App.init());
