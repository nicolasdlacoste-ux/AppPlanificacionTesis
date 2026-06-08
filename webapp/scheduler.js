// ════════════════════════════════════════
// SCHEDULER ENGINE — Akrimet Planner v2.0
// ════════════════════════════════════════

var Scheduler = (() => {
    const START_H = 7;
    const END_H = 18;
    const HOURS = END_H - START_H; // 11 horas de rango (07:00 a 18:00)

    // Paleta muted por técnico
    const TECH_COLORS = [
        '#3b82f6','#8b5cf6','#06b6d4','#10b981',
        '#f59e0b','#ec4899','#6366f1','#14b8a6',
        '#f97316','#a78bfa'
    ];
    let techColorMap = {};

    let state = {
        tecnicos: [],
        eventos: [],
        currentDate: new Date(),
        view: 'week', // Vista semanal por defecto
        mode: 'scheduler', // 'scheduler' | 'resources'
        expandPats: false,
        soloOTs: false,
        holidays: {},
    };

    const norm = s => s ? s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim() : '';
    const fmtDate = d => {
        // Use local date to avoid UTC timezone shift issues
        const y = d.getFullYear();
        const m = String(d.getMonth()+1).padStart(2,'0');
        const day = String(d.getDate()).padStart(2,'0');
        return `${y}-${m}-${day}`;
    };

    const getWeekStart = d => {
        const day = new Date(d.getFullYear(), d.getMonth(), d.getDate());
        const dow = (day.getDay() + 6) % 7; // 0=lunes
        day.setDate(day.getDate() - dow);
        return day;
    };


    // Parsea fechas de Google ISO (con T) o Base de Datos (con espacio)
    function parseAnyDate(s) {
        if (!s) {
            console.warn("[DIAGNOSTIC] parseAnyDate: input is empty/undefined");
            return null;
        }
        if (s instanceof Date) return s;
        // Si tiene 'T', es ISO de Google. Si no, intentamos parsear formato DB "YYYY-MM-DD HH:mm:ss"
        if (s.includes('T')) {
            return new Date(s.replace(/([+-]\d{2}:\d{2}|Z)$/, ''));
        }
        // Formato DB: split por espacio
        const parts = s.split(' ');
        const dateParts = parts[0].split('-');
        if (dateParts.length < 3) return null;
        const y = parseInt(dateParts[0]);
        const m = parseInt(dateParts[1]) - 1;
        const d = parseInt(dateParts[2]);
        if (parts.length > 1) {
            const timeParts = parts[1].split(':');
            return new Date(y, m, d, parseInt(timeParts[0]), parseInt(timeParts[1] || 0), parseInt(timeParts[2] || 0));
        }
        // Solo fecha
        return new Date(y, m, d, 12, 0, 0); // Noon for all-day
    }

    function shouldRenderEvent(ev) {
        if (!ev) return false;
        // Ocultar eventos cancelados en Google aceptados por el usuario
        if (ev.sync_state === 'CANCELLED_IN_GOOGLE') {
            return false;
        }
        return true;
    }

    // Explota eventos multi-día en segmentos diarios
    function getExpandedEvents(events) {
        if (!events || events.length === 0) {
            console.log("[DIAGNOSTIC] getExpandedEvents: no events to expand");
        }
        const expanded = [];
        events.forEach(ev => {
            if (!shouldRenderEvent(ev)) return;
            
            console.log("[DIAGNOSTIC] Expanding event:", {
                id: ev.google_event_id,
                summary: ev.summary,
                inicio: ev.inicio,
                fin: ev.fin,
                tecnico_nombre: ev.tecnico_nombre
            });
            // [CANONICAL_MIGRATION] ev.start/ev.end -> ev.inicio/ev.fin
            const evStartStr = (ev.inicio || '');
            const evEndStr = (ev.fin || '');
            
            let dStart = parseAnyDate(evStartStr);
            let dEnd = parseAnyDate(evEndStr);
            
            if (!dStart || !dEnd) return;

            // Detección robusta de All-day
            const hasTimeSignature = evStartStr.includes('T') || evStartStr.includes(':') || evStartStr.length > 10;
            const isFunctionallyAllDay = dStart.getHours() === 0 && dStart.getMinutes() === 0 && dEnd.getHours() === 0 && dEnd.getMinutes() === 0 && dEnd.getTime() > dStart.getTime();
            
            const isTimed = hasTimeSignature && !isFunctionallyAllDay;
            const isAllDay = !hasTimeSignature || isFunctionallyAllDay;

            // PREVENIR SPILLOVER: Si es un evento temporizado que termina exactamente a las 00:00:00,
            // retrocedemos el dEnd 1 segundo para que lógicamente pertenezca al día anterior.
            if (isTimed && dEnd.getHours() === 0 && dEnd.getMinutes() === 0 && dEnd.getSeconds() === 0 && dEnd.getTime() > dStart.getTime()) {
                dEnd = new Date(dEnd.getTime() - 1000);
            }

            let current = new Date(dStart.getFullYear(), dStart.getMonth(), dStart.getDate(), 12, 0, 0);
            const endLimit = new Date(dEnd.getFullYear(), dEnd.getMonth(), dEnd.getDate(), 12, 0, 0);
            
            // Lógica de límites Google vs Locales
            const isInclusive = isTimed || (dEnd.getTime() === dStart.getTime());

            while (isInclusive ? (current <= endLimit) : (current < endLimit)) {
                const dayStr = fmtDate(current);
                const isFirstDay = fmtDate(current) === fmtDate(dStart);
                const isLastDay = isInclusive ? (fmtDate(current) === fmtDate(dEnd)) : (fmtDate(current) === fmtDate(new Date(dEnd.getFullYear(), dEnd.getMonth(), dEnd.getDate() - 1)));

                let sh = 7, eh = 16;
                if (isFirstDay && isTimed) sh = dStart.getHours() + dStart.getMinutes()/60;
                if (isLastDay && isTimed) eh = dEnd.getHours() + dEnd.getMinutes()/60;
                if (!isFirstDay && !isLastDay) { sh = 7; eh = 16; }
                if (isAllDay) { sh = 7; eh = 16; }

                // Aplicar clamping para alinear superposiciones desde la raíz
                if (sh >= END_H) { sh = 16; eh = 18; }
                else if (eh <= START_H) { sh = 7; eh = 9; }
                const clampSh = Math.max(sh, START_H);
                const clampEh = Math.min(eh, END_H);

                expanded.push({
                    ...ev,
                    _dayStr: dayStr,
                    _sh: clampSh,
                    _eh: clampEh,
                    _isFirstDay: isFirstDay,
                    _isLastDay: isLastDay,
                    _isMultiDay: (dEnd.getTime() - dStart.getTime()) > 86400000
                });
                current.setDate(current.getDate() + 1);
            }
        });
        return expanded;
    }

    function isOT(ev) {
        // [OT_NORMALIZATION] Clasificación centralizada en backend.
        // El frontend solo consume el campo canónico app_ots.
        const appOts = ev.app_ots || [];
        const isReserva = /RESERVA/i.test(ev.summary || '');
        
        const result = appOts.length > 0 || isReserva;

        if (state.soloOTs) {
            console.log(`[OT_NORMALIZATION_UI] Event ${ev.id}:`, {
                appOts,
                isReserva,
                result
            });
        }
        return result;
    }

    function getJobKey(ev) {
        const ots = ev.app_ots || [];
        const base = ots.length ? ots.slice().sort().join('-') : (ev.summary || 'no-title');
        // Usamos día + horas para que solo resalte los que están al mismo tiempo
        return `${base}_${ev._dayStr}_${ev._sh.toFixed(2)}_${ev._eh.toFixed(2)}`.replace(/\s+/g, '_');
    }

    function assignColors(tecnicos) {
        techColorMap = {};
        tecnicos.forEach((t, i) => {
            techColorMap[t.nombre] = TECH_COLORS[i % TECH_COLORS.length];
        });
    }

    function setState(partial) {
        console.log("[SCHEDULER] setState:", Object.keys(partial).join(', '));
        if (partial.eventos) {
            console.log(`[DIAGNOSTIC] setState: Recibidos ${partial.eventos.length} eventos.`);
            if (partial.eventos.length > 0) console.log("[DIAGNOSTIC] Sample event in setState:", partial.eventos[0]);
        }
        if (partial.tecnicos) console.log(`[SCHEDULER] Recibidos ${partial.tecnicos.length} técnicos.`);
        
        // Merge partial state, ensuring holidays is always an object
        Object.assign(state, partial);
        if (!state.holidays) state.holidays = {};
    }

    function toggleResourceMode() {
        state.mode = state.mode === 'resources' ? 'scheduler' : 'resources';
        render();
        return state.mode === 'resources';
    }

    // ─────────────────────────────────────
    // RENDERING
    // ─────────────────────────────────────

    function render() {
        console.trace("[UI_FORENSICS] Scheduler.render() invocado");
        console.log("[SCHEDULER] Iniciando render ciclo completo...");
        const scrollArea = document.getElementById('scheduler-scroll-area');
        const sTop = scrollArea ? scrollArea.scrollTop : 0;
        const sLeft = scrollArea ? scrollArea.scrollLeft : 0;

        try {
            renderTechLabels();
            renderHeader();
            renderRows();
            updateDateLabel();
            console.log("[SCHEDULER] Render finalizado con éxito.");
        } catch (err) {
            console.error("[SCHEDULER] Error fatal durante el render:", err);
        }

        if (scrollArea) {
            scrollArea.scrollTop = sTop;
            scrollArea.scrollLeft = sLeft;
        }
    }

    function renderTechLabels() {
        const col = document.getElementById('tech-labels-col');
        if (!col) return;
        col.innerHTML = '<div class="tech-label-spacer"></div>';
        state.tecnicos.forEach(t => {
            const color = techColorMap[t.nombre] || '#64748b';
            const fallbackInits = t.nombre.split(' ').filter(w => w.length > 2).map(w => w[0]).join('').toUpperCase().substring(0, 3);
            const displayInits = t.iniciales || fallbackInits;
            
            const cell = document.createElement('div');
            cell.className = 'tech-label-cell';
            cell.innerHTML = `
                <div class="tech-label-name">
                    <span class="tech-color-dot" style="background:${color}"></span>${t.nombre}
                </div>
                <div class="tech-label-init">${displayInits}</div>`;
            col.appendChild(cell);
        });
    }

    function renderHeader() {
        const row = document.getElementById('time-header-row');
        if (!row) return;
        row.innerHTML = '';

        if (state.mode === 'resources' && state.view === 'day') {
             const dateStr = fmtDate(state.currentDate);
             const isToday = dateStr === fmtDate(new Date());
             const cell = document.createElement('div');
             cell.className = 'time-header-cell day-view-cell' + (isToday ? ' today' : '');
             cell.style.flexDirection = 'column';
             cell.style.gap = '4px';
             
             const isHolidayName = state.holidays ? state.holidays[dateStr] : null;

             const label = document.createElement('span');
             label.textContent = state.currentDate.toLocaleDateString('es-ES', {weekday:'long', day:'numeric'}).toUpperCase();
             if (isToday) label.style.color = 'var(--accent)';
             if (isHolidayName) {
                 label.innerHTML += ` <span style="font-size:10px; color:var(--text-muted); font-style:italic; font-weight:normal; margin-left:4px;">Feriado</span>`;
                 cell.title = isHolidayName;
             }
             cell.appendChild(label);
             
             const alerts = calcDayAlerts(dateStr);
             const aDiv = document.createElement('div');
             aDiv.style.display = 'flex'; aDiv.style.gap = '8px'; aDiv.style.fontSize = '12px';
             
             if (alerts.patConf) {
                const i = document.createElement('i');
                i.className = 'fa-solid fa-triangle-exclamation'; i.style.color = '#d97706'; i.style.cursor = 'pointer';
                i.addEventListener('mouseenter', e => showTooltip(e, 'Patrones', alerts.details.pat));
                i.addEventListener('mouseleave', hideTooltip);
                aDiv.appendChild(i);
             }
             if (alerts.vehConf) {
                const i = document.createElement('i');
                i.className = 'fa-solid fa-truck-fast'; i.style.color = '#dc2626'; i.style.cursor = 'pointer';
                i.addEventListener('mouseenter', e => showTooltip(e, 'Vehículos', alerts.details.veh));
                i.addEventListener('mouseleave', hideTooltip);
                aDiv.appendChild(i);
             }
             if (alerts.vehReq) {
                const i = document.createElement('i');
                i.className = 'fa-solid fa-key'; i.style.color = '#ca8a04'; i.style.cursor = 'pointer';
                i.addEventListener('mouseenter', e => showTooltip(e, 'Requerimientos', ['Falta asignar vehículo a evento con requerimiento']));
                i.addEventListener('mouseleave', hideTooltip);
                aDiv.appendChild(i);
             }
             
             cell.appendChild(aDiv);
             row.appendChild(cell);
             return;
        }

        if (state.view === 'day') {
            // Day view: distribute equally across full width
            for (let h = START_H; h < END_H; h++) {
                const cell = document.createElement('div');
                cell.className = 'time-header-cell day-view-cell';
                cell.textContent = `${String(h).padStart(2,'0')}:00`;
                row.appendChild(cell);
            }
            // Add end label
            const endCell = document.createElement('div');
            endCell.className = 'time-header-cell day-view-cell';
            endCell.textContent = `${String(END_H).padStart(2,'0')}:00`;
            row.appendChild(endCell);
        } else {
            // Week view: 5 normal cols + 2 half-width weekend cols
            // Using CSS grid defined in renderWeekLayout()
            renderWeekLayout(row, false);
        }
    }

    function renderWeekLayout(container, isRow) {
        const ws = getWeekStart(state.currentDate);
        const todayStr = fmtDate(new Date());

        for (let i = 0; i < 7; i++) {
            const d = new Date(ws.getFullYear(), ws.getMonth(), ws.getDate() + i);
            const isWeekend = d.getDay() === 0 || d.getDay() === 6;
            const dateStr = fmtDate(d);
            const isToday = dateStr === todayStr;
            const holidayName = state.holidays ? state.holidays[dateStr] : null;
            const cell = document.createElement('div');

            if (isRow) {
                cell.className = 'day-cell' + (isWeekend ? ' weekend' : '') + (isToday ? ' today-col' : '') + (holidayName ? ' holiday' : '');
                cell.dataset.dow = i;
                cell.dataset.date = dateStr;
            } else {
                cell.className = 'time-header-cell week-day-header' +
                    (isWeekend ? ' weekend' : '') + (isToday ? ' today' : '') + (holidayName ? ' holiday' : '');
                if (holidayName) {
                    cell.title = holidayName;
                }
                
                const alerts = calcDayAlerts(fmtDate(d));
                const aDiv = document.createElement('div');
                aDiv.style.display = 'flex'; aDiv.style.gap = '5px'; aDiv.style.marginTop = '2px';

                if (alerts.patConf) {
                    const i = document.createElement('i');
                    i.className = 'fa-solid fa-triangle-exclamation'; i.style.color = '#d97706'; i.style.cursor = 'pointer';
                    i.addEventListener('mouseenter', e => showTooltip(e, 'Patrones', alerts.details.pat));
                    i.addEventListener('mouseleave', hideTooltip);
                    aDiv.appendChild(i);
                }
                if (alerts.vehConf) {
                    const i = document.createElement('i');
                    i.className = 'fa-solid fa-truck-fast'; i.style.color = '#dc2626'; i.style.cursor = 'pointer';
                    i.addEventListener('mouseenter', e => showTooltip(e, 'Vehículos', alerts.details.veh));
                    i.addEventListener('mouseleave', hideTooltip);
                    aDiv.appendChild(i);
                }
                if (alerts.vehReq) {
                    const i = document.createElement('i');
                    i.className = 'fa-solid fa-key'; i.style.color = '#ca8a04'; i.style.cursor = 'pointer';
                    i.addEventListener('mouseenter', e => showTooltip(e, 'Requerimientos', ['Falta asignar vehículo']));
                    i.addEventListener('mouseleave', hideTooltip);
                    aDiv.appendChild(i);
                }

                let dayLabelHTML = `
                    <span class="wh-day">${d.toLocaleDateString('es-ES', {weekday:'short'}).toUpperCase()}</span>
                    <span class="wh-date">${d.getDate()}/${d.getMonth()+1}</span>`;
                if (holidayName) {
                    dayLabelHTML += `<div style="font-size: 9px; margin-top: 2px; color: var(--text-muted); font-style: italic; font-weight: normal;">Feriado</div>`;
                }
                cell.innerHTML = dayLabelHTML;
                cell.appendChild(aDiv);
            }
            container.appendChild(cell);
        }
    }

    function renderRows() {
        console.log(`[SCHEDULER] renderRows: Dibujando filas para ${state.tecnicos.length} técnicos.`);
        const container = document.getElementById('scheduler-rows-container');
        if (!container) {
            console.error("[SCHEDULER] Error: No se encontró 'scheduler-rows-container' en el DOM.");
            return;
        }
        container.innerHTML = '';

        // Apply week-grid or day-grid class to scroll area
        const scrollArea = document.getElementById('scheduler-scroll-area');
        const wrapper = document.getElementById('scheduler-wrapper');
        
        if (wrapper) {
            if (state.mode === 'resources') wrapper.classList.add('res-mode');
            else wrapper.classList.remove('res-mode');
        }

        if (scrollArea) {
            if (state.view === 'week') {
                scrollArea.classList.add('week-mode');
                scrollArea.classList.remove('day-mode');
            } else {
                scrollArea.classList.add('day-mode');
                scrollArea.classList.remove('week-mode');
            }
        }

        // Pre-calcular frecuencia de técnicos por trabajo para mostrar iconos de grupo
        const expandedAll = getExpandedEvents(state.eventos);
        const jobFreq = {};
        expandedAll.forEach(ev => {
            const jk = getJobKey(ev);
            jobFreq[jk] = (jobFreq[jk] || 0) + 1;
        });
        state._jobFreq = jobFreq;

        state.tecnicos.forEach(t => {
            const row = document.createElement('div');
            row.className = 'scheduler-row';
            row.dataset.tech = t.nombre;

            if (state.view === 'day') {
                renderDayRow(row, t);
            } else {
                renderWeekRow(row, t);
            }

            row.addEventListener('dragover', e => { e.preventDefault(); row.classList.add('drag-over'); });
            row.addEventListener('dragleave', e => {
                if (!row.contains(e.relatedTarget)) row.classList.remove('drag-over');
            });
            row.addEventListener('drop', e => handleDrop(e, t));
            row.addEventListener('dblclick', e => handleDblClick(e, t));
            container.appendChild(row);
        });

        // Sincronizar altura de columna de técnicos cuando cambia el alto de las filas en resources
        if (state.mode === 'resources') {
            const labels = document.querySelectorAll('.tech-label-cell');
            const observer = new ResizeObserver(entries => {
                entries.forEach(entry => {
                    const row = entry.target;
                    const idx = Array.from(container.children).indexOf(row);
                    if (labels[idx]) labels[idx].style.height = row.offsetHeight + 'px';
                });
            });
            container.querySelectorAll('.scheduler-row').forEach(row => {
                observer.observe(row);
                const idx = Array.from(container.children).indexOf(row);
                if (labels[idx]) labels[idx].style.height = row.offsetHeight + 'px';
            });
        } else {
            document.querySelectorAll('.tech-label-cell').forEach(l => l.style.height = '');
        }
    }

    function renderDayRow(row, tech) {
        const color = techColorMap[tech.nombre] || '#64748b';
        const dateStr = fmtDate(state.currentDate);

        // Filter events for today + this tech using expanded logic
        const expanded = getExpandedEvents(state.eventos);
        console.log(`[DIAGNOSTIC] renderDayRow (${tech.nombre}): expanded count = ${expanded.length}`);
        let eventsToday = expanded.filter(ev => {
            // [CANONICAL_MIGRATION] match by calendar_id (fallback to nombre)
            const matchesTech = (ev.calendar_id && ev.calendar_id === tech.correo) || (!ev.calendar_id && ev.tecnico_nombre === tech.nombre);
            if (!matchesTech) return false;
            return ev._dayStr === dateStr;
        });
        console.log(`[DIAGNOSTIC] renderDayRow (${tech.nombre}): filtered count = ${eventsToday.length}`);
        
        if (state.soloOTs) eventsToday = eventsToday.filter(ev => isOT(ev));

        if (state.mode === 'resources') {
            eventsToday.forEach(ev => {
                row.appendChild(createResourceCard(ev, color, tech.nombre));
            });
            return;
        }

        const groups = getOverlapGroups(eventsToday);
        groups.forEach(group => {
            group.forEach((ev, colIdx) => {
                const block = createDayBlock(ev, color, colIdx, group.length);
                if (block) row.appendChild(block);
            });
        });
    }

    function renderWeekRow(row, tech) {
        const color = techColorMap[tech.nombre] || '#64748b';
        const ws = getWeekStart(state.currentDate);

        // Build day cells
        renderWeekLayout(row, true);

        const expanded = getExpandedEvents(state.eventos);
        
        let weekEvs = expanded.filter(ev => {
            // [CANONICAL_MIGRATION] match by calendar_id (fallback to nombre)
            const matchesTech = (ev.calendar_id && ev.calendar_id === tech.correo) || (!ev.calendar_id && ev.tecnico_nombre === tech.nombre);
            if (!matchesTech) return false;
            
            const d = parseAnyDate(ev._dayStr);
            const weEnd = new Date(ws.getFullYear(), ws.getMonth(), ws.getDate() + 6, 23, 59, 59);
            const match = d >= ws && d <= weEnd;
            return match;
        });

        console.log(`[DIAGNOSTIC] renderWeekRow (${tech.nombre}): filtered count = ${weekEvs.length}`);
        if (weekEvs.length > 0) {
            console.log(`[SCHEDULER] Row ${tech.nombre}: Encontrados ${weekEvs.length} segmentos en la semana.`);
        }
        if (state.soloOTs) weekEvs = weekEvs.filter(ev => isOT(ev));

        const byDay = {};
        weekEvs.forEach(ev => {
            if (!byDay[ev._dayStr]) byDay[ev._dayStr] = [];
            byDay[ev._dayStr].push(ev);
        });

        Object.entries(byDay).forEach(([dateStr, evs]) => {
            const d = parseAnyDate(dateStr);
            if (!d) return;
            const dow = (d.getDay() + 6) % 7;
            const cell = row.querySelector(`[data-dow="${dow}"]`);
            if (!cell) return;

            if (state.mode === 'resources') {
                evs.forEach(ev => {
                    cell.appendChild(createResourceCard(ev, color, tech.nombre));
                });
                return;
            }

            cell.style.position = 'relative';
            
            // Línea de tiempo horizontal (X=Tiempo), Apilamiento vertical (Y=Solapamiento)
            const groups = getOverlapGroups(evs);
            groups.forEach(group => {
                group.forEach((ev, colIdx) => {
                    const leftPct = ((ev._sh - START_H) / HOURS) * 100;
                    const widthPct = Math.max(((ev._eh - ev._sh) / HOURS) * 100, 2); 
                    const topPct = (colIdx / group.length) * 100;
                    const heightPct = (1 / group.length) * 100;

                    const block = document.createElement('div');
                    const jk = getJobKey(ev);
                    
                    block.className = 'ev-block week-ev-block' + (state.soloOTs && !isOT(ev) ? ' dim' : '');
                    if (ev._isMultiDay) {
                        if (!ev._isFirstDay) block.classList.add('cont-prev');
                        if (!ev._isLastDay) block.classList.add('cont-next');
                    }
                    
                    block.dataset.jobKey = jk;
        if (window.App && App.isBatchMode && App.isBatchMode() && App.isEventSelected(ev.google_event_id)) {
            block.classList.add("batch-selected");
        }

                    block.style.cssText = `
                        background:${color}dd;
                        left:${leftPct}%;
                        width:calc(${widthPct}% - 1px);
                        top:calc(${topPct}% + 1px);
                        height:calc(${heightPct}% - 2px);
                    `;
                    
                    const isGroup = state._jobFreq && state._jobFreq[jk] > 1;
                    const confirmedGrupoId = ev.extended_props?.private?.grupo_id || null;
                    const groupIcon = isGroup ? '<i class="fa-solid fa-users group-badge" title="Mismo trabajo"></i>' : '';
                    const confirmedIcon = confirmedGrupoId ? '<i class="fa-solid fa-link group-confirmed-badge" title="Grupo confirmado"></i>' : '';
                    block.innerHTML = `<div class="ev-title" style="font-size:9px">${ev.summary}</div>${groupIcon}${confirmedIcon}`;
                    if (confirmedGrupoId) block.dataset.grupoId = confirmedGrupoId;

                    // Hover: highlight por grupo_id confirmado (prioridad) o por jobKey
                    block.addEventListener('mouseenter', () => {
                        if (confirmedGrupoId) {
                            document.querySelectorAll(`.ev-block[data-grupo-id="${confirmedGrupoId}"]`).forEach(el => el.classList.add('group-active'));
                        } else {
                            document.querySelectorAll(`.ev-block[data-job-key="${jk}"]`).forEach(el => el.classList.add('group-active'));
                        }
                    });
                    block.addEventListener('mouseleave', () => {
                        if (confirmedGrupoId) {
                            document.querySelectorAll(`.ev-block[data-grupo-id="${confirmedGrupoId}"]`).forEach(el => el.classList.remove('group-active'));
                        } else {
                            document.querySelectorAll(`.ev-block[data-job-key="${jk}"]`).forEach(el => el.classList.remove('group-active'));
                        }
                    });

                    if (ev._syncing) {
                        block.setAttribute('draggable', 'false');
                        block.classList.add('syncing');
                        block.style.opacity = '0.5';
                        block.innerHTML += '<div class="ev-sync-spinner"><i class="fa-solid fa-rotate fa-spin"></i></div>';
                    } else {
                        block.setAttribute('draggable', 'true');
                        block.addEventListener('dragstart', e => {
                            e.dataTransfer.setData('application/json', JSON.stringify({
                                type: 'move',
                                eventId: ev.google_event_id || ev.id,
                                calendarId: ev.calendar_id || 'primary'
                            }));
                        });
                    }

                    block.addEventListener('click', e => { 
                        if (ev._syncing) return;
                        e.stopPropagation(); 
                        App.selectEvent(ev, e.ctrlKey || e.metaKey); 
                    });
                    cell.appendChild(block);
                });
            });
        });
    }

    function createDayBlock(ev, color, colIdx, totalCols) {
        // Usar valores pre-calculados por getExpandedEvents
        const leftPct = ((ev._sh - START_H) / HOURS) * 100;
        const widthPct = ((ev._eh - ev._sh) / HOURS) * 100;
        const topPct = totalCols > 1 ? (colIdx / totalCols) * 100 : 0;
        const heightPct = totalCols > 1 ? (1 / totalCols) * 100 : 100;

        const block = document.createElement('div');
        const jk = getJobKey(ev);
        
        block.className = 'ev-block' + (state.soloOTs && !isOT(ev) ? ' dim' : '');
        if (ev._isMultiDay) {
            if (!ev._isFirstDay) block.classList.add('cont-prev');
            if (!ev._isLastDay) block.classList.add('cont-next');
        }
        if (ev.sync_state === 'CANCELLED_IN_GOOGLE') {
            block.classList.add('cancelled-google');
        }
        
        block.dataset.jobKey = jk;
        if (window.App && App.isBatchMode && App.isBatchMode() && App.isEventSelected(ev.google_event_id)) {
            block.classList.add("batch-selected");
        }

        block.style.cssText = `
            left:${leftPct}%;
            width:${Math.max(widthPct, 1.5)}%;
            background:${color}dd;
            top:calc(${topPct}% + 4px);
            height:calc(${heightPct}% - 8px);
            bottom:unset;`;
        const isGroup = state._jobFreq && state._jobFreq[jk] > 1;
        const confirmedGrupoId = ev.extended_props?.private?.grupo_id || null;
        const groupIcon = isGroup ? '<i class="fa-solid fa-users group-badge" title="Mismo trabajo"></i>' : '';
        const confirmedIcon = confirmedGrupoId ? '<i class="fa-solid fa-link group-confirmed-badge" title="Grupo confirmado"></i>' : '';
        if (confirmedGrupoId) block.dataset.grupoId = confirmedGrupoId;

        block.innerHTML = `
            <div class="ev-title">${ev.summary}</div>
            <div class="ev-time">${fmtHour(sh)}–${fmtHour(eh)}</div>
            ${groupIcon}${confirmedIcon}
        `;

        // Hover: highlight por grupo_id confirmado (prioridad) o por jobKey
        block.addEventListener('mouseenter', () => {
            if (confirmedGrupoId) {
                document.querySelectorAll(`.ev-block[data-grupo-id="${confirmedGrupoId}"]`).forEach(el => el.classList.add('group-active'));
            } else {
                document.querySelectorAll(`.ev-block[data-job-key="${jk}"]`).forEach(el => el.classList.add('group-active'));
            }
        });
        block.addEventListener('mouseleave', () => {
            if (confirmedGrupoId) {
                document.querySelectorAll(`.ev-block[data-grupo-id="${confirmedGrupoId}"]`).forEach(el => el.classList.remove('group-active'));
            } else {
                document.querySelectorAll(`.ev-block[data-job-key="${jk}"]`).forEach(el => el.classList.remove('group-active'));
            }
        });

        
        // Habilitar arrastre para re-agendamiento (si no está sincronizando)
        if (ev._syncing) {
            block.setAttribute('draggable', 'false');
            block.classList.add('syncing');
            block.style.opacity = '0.5';
            block.style.cursor = 'wait';
            block.innerHTML += '<div class="ev-sync-spinner"><i class="fa-solid fa-rotate fa-spin"></i></div>';
        } else if (ev.sync_state === 'CANCELLED_IN_GOOGLE') {
            block.setAttribute('draggable', 'false');
            block.title = "Evento eliminado en Google Calendar";
        } else {
            block.setAttribute('draggable', 'true');
            block.addEventListener('dragstart', e => {
                e.dataTransfer.setData('application/json', JSON.stringify({
                    type: 'move',
                    eventId: ev.google_event_id || ev.id,
                    calendarId: ev.calendar_id || 'primary'
                }));
                block.classList.add('dragging');
            });
            block.addEventListener('dragend', () => block.classList.remove('dragging'));
        }

        block.addEventListener('click', e => { 
            if (ev._syncing) return;
            e.stopPropagation(); 
            if (ev.sync_state === 'CANCELLED_IN_GOOGLE') {
                App.toast('Este evento fue eliminado en Google. Pendiente de revisión.', 'warning');
                return;
            }
            App.selectEvent(ev, e.ctrlKey || e.metaKey); 
        });
        return block;
    }

    // ─────────────────────────────────────
    // RESOURCES CARDS
    // ─────────────────────────────────────

    function createResourceCard(ev, color, techNombre) {
        const card = document.createElement('div');
        card.className = 'res-card' + (ev._syncing ? ' syncing' : '');
        if (window.App && App.isBatchMode && App.isBatchMode() && App.isEventSelected(ev.google_event_id)) {
            card.classList.add("batch-selected");
        }
        if (ev.sync_state === 'CANCELLED_IN_GOOGLE') {
            card.classList.add('cancelled-google');
        }
        if (ev._syncing) {
            card.style.opacity = '0.6';
            card.style.pointerEvents = 'none';
        }

        const checkMultiDayConstraint = () => {
             const isTimed = (ev.inicio || '').includes('T');
             const d1 = ev.inicio;
             const d2 = ev.fin;
             if (!isTimed && d1 && d2 && d1 !== d2) {
                 App.toast('Evento multi-día (lectura). Por favor utiliza el botón de "Individualizar" abriendo los detalles antes de modificar sus recursos.', 'warning');
                 return true;
             }
             return false;
        };

        // 1. Evento
        const otsStr = (ev.app_ots || []).join(', ');
        const evBox = document.createElement('div');
        evBox.className = 'res-rc-ev';
        evBox.innerHTML = `
            <div class="res-rc-ev-title">${ev.summary || 'Evento'}</div>
            ${otsStr ? `<div class="res-rc-ev-ots">OTs: ${otsStr}</div>` : ''}
            <div style="font-size:9px;color:var(--text-muted);margin-top:2px">${fmtHour(ev._sh)} - ${fmtHour(ev._eh)}</div>
        `;
        evBox.addEventListener('click', (e) => {
            e.stopPropagation();
            if (ev.sync_state === 'CANCELLED_IN_GOOGLE') {
                App.toast('Este evento fue eliminado en Google. Pendiente de revisión.', 'warning');
                return;
            }
            App.selectEvent(ev, e.ctrlKey || e.metaKey); // Abrir panel derecho o batch
        });
        card.appendChild(evBox);

        // 2. Patrones
        const props = ev.extended_props?.private || {};
        const isReq = (props.app_requiere_vehiculo === 'true');
        let pats = getEventPats(ev);

        // Validar conflictos de patrones (Día completo)
        const expHoy = getExpandedEvents(state.eventos).filter(e => e._dayStr === ev._dayStr);
        let patConf = false;
        let patConfMsg = '';
        for (const p of pats) {
            if (checkPatternConflict(p, expHoy, ev.google_event_id)) {
                patConf = true;
                patConfMsg = `Conflicto: El patrón '${p}' está bloqueado por otro técnico que no comparte OT.`;
                break;
            }
        }

        const patBox = document.createElement('div');
        patBox.className = 'res-rc-pats' + (patConf ? ' conflict' : '');
        patBox.innerHTML = `
            <div class="res-rc-pats-header" title="${patConfMsg}">
                <div><i class="fa-solid fa-tools"></i> <b>${pats.length}</b> Pats ${patConf ? '<i class="fa-solid fa-triangle-exclamation"></i>':''}</div>
                <i class="fa-solid fa-plus btn-pat-expand" style="cursor:pointer" title="Expandir/Agregar" data-id="${ev.google_event_id}"></i>
            </div>
            <div class="res-rc-pats-list" style="display:${state.expandPats ? 'flex' : 'none'}">
                ${pats.map(p => `<div class="res-rc-pat-item"><span>${p}</span> <i class="fa-solid fa-xmark btn-del-pat" data-pat="${p}" title="Quitar"></i></div>`).join('')}
                <button class="btn-secondary btn-add-pat" style="font-size:9px; padding:2px; margin-top:4px"><i class="fa-solid fa-plus"></i> Añadir</button>
            </div>
        `;
        card.appendChild(patBox);

        patBox.querySelector('.btn-pat-expand').addEventListener('click', e => {
            e.stopPropagation();
            const list = patBox.querySelector('.res-rc-pats-list');
            list.style.display = list.style.display === 'none' ? 'flex' : 'none';
        });

        patBox.querySelectorAll('.btn-del-pat').forEach(b => {
             b.addEventListener('click', async e => {
                 e.stopPropagation();
                 if (checkMultiDayConstraint()) return;
                 const p = b.dataset.pat;
                 if (confirm(`Quitar ${p} del evento?`)) {
                     await updateResourceMetadata(ev, { patrones: pats.filter(x => x !== p) });
                 }
             });
        });

        patBox.querySelector('.btn-add-pat').addEventListener('click', e => {
             e.stopPropagation();
             if (checkMultiDayConstraint()) return;
             App.openPatronModal(pats, async (newPats) => {
                 await updateResourceMetadata(ev, { patrones: newPats });
             });
        });

        // 3. Vehículos
        const vehBox = document.createElement('div');
        vehBox.className = 'res-rc-veh';
        
        let cv = props.app_vehiculo || ev.app_vehiculo || '';
        const vehiculos = App.getVehiculos() || [];
        
        // Check alerts
        let confStr = '';
        if (cv) {
             const gid = (ev.extended_props?.private?.grupo_id) || null;
             const cfInfo = App.checkVehicleConflicts(cv, ev._dayStr, ev._sh, ev._eh, ev.google_event_id, techNombre, gid);
             if (cfInfo) {
                 confStr = cfInfo;
                 vehBox.classList.add('conflict');
             }
        } else if (isReq) {
             confStr = 'Requiere vehículo pero no tiene asignado';
             vehBox.classList.add('conflict');
        }

        let selHtml = `<select class="res-rc-veh-sel" title="${confStr}">
            <option value="">(Sin vehículo${isReq? ' - Req.':''})</option>
            ${vehiculos.map(v => `<option value="${v.nombre}" ${v.nombre===cv?'selected':''}>${v.nombre}</option>`).join('')}
        </select>`;
        
        vehBox.innerHTML = `<i class="fa-solid fa-truck-fast"></i> ` + selHtml;
        card.appendChild(vehBox);

        const selEl = vehBox.querySelector('select');
        selEl.addEventListener('click', e => e.stopPropagation());
        selEl.addEventListener('change', async e => {
            const val = e.target.value;
            if (checkMultiDayConstraint()) {
                 selEl.value = cv; // Revertir selector
                 return;
            }
            
            // Para propagar a todo el día: el usuario dijo "se podría extender a todos los eventos del día" 
            const exp = getExpandedEvents(state.eventos);
            const eventsDelDia = exp.filter(x => {
                const matchesTech = (x.calendar_id && ev.calendar_id && x.calendar_id === ev.calendar_id) || (!x.calendar_id && x.tecnico_nombre === techNombre);
                return matchesTech && x._dayStr === ev._dayStr;
            });
            if (eventsDelDia.length > 1 && confirm(`¿Desea asignar el vehículo ${val||'Ninguno'} a TODOS los ${eventsDelDia.length} eventos de ${techNombre} de este día?`)) {
                 App.toast('Aplicando a todos los eventos...');
                 for (const x of eventsDelDia) {
                     await updateResourceMetadata(x, { vehiculo: val || null, requiere_vehiculo: null }, false); 
                 }
                 App.refresh();
            } else {
                 await updateResourceMetadata(ev, { vehiculo: val || null, requiere_vehiculo: null });
            }
        });

        return card;
    }

    async function updateResourceMetadata(ev, partial, reqRefresh = true) {
        if(reqRefresh) App.toast('Guardando cambios...', 'info');
        try {
            const calId = ev.calendar_id;
            const props = ev.extended_props?.private || {};
            // Si hay patrones omitidos en partial, re-enviar los actuales.
            let patsToSave = partial.patrones !== undefined ? partial.patrones : null;
            if (patsToSave === null) {
                const ep = props.app_patrones || ev.app_patrones || '[]';
                patsToSave = typeof ep === 'string' ? JSON.parse(ep) : ep;
            }
            if (!Array.isArray(patsToSave)) patsToSave = [];

            const bBody = {
                 event_id: ev.google_event_id,
                 calendar_id_origen: calId,
                 correo_destino: calId,
                 nueva_fecha: ev.inicio ? ev.inicio.substring(0,10) : ev._dayStr, // no altera start/end reales, la API los mantiene si no van
                 patrones: patsToSave,
                 vehiculo: partial.vehiculo !== undefined ? partial.vehiculo : props.app_vehiculo,
                 requiere_vehiculo: partial.requiere_vehiculo !== undefined ? partial.requiere_vehiculo : (props.app_requiere_vehiculo === 'true')
            };

            const r = await fetch(`/api/eventos/${ev.google_event_id}/mover`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(bBody)
            });
            if (!r.ok) throw new Error(await r.text());
            if (reqRefresh) {
                 App.toast('Cambios guardados ✓', 'success');
                 App.refresh();
            }
        } catch(e) {
            App.toast(e, 'error');
        }
    }

    // ─────────────────────────────────────
    // HELPERS
    // ─────────────────────────────────────

    function calcDayAlerts(dateStr) {
         let patConf = false, vehConf = false, vehReq = false;
         let details = { pat: [], veh: [] };
         const exp = getExpandedEvents(state.eventos).filter(e => e._dayStr === dateStr);
         
         exp.forEach(ev => {
             const props = ev.extended_props?.private || {};
             const cv = props.app_vehiculo || ev.app_vehiculo;
             const isReq = (props.app_requiere_vehiculo === 'true');
             
             if (isReq && !cv) vehReq = true;
             else if (cv) {
                 const resId = ev.tecnico_nombre || ev['Técnico'];
                 const gid = (ev.extended_props?.private?.grupo_id) || null;
                 const cfo = App.checkVehicleConflicts(cv, dateStr, ev._sh, ev._eh, ev.google_event_id, resId, gid);
                 if (cfo) {
                     vehConf = true;
                     details.veh.push(`${cv}: ${ev.summary} (${resId}) tiene conflicto.`);
                 }
             }

             const evPats = getEventPats(ev);
             for (const p of evPats) {
                 const conflictInfo = checkPatternConflict(p, exp, ev.google_event_id);
                 if (conflictInfo === true) {
                     patConf = true;
                     details.pat.push(`${p}: Usado en "${ev.summary}" con conflicto de grupo.`);
                 }
             }
         });

         // De-duplicate details
         details.pat = [...new Set(details.pat)];
         details.veh = [...new Set(details.veh)];

         return { patConf, vehConf, vehReq, details };
    }

    function showTooltip(e, title, items) {
        const tt = document.getElementById('alert-tooltip');
        if (!tt || !items.length) return;
        
        tt.innerHTML = `<div class="tooltip-header">${title}</div>`;
        items.forEach(it => {
            tt.innerHTML += `<div class="tooltip-item"><i class="fa-solid fa-circle-info"></i><span>${it}</span></div>`;
        });
        
        tt.classList.remove('hidden');
        const rect = e.target.getBoundingClientRect();
        tt.style.left = (rect.left) + 'px';
        tt.style.top = (rect.bottom + 5) + 'px';
        
        // Ajustar si se sale por la derecha
        if (rect.left + 250 > window.innerWidth) {
            tt.style.left = (window.innerWidth - 260) + 'px';
        }
    }

    function hideTooltip() {
        const tt = document.getElementById('alert-tooltip');
        if (tt) tt.classList.add('hidden');
    }

    function checkPatternConflict(patName, dayEvents, currentEvId) {
        if (!patName) return false;
        
        const currentEv = dayEvents.find(e => e.google_event_id === currentEvId);
        if (!currentEv) return false;
        
        const currentOTs = getEventOTs(currentEv);
        
        // Buscar otros eventos que usen el mismo patrón
        const othersUsingPat = dayEvents.filter(e => {
            if (e.google_event_id === currentEvId) return false;
            const ePats = getEventPats(e);
            return ePats.includes(patName);
        });
        
        if (othersUsingPat.length === 0) return false;
        
        // Si hay otros, verificar si TODOS comparten al menos una OT con el evento actual
        // (Lógica de Grupos: si comparten OT, están en el mismo equipo)
        // Nota: Para simplificar, si el otro evento no comparte ninguna OT con el actual, ya hay conflicto.
        for (const other of othersUsingPat) {
            const otherOTs = getEventOTs(other);
            const common = currentOTs.filter(ot => otherOTs.includes(ot));
            if (common.length === 0) {
                 // No hay OT en común -> Conflicto de día completo
                 return true;
            }
        }
        
        return false;
    }

    function getEventOTs(ev) {
        let ots = ev.app_ots || [];
        if (typeof ots === 'string') {
            try { ots = JSON.parse(ots); } catch { ots = []; }
        }
        return Array.isArray(ots) ? ots : [];
    }

    function getEventPats(ev) {
        const props = ev.extended_props?.private || {};
        let pats = props.app_patrones || ev.app_patrones || [];
        if (typeof pats === 'string') {
            try { pats = JSON.parse(pats); } catch { pats = []; }
        }
        return Array.isArray(pats) ? pats : [];
    }

    function fmtHour(h) {
        const hh = Math.floor(h);
        const mm = Math.round((h - hh) * 60);
        return `${String(hh).padStart(2,'0')}:${String(mm).padStart(2,'0')}`;
    }

    function getOverlapGroups(events) {
        if (!events.length) return [];

        const sorted = [...events].sort((a, b) => a._sh - b._sh);
        const groups = [];
        let curGroup = [];
        let groupEndH = null;

        sorted.forEach(ev => {
            const evSh = ev._sh;
            const evEh = ev._eh;
            if (curGroup.length === 0 || evSh < groupEndH) {
                curGroup.push(ev);
                groupEndH = groupEndH !== null ? Math.max(groupEndH, evEh) : evEh;
            } else {
                groups.push(curGroup);
                curGroup = [ev];
                groupEndH = evEh;
            }
        });
        if (curGroup.length) groups.push(curGroup);
        return groups;
    }

    function updateDateLabel() {
        const label = document.getElementById('current-date-label');
        if (!label) return;
        if (state.view === 'day') {
            label.textContent = state.currentDate.toLocaleDateString('es-ES', {
                weekday:'long', day:'numeric', month:'long', year:'numeric'
            }).toUpperCase();
        } else {
            const ws = getWeekStart(state.currentDate);
            const we = new Date(ws.getFullYear(), ws.getMonth(), ws.getDate() + 6);
            label.textContent = `Sem. ${ws.getDate()}/${ws.getMonth()+1} — ${we.getDate()}/${we.getMonth()+1}/${we.getFullYear()}`;
        }
    }

    // ─────────────────────────────────────
    // DRAG & DROP
    // ─────────────────────────────────────

    function handleDrop(e, tech) {
        e.preventDefault();
        document.querySelectorAll('.scheduler-row').forEach(r => r.classList.remove('drag-over'));
        
        try {
            const dragData = JSON.parse(e.dataTransfer.getData('application/json'));
            let hour = undefined;
            let targetDateStr = fmtDate(state.currentDate);

            // 1. Calcular Fecha (si estamos en vista semanal, buscar la celda)
            if (state.view === 'week') {
                const cell = e.target.closest('.day-cell');
                if (cell && cell.dataset.date) {
                    targetDateStr = cell.dataset.date;
                }
            }

            // 2. Calcular Hora
            if (state.view === 'week') {
                const cell = e.target.closest('.day-cell');
                if (cell) {
                    const rect = cell.getBoundingClientRect();
                    const relX = e.clientX - rect.left;
                    const pct = Math.max(0, Math.min(1, relX / rect.width));
                    hour = Math.floor((START_H + pct * HOURS) * 2) / 2;
                }
            } else if (state.view === 'day') {
                const scrollArea = document.getElementById('scheduler-scroll-area');
                const contentLeft = scrollArea.getBoundingClientRect().left;
                const relX = e.clientX - contentLeft + scrollArea.scrollLeft;
                const totalW = scrollArea.scrollWidth;
                const pct = Math.max(0, Math.min(1, relX / totalW));
                hour = Math.floor((START_H + pct * HOURS) * 2) / 2;
            }

            if (dragData.type === 'move') {
                // Caso: Mover evento existente
                App.moveEvent(dragData.eventId, dragData.calendarId, tech.correo, targetDateStr, hour);
            } else {
                // Caso: Crear evento rápido desde backlog
                App.openQuickCreate(tech, parseAnyDate(targetDateStr), hour !== undefined ? hour : 7, dragData);
            }
        } catch (err) {
            console.error('Drop error:', err);
        }
    }

    function handleDblClick(e, tech) {
        let hour = 7;
        let targetDate = state.currentDate;
        
        if (state.view === 'week') {
            const cell = e.target.closest('.day-cell');
            if (cell && cell.dataset.date) {
                targetDate = parseAnyDate(cell.dataset.date);
                const rect = cell.getBoundingClientRect();
                const relX = e.clientX - rect.left;
                const pct = Math.max(0, Math.min(1, relX / rect.width));
                hour = Math.floor((START_H + pct * HOURS) * 2) / 2;
            }
        } else if (state.view === 'day') {
            const scrollArea = document.getElementById('scheduler-scroll-area');
            const contentLeft = scrollArea.getBoundingClientRect().left;
            const relX = e.clientX - contentLeft + scrollArea.scrollLeft;
            const totalW = scrollArea.scrollWidth;
            const pct = Math.max(0, relX / totalW);
            hour = Math.floor((START_H + pct * HOURS) * 2) / 2;
        }
        App.openQuickCreate(tech, targetDate, hour, null);
    }

    // ─────────────────────────────────────
    // NAVIGATION
    // ─────────────────────────────────────

    function navigate(delta) {
        const d = state.currentDate;
        if (state.view === 'day') {
            state.currentDate = new Date(d.getFullYear(), d.getMonth(), d.getDate() + delta);
        } else {
            state.currentDate = new Date(d.getFullYear(), d.getMonth(), d.getDate() + delta * 7);
        }
        render();
    }

    function goToday() {
        state.currentDate = new Date();
        render();
    }

    function setView(v) {
        state.view = v;
        document.querySelectorAll('.view-btn').forEach(b => b.classList.remove('active'));
        const btn = document.getElementById(v === 'day' ? 'btn-view-day' : 'btn-view-week');
        if (btn) btn.classList.add('active');
        render();
    }

    const api = {
        setState,
        render,
        renderRows,
        renderWeekRow,
        renderDayRow,
        assignColors,
        navigate,
        goToday,
        setView,
        toggleResourceMode
    };

    console.log("[SCHEDULER] Engine loaded. Methods:", Object.keys(api).join(', '));
    window.Scheduler = api;
    return api;
})();
