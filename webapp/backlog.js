// ════════════════════════════════════════
// BACKLOG — Left Panel
// Akrimet Planner v2.0
// ════════════════════════════════════════

const Backlog = (() => {
    let _eventos = [];
    let _allStatuses = new Set();

    function render(ots, eventos) {
        allOTs = ots;
        _eventos = eventos || [];
        
        // Recolectar estados únicos para el filtro
        const prevStatus = document.getElementById('ot-status-filter').value;
        _allStatuses.clear();
        allOTs.forEach(o => { if (o.estado) _allStatuses.add(o.estado); });
        
        _updateStatusFilter(prevStatus);
        _applyFilter();
    }

    function _updateStatusFilter(prevValue) {
        const select = document.getElementById('ot-status-filter');
        // Preservar las opciones fijas
        const fixedOptions = `
            <option value="PENDIENTES" ${prevValue==='PENDIENTES'?'selected':''}>Pendientes (Nuevas/Reprog.)</option>
            <option value="TODAS" ${prevValue==='TODAS'?'selected':''}>Ver Todas</option>
        `;
        
        const dynamicOptions = Array.from(_allStatuses)
            .sort()
            .map(s => `<option value="${s}" ${prevValue===s?'selected':''}>${s}</option>`)
            .join('');
            
        select.innerHTML = fixedOptions + '<hr>' + dynamicOptions;
    }

    function _applyFilter() {
        const query = (document.getElementById('ot-search').value || '').toLowerCase();
        const statusFilter = document.getElementById('ot-status-filter').value;

        let filtered = allOTs;

        // 1. Filtro por estado
        if (statusFilter === 'PENDIENTES') {
            filtered = filtered.filter(o => o.estado === 'Nueva' || o.estado === 'Reprogramar');
        } else if (statusFilter !== 'TODAS') {
            filtered = filtered.filter(o => o.estado === statusFilter);
        }

        // 2. Filtro por búsqueda de texto
        if (query) {
            filtered = filtered.filter(o =>
                o.nro.toLowerCase().includes(query) ||
                (o.cliente || '').toLowerCase().includes(query) ||
                (o.trabajo || '').toLowerCase().includes(query)
            );
        }

        const list = document.getElementById('ot-list');
        list.innerHTML = '';
        document.getElementById('ot-count').textContent = filtered.length;

        if (!filtered.length) {
            list.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-muted);font-size:12px">Sin OTs pendientes</div>';
            return;
        }

        filtered.forEach(ot => {
            // Detección de agenda (cross-check)
            const eventosAsociados = _eventos.filter(ev => {
                const searchStr = (ev.title + ' ' + (ev.description || '')).toLowerCase();
                const rawOts = ev.extendedProperties?.private?.app_ots;
                let otsInProps = [];
                if (rawOts) {
                    try {
                        const parsed = JSON.parse(rawOts);
                        otsInProps = Array.isArray(parsed) ? parsed : [String(parsed)];
                    } catch {
                        otsInProps = [String(rawOts)];
                    }
                }
                return searchStr.includes(ot.nro.toLowerCase()) || otsInProps.includes(ot.nro);
            });
            const esAgendada = eventosAsociados.length > 0;

            const card = document.createElement('div');
            card.className = 'ot-card';
            card.draggable = true;
            card.dataset.nro = ot.nro;

            const estadoColor = ot.estado === 'Reprogramar' ? '#f59e0b' : (ot.estado === 'Nueva' ? 'var(--accent)' : 'var(--text-muted)');
            
            card.innerHTML = `
                <div class="ot-card-header">
                    <span class="ot-badge" style="color:${estadoColor};background:${estadoColor}22">OT ${ot.nro}</span>
                    <div style="display:flex; gap:8px; align-items:center;">
                        ${esAgendada ? `<i class="fa-solid fa-calendar-check ot-agenda-icon" title="Ver agenda"></i>` : ''}
                        <span class="ot-date">${formatDate(ot.fecha)}</span>
                    </div>
                </div>
                <div class="ot-cliente">${ot.cliente || '—'}</div>
                <div class="ot-trabajo">${ot.trabajo || '—'}</div>`;

            // Click → OT Scheduler en panel derecho
            card.addEventListener('click', e => {
                if (e.target.closest('.ot-agenda-icon')) {
                    _showOTAgenda(ot, eventosAsociados);
                    return;
                }
                document.querySelectorAll('.ot-card').forEach(c => c.classList.remove('selected'));
                card.classList.add('selected');
                RightPanel.showOTScheduler(ot);
            });

            // Drag
            card.addEventListener('dragstart', e => {
                e.dataTransfer.setData('application/json', JSON.stringify(ot));
                e.dataTransfer.effectAllowed = 'copy';
                // Small delay so the ghost image shows the full card
                setTimeout(() => card.style.opacity = '0.5', 0);
            });
            card.addEventListener('dragend', () => {
                card.style.opacity = '1';
            });

            list.appendChild(card);
        });
    }

    function formatDate(str) {
        if (!str) return '';
        try {
            // Dates may come as YYYY-MM-DD or DD/MM/YYYY
            let d;
            if (str.includes('-')) {
                d = new Date(str + 'T12:00:00');
            } else {
                const [day, month, year] = str.split('/');
                d = new Date(`${year}-${month}-${day}T12:00:00`);
            }
            return isNaN(d) ? str : d.toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit' });
        } catch { return str; }
    }

    function _showOTAgenda(ot, eventos) {
        document.getElementById('modal-ot-agenda-title').textContent = `Agenda de OT ${ot.nro} — ${ot.cliente}`;
        const tbody = document.getElementById('ot-agenda-tbody');
        tbody.innerHTML = '';
        
        eventos.sort((a,b) => a.start.localeCompare(b.start)).forEach(ev => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${ev.start.substring(0,10)}</td>
                <td><strong>${ev.resourceId || '—'}</strong></td>
                <td>${ev.title}</td>
            `;
            tbody.appendChild(tr);
        });
        
        document.getElementById('modal-ot-agenda').classList.remove('hidden');
    }

    function init() {
        document.getElementById('ot-search').addEventListener('input', _applyFilter);
        document.getElementById('ot-status-filter').addEventListener('change', _applyFilter);
    }

    return { render, init };
})();
