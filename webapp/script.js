document.addEventListener('DOMContentLoaded', async function() {
    const otListEl = document.getElementById('ot-list');
    const calendarEl = document.getElementById('calendar');
    const detailEl = document.getElementById('ot-detail');
    const emptyDetailEl = document.getElementById('empty-detail');
    
    // Configuración
    const CONFIG = {
        START_HOUR: 7,
        END_HOUR: 18,
        COL_WIDTH: 120, // Aumentado para mejor legibilidad
        ROW_HEIGHT: 80
    };

    let state = {
        tecnicos: [],
        eventos: [],
        ots: [],
        currentDate: new Date(),
        view: 'day' // 'day' o 'week'
    };

    // Helper: Normalizar para comparación
    function normalize(str) {
        if (!str) return "";
        return str.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
    }

    // --- INICIALIZACIÓN ---

    async function init() {
        renderSkeleton();
        await fetchData();
        renderScheduler();
        renderBacklog();
    }

    function renderSkeleton() {
        calendarEl.innerHTML = `
            <div class="scheduler-container">
                <div class="scheduler-grid" id="scheduler-grid">
                    <div class="scheduler-tech-col" id="tech-column"></div>
                    <div class="scheduler-time-header" id="time-header"></div>
                    <div class="scheduler-content" id="scheduler-body"></div>
                </div>
            </div>
        `;
    }

    async function fetchData() {
        try {
            const [techRes, eventRes, otRes] = await Promise.all([
                fetch('/api/tecnicos'),
                fetch('/api/eventos'),
                fetch('/api/ots/pendientes')
            ]);
            state.tecnicos = await techRes.json();
            state.eventos = await eventRes.json();
            state.ots = await otRes.json();
        } catch (e) {
            console.error("Error fetching data:", e);
        }
    }

    // --- RENDERIZADO DEL SCHEDULER ---

    function renderScheduler() {
        const timeHeader = document.getElementById('time-header');
        const techColumn = document.getElementById('tech-column');
        const schedulerBody = document.getElementById('scheduler-body');
        const dateLabel = document.getElementById('current-date-label');

        // Actualizar Label de Fecha
        const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
        dateLabel.innerText = state.currentDate.toLocaleDateString('es-ES', options).toUpperCase();

        // 1. Renderizar Cabecera de Tiempo / Días
        timeHeader.innerHTML = '';
        
        if (state.view === 'day') {
            const numCols = CONFIG.END_HOUR - CONFIG.START_HOUR + 1;
            const totalWidth = numCols * CONFIG.COL_WIDTH;
            timeHeader.style.gridTemplateColumns = `repeat(${numCols}, minmax(${CONFIG.COL_WIDTH}px, 1fr))`;
            schedulerBody.style.gridTemplateColumns = `repeat(${numCols}, minmax(${CONFIG.COL_WIDTH}px, 1fr))`;
            timeHeader.style.width = `${totalWidth}px`;
            schedulerBody.style.width = `${totalWidth}px`;

            for (let h = CONFIG.START_HOUR; h <= CONFIG.END_HOUR; h++) {
                const div = document.createElement('div');
                div.className = 'time-slot-header';
                div.innerText = `${h.toString().padStart(2, '0')}:00`;
                timeHeader.appendChild(div);
            }
        } else {
            // Vista Semanal
            const numCols = 7;
            const totalWidth = Math.max(calendarEl.offsetWidth - 180, numCols * 150);
            timeHeader.style.gridTemplateColumns = `repeat(${numCols}, 1fr)`;
            schedulerBody.style.gridTemplateColumns = `repeat(${numCols}, 1fr)`;
            timeHeader.style.width = `${totalWidth}px`;
            schedulerBody.style.width = `${totalWidth}px`;

            const startOfWeek = new Date(state.currentDate);
            startOfWeek.setDate(state.currentDate.getDate() - state.currentDate.getDay() + 1); // Lunes

            for (let i = 0; i < 7; i++) {
                const day = new Date(startOfWeek);
                day.setDate(startOfWeek.getDate() + i);
                const div = document.createElement('div');
                div.className = 'time-slot-header';
                div.innerText = day.toLocaleDateString('es-ES', { weekday: 'short', day: 'numeric' }).toUpperCase();
                timeHeader.appendChild(div);
            }
        }

        // 2. Renderizar Filas de Técnicos y Celdas de Datos
        techColumn.innerHTML = '';
        schedulerBody.innerHTML = '';
        
        state.tecnicos.forEach(tech => {
            // Columna Izquierda (Nombre)
            const techCell = document.createElement('div');
            techCell.className = 'tech-cell';
            techCell.innerHTML = `
                <div class="tech-name text-blue-400">${tech.nombre}</div>
                <div class="tech-meta">${tech.iniciales} | ${tech.correo}</div>
            `;
            techColumn.appendChild(techCell);

            // Fila de datos
            const row = document.createElement('div');
            row.className = 'scheduler-row';
            row.dataset.tech = tech.nombre;
            
            // Evento para crear NUEVO al hacer clic en espacio libre
            row.addEventListener('click', (e) => {
                if (e.target === row) handleGridClick(e, tech.nombre);
            });

            // Soporte Drag & Drop
            row.addEventListener('dragover', (e) => e.preventDefault());
            row.addEventListener('drop', (e) => handleDropOnRow(e, tech.nombre));

            schedulerBody.appendChild(row);

            // 3. Renderizar Eventos de este técnico
            renderEventsForRow(row, tech.nombre);
        });
    }

    function renderEventsForRow(rowEl, techName) {
        const techNorm = normalize(techName);
        
        if (state.view === 'day') {
            const hoyStr = state.currentDate.toISOString().split('T')[0];
            const evs = state.eventos.filter(ev => 
                normalize(ev.resourceId) === techNorm && 
                ev.start.startsWith(hoyStr)
            );
            evs.forEach(ev => {
                const block = createEventBlockDay(ev);
                if (block) rowEl.appendChild(block);
            });
        } else {
            // Eventos de la semana
            const startOfWeek = new Date(state.currentDate);
            startOfWeek.setDate(state.currentDate.getDate() - state.currentDate.getDay() + 1);
            const endOfWeek = new Date(startOfWeek);
            endOfWeek.setDate(startOfWeek.getDate() + 7);

            const evs = state.eventos.filter(ev => {
                const evStart = new Date(ev.start);
                return normalize(ev.resourceId) === techNorm && evStart >= startOfWeek && evStart < endOfWeek;
            });

            evs.forEach(ev => {
                const block = createEventBlockWeek(ev, startOfWeek);
                if (block) rowEl.appendChild(block);
            });
        }
    }

    function createEventBlockDay(ev) {
        // ... (Lógica anterior de día)
        const start = new Date(ev.start);
        const end = new Date(ev.end);
        const startH = start.getHours() + (start.getMinutes() / 60);
        const endH = end.getHours() + (end.getMinutes() / 60);
        if (startH > CONFIG.END_HOUR || endH < CONFIG.START_HOUR) return null;
        const leftPct = ((Math.max(startH, CONFIG.START_HOUR) - CONFIG.START_HOUR) / (CONFIG.END_HOUR - CONFIG.START_HOUR + 1)) * 100;
        const widthPct = ((Math.min(endH, CONFIG.END_HOUR + 1) - Math.max(startH, CONFIG.START_HOUR)) / (CONFIG.END_HOUR - CONFIG.START_HOUR + 1)) * 100;

        const block = document.createElement('div');
        block.className = `event-block color-ot`;
        if (ev.title.toUpperCase().includes("RESERVA")) block.className = 'event-block color-reserva';
        if (ev.title.toUpperCase().includes("VIAJE")) block.className = 'event-block color-viaje';

        block.style.left = `${leftPct}%`;
        block.style.width = `${widthPct}%`;
        block.innerHTML = `
            <div class="event-title">${ev.title}</div>
            <div class="event-time">${start.getHours()}:${start.getMinutes().toString().padStart(2,'0')} - ${end.getHours()}:${end.getMinutes().toString().padStart(2,'0')}</div>
        `;
        block.onclick = (e) => { e.stopPropagation(); showDetail(ev); };
        return block;
    }

    function createEventBlockWeek(ev, startOfWeek) {
        const start = new Date(ev.start);
        const dayIdx = (start.getDay() + 6) % 7; // Ajustar a 0=Lunes
        
        const leftPct = (dayIdx / 7) * 100;
        const widthPct = (1 / 7) * 100 - 0.5; // Un poco menos para dejar gap

        const block = document.createElement('div');
        block.className = `event-block color-ot`;
        if (ev.title.toUpperCase().includes("RESERVA")) block.className = 'event-block color-reserva';
        
        block.style.left = `${leftPct}%`;
        block.style.width = `${widthPct}%`;
        block.style.top = '5px';
        block.style.bottom = '5px';

        block.innerHTML = `<div class="event-title text-[10px]">${ev.title}</div>`;
        block.onclick = (e) => { e.stopPropagation(); showDetail(ev); };
        return block;
    }

    // --- LOGICA DE INTERACCIÓN ---

    function handleGridClick(e, techName) {
        const rect = e.target.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const pct = (x / rect.width);
        const hour = CONFIG.START_HOUR + (pct * (CONFIG.END_HOUR - CONFIG.START_HOUR + 1));
        
        console.log(`Click en ${techName} a las ${Math.floor(hour)}:${Math.floor((hour%1)*60)}`);
        
        // Simular creación
        const mockEvent = {
            title: "NUEVA ASIGNACIÓN",
            resourceId: techName,
            start: `${state.currentDate.toISOString().split('T')[0]}T${Math.floor(hour).toString().padStart(2,'0')}:00:00`,
            end: `${state.currentDate.toISOString().split('T')[0]}T${(Math.floor(hour)+2).toString().padStart(2,'0')}:00:00`,
            extendedProps: { description: "Creado manualmente desde el grid." }
        };
        showDetail(mockEvent);
    }

    function handleDropOnRow(e, techName) {
        e.preventDefault();
        const otData = JSON.parse(e.dataTransfer.getData('application/json'));
        
        const rect = e.currentTarget.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const pct = (x / rect.width);
        const hour = CONFIG.START_HOUR + (pct * (CONFIG.END_HOUR - CONFIG.START_HOUR + 1));

        alert(`Asignando OT ${otData.nro} a ${techName} a partir de las ${Math.floor(hour)}:00 hs`);
        
        // Aquí se llamaría a la API de creación
    }

    function renderBacklog() {
        otListEl.innerHTML = '';
        state.ots.forEach(ot => {
            const card = document.createElement('div');
            card.className = "p-4 bg-[#334155] rounded-xl border border-transparent hover:border-blue-500 cursor-grab active:cursor-grabbing transition-all";
            card.draggable = true;
            card.innerHTML = `
                <div class="flex justify-between items-start mb-2">
                    <span class="text-xs font-bold bg-blue-500/20 text-blue-400 px-2 py-1 rounded">OT ${ot.nro}</span>
                    <span class="text-[10px] text-slate-400">${ot.fecha || ''}</span>
                </div>
                <h3 class="font-bold text-sm mb-1">${ot.cliente}</h3>
                <p class="text-xs text-slate-400 line-clamp-2">${ot.trabajo}</p>
            `;

            card.addEventListener('dragstart', (e) => {
                e.dataTransfer.setData('application/json', JSON.stringify(ot));
            });

            otListEl.appendChild(card);
        });
    }

    function showDetail(ev) {
        emptyDetailEl.classList.add('hidden');
        detailEl.classList.remove('hidden');
        
        detailEl.querySelector('h2').innerText = ev.title;
        detailEl.querySelector('textarea').value = ev.extendedProps?.description || ev.description || '';
        
        const dir = ev.extendedProps?.direccion || '';
        const dirContainer = detailEl.querySelector('.bg-blue-500\\/10');
        if (dir) {
            dirContainer.innerHTML = `<i class="fa-solid fa-location-dot mr-2"></i> ${dir}`;
            dirContainer.classList.remove('hidden');
        } else {
            dirContainer.classList.add('hidden');
        }
    }

    // 4. Navegación
    document.getElementById('btn-prev').onclick = () => {
        state.currentDate.setDate(state.currentDate.getDate() - 1);
        renderScheduler();
    };

    document.getElementById('btn-next').onclick = () => {
        state.currentDate.setDate(state.currentDate.getDate() + 1);
        renderScheduler();
    };

    document.getElementById('btn-today').onclick = () => {
        state.currentDate = new Date();
        renderScheduler();
    };

    document.getElementById('btn-view-week').onclick = (e) => {
        state.view = 'day';
        document.getElementById('btn-view-week').classList.add('bg-blue-600');
        document.getElementById('btn-view-month').classList.remove('bg-blue-600');
        renderScheduler();
    };

    document.getElementById('btn-view-month').onclick = (e) => {
        state.view = 'week';
        document.getElementById('btn-view-month').classList.add('bg-blue-600');
        document.getElementById('btn-view-week').classList.remove('bg-blue-600');
        renderScheduler();
    };

    // Sincronización
    document.getElementById('btn-sync').addEventListener('click', async () => {
        const btn = document.getElementById('btn-sync');
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Sincronizando...';
        btn.disabled = true;
        try {
            const res = await fetch('/api/sync');
            const data = await res.json();
            alert("Sincronización Terminada");
            await fetchData();
            renderScheduler();
            renderBacklog();
        } catch (e) {
            alert("Error de sincronización");
        } finally {
            btn.innerHTML = '<i class="fa-solid fa-rotate"></i> Sincronizar';
            btn.disabled = false;
        }
    });

    init();
});
