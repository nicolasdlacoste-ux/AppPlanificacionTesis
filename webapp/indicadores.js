document.addEventListener('DOMContentLoaded', () => {
    const modal = document.getElementById('modal-indicadores');
    if (!modal) return;
    
    let currentMode = 'semana'; // 'semana' or 'mes'
    let referenceDate = new Date(); // keeps track of the current week/month we are viewing
    
    // UI Elements
    const btnOpen = document.getElementById('btn-open-indicadores');
    const btnPrev = document.getElementById('ind-btn-prev');
    const btnNext = document.getElementById('ind-btn-next');
    const btnSemana = document.getElementById('ind-btn-semana');
    const btnMes = document.getElementById('ind-btn-mes');
    const labelRango = document.getElementById('ind-label-rango');
    const container = document.getElementById('ind-resultados');
    
    btnOpen.addEventListener('click', () => {
        referenceDate = new Date();
        updateUI();
        modal.classList.remove('hidden');
        fetchIndicadores();
    });
    
    btnSemana.addEventListener('click', () => {
        currentMode = 'semana';
        updateUI();
        fetchIndicadores();
    });
    
    btnMes.addEventListener('click', () => {
        currentMode = 'mes';
        updateUI();
        fetchIndicadores();
    });
    
    btnPrev.addEventListener('click', () => {
        if (currentMode === 'semana') {
            referenceDate.setDate(referenceDate.getDate() - 7);
        } else {
            referenceDate.setMonth(referenceDate.getMonth() - 1);
        }
        updateUI();
        fetchIndicadores();
    });
    
    btnNext.addEventListener('click', () => {
        if (currentMode === 'semana') {
            referenceDate.setDate(referenceDate.getDate() + 7);
        } else {
            referenceDate.setMonth(referenceDate.getMonth() + 1);
        }
        updateUI();
        fetchIndicadores();
    });
    
    function getWeekRange(d) {
        const date = new Date(d.getTime());
        const day = date.getDay();
        const diff = date.getDate() - day + (day === 0 ? -6 : 1); // adjust when day is sunday
        const start = new Date(date.setDate(diff));
        const end = new Date(start);
        end.setDate(end.getDate() + 4); // Friday
        return { start, end };
    }
    
    function getMonthRange(d) {
        const start = new Date(d.getFullYear(), d.getMonth(), 1);
        const end = new Date(d.getFullYear(), d.getMonth() + 1, 0); // Last day of month
        return { start, end };
    }
    
    function formatDate(d) {
        const yyyy = d.getFullYear();
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        const dd = String(d.getDate()).padStart(2, '0');
        return `${yyyy}-${mm}-${dd}`;
    }
    
    function formatDisplayDate(d) {
        return d.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit' });
    }
    
    function updateUI() {
        if (currentMode === 'semana') {
            btnSemana.className = 'btn-primary';
            btnMes.className = 'btn-secondary';
            const { start, end } = getWeekRange(referenceDate);
            labelRango.textContent = `${formatDisplayDate(start)} a ${formatDisplayDate(end)}`;
        } else {
            btnSemana.className = 'btn-secondary';
            btnMes.className = 'btn-primary';
            const { start, end } = getMonthRange(referenceDate);
            const monthName = start.toLocaleDateString('es-AR', { month: 'long', year: 'numeric' });
            labelRango.textContent = monthName.charAt(0).toUpperCase() + monthName.slice(1);
        }
    }
    
    async function fetchIndicadores() {
        container.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-muted);"><i class="fa-solid fa-spinner fa-spin fa-2x"></i><br><br>Calculando indicadores...</div>';
        
        let startStr, endStr;
        if (currentMode === 'semana') {
            const { start, end } = getWeekRange(referenceDate);
            startStr = formatDate(start);
            endStr = formatDate(end);
        } else {
            const { start, end } = getMonthRange(referenceDate);
            startStr = formatDate(start);
            endStr = formatDate(end);
        }
        
        try {
            const res = await fetch(`/api/indicadores/ocupacion?start_date=${startStr}&end_date=${endStr}`);
            if (!res.ok) throw new Error('Error en backend');
            const data = await res.json();
            renderIndicadores(data);
        } catch (e) {
            container.innerHTML = `<div style="text-align:center; padding:30px; color:var(--danger);">${e.message}</div>`;
        }
    }
    
    function renderIndicadores(data) {
        if (!data.servicios || data.servicios.length === 0) {
            container.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-muted);">No hay días hábiles en este rango.</div>';
            return;
        }
        
        let html = `
            <table class="data-table" style="width:100%;">
                <thead>
                    <tr>
                        <th style="text-align:left;">Servicio</th>
                        <th style="text-align:center; width:80px;">Técnicos</th>
                        <th style="text-align:center; width: 200px;">Solo OTs</th>
                        <th style="text-align:center; width: 200px;">Todos los Eventos</th>
                    </tr>
                </thead>
                <tbody>
        `;
        
        data.servicios.forEach(s => {
            html += `
                <tr>
                    <td style="text-align:left; font-weight:600;">${s.servicio}</td>
                    <td style="text-align:center;">${s.tecnicos_count}</td>
                    <td>
                        <div style="display:flex; align-items:center; gap:10px;">
                            <div style="flex:1; background:var(--surface-3); height:8px; border-radius:4px; overflow:hidden;">
                                <div style="width:${s.ocupacion_ot}%; background:var(--accent); height:100%;"></div>
                            </div>
                            <span style="font-size:11px; width:40px; text-align:right; font-weight:600;">${s.ocupacion_ot}%</span>
                        </div>
                    </td>
                    <td>
                        <div style="display:flex; align-items:center; gap:10px;">
                            <div style="flex:1; background:var(--surface-3); height:8px; border-radius:4px; overflow:hidden;">
                                <div style="width:${s.ocupacion_all}%; background:var(--success); height:100%;"></div>
                            </div>
                            <span style="font-size:11px; width:40px; text-align:right; font-weight:600;">${s.ocupacion_all}%</span>
                        </div>
                    </td>
                </tr>
            `;
        });
        
        html += `</tbody></table>`;
        html += `<div style="text-align:right; margin-top:10px; font-size:11px; color:var(--text-muted);">Promediado sobre ${data.dias_habiles_count} días hábiles (L-V).</div>`;
        container.innerHTML = html;
    }
});
