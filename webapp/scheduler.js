// ════════════════════════════════════════
// SCHEDULER ENGINE — Akrimet Planner v2.0
// ════════════════════════════════════════

const Scheduler = (() => {
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

    // Extraer números de OT del título del evento
    function extractOTsFromTitle(title) {
        if (!title) return [];
        return (title.match(/\d{4,}/g) || []);
    }

    // Parsea fechas de Google ISO (con T) o Base de Datos (con espacio)
    function parseAnyDate(s) {
        if (!s) return null;
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

    // Explota eventos multi-día en segmentos diarios
    function getExpandedEvents(events) {
        const expanded = [];
        events.forEach(ev => {
            const evStartStr = (ev.start || ev.Inicio || '');
            const evEndStr = (ev.end || ev.Fin || '');
            
            let dStart = parseAnyDate(evStartStr);
            let dEnd = parseAnyDate(evEndStr);
            
            if (!dStart || !dEnd) return;

            // Detección robusta de All-day
            const isTimed = evStartStr.includes('T') || evStartStr.includes(':') || evStartStr.length > 10;
            const isAllDay = !isTimed;

            let current = new Date(dStart.getFullYear(), dStart.getMonth(), dStart.getDate(), 12, 0, 0);
            const endLimit = new Date(dEnd.getFullYear(), dEnd.getMonth(), dEnd.getDate(), 12, 0, 0);
            
            // Lógica de límites Google vs Locales
            const isInclusive = isTimed || (dEnd.getTime() === dStart.getTime());

            while (isInclusive ? (current <= endLimit) : (current < endLimit)) {
                const dayStr = fmtDate(current);
                const isFirstDay = fmtDate(current) === fmtDate(dStart);
                const isLastDay = fmtDate(current) === fmtDate(dEnd);

                let sh = 7, eh = 16;
                if (isFirstDay && isTimed) sh = dStart.getHours() + dStart.getMinutes()/60;
                if (isLastDay && isTimed) eh = dEnd.getHours() + dEnd.getMinutes()/60;
                if (!isFirstDay && !isLastDay) { sh = 7; eh = 16; }
                if (isAllDay) { sh = 7; eh = 16; }

                expanded.push({
                    ...ev,
                    _dayStr: dayStr,
                    _sh: sh,
                    _eh: eh
                });
                current.setDate(current.getDate() + 1);
            }
        });
        return expanded;
    }

    function isOT(ev) {
        return extractOTsFromTitle(ev.title).length > 0 || /RESERVA/i.test(ev.title || '');
    }

    function assignColors(tecnicos) {
        techColorMap = {};
        tecnicos.forEach((t, i) => {
            techColorMap[t.nombre] = TECH_COLORS[i % TECH_COLORS.length];
        });
    }

    function setState(partial) {
        Object.assign(state, partial);
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
        renderTechLabels();
        renderHeader();
        renderRows();
        updateDateLabel();
    }

    function renderTechLabels() {
        const col = document.getElementById('tech-labels-col');
        col.innerHTML = '<div class="tech-label-spacer"></div>';
        state.tecnicos.forEach(t => {
            const color = techColorMap[t.nombre] || '#64748b';
            const cell = document.createElement('div');
            cell.className = 'tech-label-cell';
            cell.innerHTML = `
                <div class="tech-label-name">
                    <span class="tech-color-dot" style="background:${color}"></span>${t.nombre}
                </div>
                <div class="tech-label-init">${t.iniciales || ''}</div>`;
            col.appendChild(cell);
        });
    }

    function renderHeader() {
        const row = document.getElementById('time-header-row');
        row.innerHTML = '';

        if (state.mode === 'resources' && state.view === 'day') {
             const dateStr = fmtDate(state.currentDate);
             const isToday = dateStr === fmtDate(new Date());
             const cell = document.createElement('div');
             cell.className = 'time-header-cell day-view-cell' + (isToday ? ' today' : '');
             cell.style.flexDirection = 'column';
             cell.style.gap = '4px';
             
             const label = document.createElement('span');
             label.textContent = state.currentDate.toLocaleDateString('es-ES', {weekday:'long', day:'numeric'}).toUpperCase();
             if (isToday) label.style.color = 'var(--accent)';
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
            const isToday = fmtDate(d) === todayStr;
            const cell = document.createElement('div');

            if (isRow) {
                cell.className = 'day-cell' + (isWeekend ? ' weekend' : '') + (isToday ? ' today-col' : '');
                cell.dataset.dow = i;
                cell.dataset.date = fmtDate(d);
            } else {
                cell.className = 'time-header-cell week-day-header' +
                    (isWeekend ? ' weekend' : '') + (isToday ? ' today' : '');
                
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

                cell.innerHTML = `
                    <span class="wh-day">${d.toLocaleDateString('es-ES', {weekday:'short'}).toUpperCase()}</span>
                    <span class="wh-date">${d.getDate()}/${d.getMonth()+1}</span>`;
                cell.appendChild(aDiv);
            }
            container.appendChild(cell);
        }
    }

    function renderRows() {
        const container = document.getElementById('scheduler-rows-container');
        container.innerHTML = '';

        // Apply week-grid or day-grid class to scroll area
        const scrollArea = document.getElementById('scheduler-scroll-area');
        const wrapper = document.getElementById('scheduler-wrapper');
        
        if (state.mode === 'resources') wrapper.classList.add('res-mode');
        else wrapper.classList.remove('res-mode');

        if (state.view === 'week') {
            scrollArea.classList.add('week-mode');
            scrollArea.classList.remove('day-mode');
        } else {
            scrollArea.classList.add('day-mode');
            scrollArea.classList.remove('week-mode');
        }

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
        let eventsToday = expanded.filter(ev => {
            if (norm(ev.resourceId || ev['Técnico']) !== norm(tech.nombre)) return false;
            return ev._dayStr === dateStr;
        });
        
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
            if (norm(ev.resourceId || ev['Técnico']) !== norm(tech.nombre)) return false;
            const d = parseAnyDate(ev._dayStr);
            const weEnd = new Date(ws.getFullYear(), ws.getMonth(), ws.getDate() + 7, 12, 0, 0);
            return d >= ws && d < weEnd;
        });
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
                    let sh = ev._sh;
                    let eh = ev._eh;

                    // Excepción: Si cae fuera de horario, forzar visibilidad en los extremos
                    if (sh >= END_H) { sh = 16; eh = 18; }
                    else if (eh <= START_H) { sh = 7; eh = 9; }

                    const clampSh = Math.max(sh, START_H);
                    const clampEh = Math.min(eh, END_H);
                    
                    const leftPct = ((clampSh - START_H) / HOURS) * 100;
                    const widthPct = Math.max(((clampEh - clampSh) / HOURS) * 100, 2); 
                    const topPct = (colIdx / group.length) * 100;
                    const heightPct = (1 / group.length) * 100;

                    const block = document.createElement('div');
                    block.className = 'ev-block week-ev-block' + (state.soloOTs && !isOT(ev) ? ' dim' : '');
                    block.style.cssText = `
                        background:${color}dd;
                        left:${leftPct}%;
                        width:calc(${widthPct}% - 1px);
                        top:calc(${topPct}% + 1px);
                        height:calc(${heightPct}% - 2px);
                    `;
                    block.innerHTML = `<div class="ev-title" style="font-size:9px">${ev.title}</div>`;

                    block.setAttribute('draggable', 'true');
                    block.addEventListener('dragstart', e => {
                        e.dataTransfer.setData('application/json', JSON.stringify({
                            type: 'move',
                            eventId: ev.id,
                            calendarId: ev.calendar_id || ev.calendarId || 'primary'
                        }));
                    });

                    block.addEventListener('click', e => { e.stopPropagation(); App.selectEvent(ev); });
                    cell.appendChild(block);
                });
            });
        });
    }

    function createDayBlock(ev, color, colIdx, totalCols) {
        // Usar valores pre-calculados por getExpandedEvents
        let sh = ev._sh;
        let eh = ev._eh;

        // Excepción: Si cae fuera de horario, forzar visibilidad en los extremos
        if (sh >= END_H) { sh = 16; eh = 18; }
        else if (eh <= START_H) { sh = 7; eh = 9; }
        
        const clampSh = Math.max(sh, START_H);
        const clampEh = Math.min(eh, END_H);
        const leftPct = ((clampSh - START_H) / HOURS) * 100;
        const widthPct = ((clampEh - clampSh) / HOURS) * 100;
        const topPct = totalCols > 1 ? (colIdx / totalCols) * 100 : 0;
        const heightPct = totalCols > 1 ? (1 / totalCols) * 100 : 100;

        const block = document.createElement('div');
        block.className = 'ev-block' + (state.soloOTs && !isOT(ev) ? ' dim' : '');
        block.style.cssText = `
            left:${leftPct}%;
            width:${Math.max(widthPct, 1.5)}%;
            background:${color}dd;
            top:calc(${topPct}% + 4px);
            height:calc(${heightPct}% - 8px);
            bottom:unset;`;
        block.innerHTML = `
            <div class="ev-title">${ev.title}</div>
            <div class="ev-time">${fmtHour(sh)}–${fmtHour(eh)}</div>`;
        
        // Habilitar arrastre para re-agendamiento
        block.setAttribute('draggable', 'true');
        block.addEventListener('dragstart', e => {
            e.dataTransfer.setData('application/json', JSON.stringify({
                type: 'move',
                eventId: ev.id,
                calendarId: ev.calendar_id || ev.calendarId || 'primary'
            }));
            block.classList.add('dragging');
        });
        block.addEventListener('dragend', () => block.classList.remove('dragging'));

        block.addEventListener('click', e => { e.stopPropagation(); App.selectEvent(ev); });
        return block;
    }

    // ─────────────────────────────────────
    // RESOURCES CARDS
    // ─────────────────────────────────────

    function createResourceCard(ev, color, techNombre) {
        const card = document.createElement('div');
        card.className = 'res-card';

        const checkMultiDayConstraint = () => {
             const isTimed = (ev.start || ev.Inicio || '').includes('T');
             const d1 = ev.start || ev.Inicio;
             const d2 = ev.end || ev.Fin;
             if (!isTimed && d1 && d2 && d1 !== d2) {
                 App.toast('Evento multi-día (lectura). Por favor utiliza el botón de "Individualizar" abriendo los detalles antes de modificar sus recursos.', 'warning');
                 return true;
             }
             return false;
        };

        // 1. Evento
        const otsStr = extractOTsFromTitle(ev.title).join(', ');
        const evBox = document.createElement('div');
        evBox.className = 'res-rc-ev';
        evBox.innerHTML = `
            <div class="res-rc-ev-title">${ev.title || 'Evento'}</div>
            ${otsStr ? `<div class="res-rc-ev-ots">OTs: ${otsStr}</div>` : ''}
            <div style="font-size:9px;color:var(--text-muted);margin-top:2px">${fmtHour(ev._sh)} - ${fmtHour(ev._eh)}</div>
        `;
        evBox.addEventListener('click', (e) => {
            e.stopPropagation();
            App.selectEvent(ev); // Abrir panel derecho
        });
        card.appendChild(evBox);

        // 2. Patrones
        const props = ev.extendedProperties?.private || {};
        const isReq = (props.app_requiere_vehiculo === 'true');
        let pats = getEventPats(ev);

        // Validar conflictos de patrones (Día completo)
        const expHoy = getExpandedEvents(state.eventos).filter(e => e._dayStr === ev._dayStr);
        let patConf = false;
        let patConfMsg = '';
        for (const p of pats) {
            if (checkPatternConflict(p, expHoy, ev.id)) {
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
                <i class="fa-solid fa-plus btn-pat-expand" style="cursor:pointer" title="Expandir/Agregar" data-id="${ev.id}"></i>
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
             const cfInfo = App.checkVehicleConflicts(cv, ev._dayStr, ev._sh, ev._eh, ev.id, techNombre);
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
            const eventsDelDia = exp.filter(x => x.resourceId === techNombre && x._dayStr === ev._dayStr);
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
            const calId = ev.calendarId || ev.calendar_id;
            const props = ev.extendedProperties?.private || {};
            // Si hay patrones omitidos en partial, re-enviar los actuales.
            let patsToSave = partial.patrones !== undefined ? partial.patrones : null;
            if (patsToSave === null) {
                const ep = props.app_patrones || ev.app_patrones || '[]';
                patsToSave = typeof ep === 'string' ? JSON.parse(ep) : ep;
            }
            if (!Array.isArray(patsToSave)) patsToSave = [];

            const bBody = {
                 event_id: ev.id,
                 calendar_id_origen: calId,
                 correo_destino: calId,
                 nueva_fecha: ev.start ? ev.start.substring(0,10) : ev._dayStr, // no altera start/end reales, la API los mantiene si no van
                 patrones: patsToSave,
                 vehiculo: partial.vehiculo !== undefined ? partial.vehiculo : props.app_vehiculo,
                 requiere_vehiculo: partial.requiere_vehiculo !== undefined ? partial.requiere_vehiculo : (props.app_requiere_vehiculo === 'true')
            };

            const r = await fetch(`/api/eventos/${ev.id}/mover`, {
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
            App.toast('Error: ' + e.message, 'error');
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
             const props = ev.extendedProperties?.private || {};
             const cv = props.app_vehiculo || ev.app_vehiculo;
             const isReq = (props.app_requiere_vehiculo === 'true');
             
             if (isReq && !cv) vehReq = true;
             else if (cv) {
                 const resId = ev.resourceId || ev['Técnico'];
                 const cfo = App.checkVehicleConflicts(cv, dateStr, ev._sh, ev._eh, ev.id, resId);
                 if (cfo) {
                     vehConf = true;
                     details.veh.push(`${cv}: ${ev.title} (${resId}) tiene conflicto.`);
                 }
             }

             const evPats = getEventPats(ev);
             for (const p of evPats) {
                 const conflictInfo = checkPatternConflict(p, exp, ev.id);
                 if (conflictInfo === true) {
                     patConf = true;
                     details.pat.push(`${p}: Usado en "${ev.title}" con conflicto de grupo.`);
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
        
        const currentEv = dayEvents.find(e => e.id === currentEvId);
        if (!currentEv) return false;
        
        const currentOTs = getEventOTs(currentEv);
        
        // Buscar otros eventos que usen el mismo patrón
        const othersUsingPat = dayEvents.filter(e => {
            if (e.id === currentEvId) return false;
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
        const props = ev.extendedProperties?.private || {};
        let ots = props.app_ots || ev.app_ots || '[]';
        try { ots = typeof ots === 'string' ? JSON.parse(ots) : ots; } catch { ots = []; }
        if (!Array.isArray(ots)) ots = [];
        const fromTitle = extractOTsFromTitle(ev.title);
        return Array.from(new Set([...ots, ...fromTitle]));
    }

    function getEventPats(ev) {
        const props = ev.extendedProperties?.private || {};
        let pats = props.app_patrones || ev.app_patrones || '[]';
        try { pats = typeof pats === 'string' ? JSON.parse(pats) : pats; } catch { pats = []; }
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
            let hour = 7;
            let targetDateStr = fmtDate(state.currentDate);

            // 1. Calcular Fecha (si estamos en vista semanal, buscar la celda)
            if (state.view === 'week') {
                const cell = e.target.closest('.day-cell');
                if (cell && cell.dataset.date) {
                    targetDateStr = cell.dataset.date;
                }
            }

            // 2. Calcular Hora (si estamos en vista día)
            if (state.view === 'day') {
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
                App.openQuickCreate(tech, parseAnyDate(targetDateStr), hour, dragData);
            }
        } catch (err) {
            console.error('Drop error:', err);
        }
    }

    function handleDblClick(e, tech) {
        let hour = 7;
        if (state.view === 'day') {
            const scrollArea = document.getElementById('scheduler-scroll-area');
            const contentLeft = scrollArea.getBoundingClientRect().left;
            const relX = e.clientX - contentLeft + scrollArea.scrollLeft;
            const totalW = scrollArea.scrollWidth;
            const pct = Math.max(0, relX / totalW);
            hour = Math.floor((START_H + pct * HOURS) * 2) / 2;
        }
        App.openQuickCreate(tech, state.currentDate, hour, null);
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
        document.getElementById(v === 'day' ? 'btn-view-day' : 'btn-view-week').classList.add('active');
        render();
    }

    return {
        setState, render, assignColors, navigate, goToday, setView,
        extractOTsFromTitle, toggleResourceMode
    };
})();
