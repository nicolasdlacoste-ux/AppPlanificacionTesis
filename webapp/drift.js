// ════════════════════════════════════════
// DRIFT MANAGER — Interfaz de Usuario
// ════════════════════════════════════════

const DriftManager = (() => {
    let _driftData = { items: [], corrupt: [] };

    function init() {
        const badge = document.getElementById('drift-badge');
        if (badge) badge.addEventListener('click', openModal);

        // Bind close buttons
        document.querySelectorAll('[data-modal="modal-drift"]').forEach(btn => {
            btn.addEventListener('click', () => {
                document.getElementById('modal-drift')?.classList.add('hidden');
            });
        });

        // Tabs
        const tabs = document.querySelectorAll('#modal-drift .tab-btn');
        tabs.forEach(t => t.addEventListener('click', (e) => switchTab(e.target)));

        // Polling para actualizar el badge (misma frecuencia que el poll manager o un poco más espaciado)
        setInterval(fetchDriftData, 60000);
        fetchDriftData(); // Carga inicial
    }

    async function fetchDriftData() {
        try {
            const res = await fetch('/api/drift');
            if (!res.ok) return;
            const data = await res.json();
            _driftData.items = data.drift_items || [];
            _driftData.corrupt = data.corrupt_sql || {};
            updateBadge();
        } catch (e) {
            console.error('[DriftManager] Error fetching drift:', e);
        }
    }

    function updateBadge() {
        const badge = document.getElementById('drift-badge');
        const countSpan = document.getElementById('drift-count');
        if (!badge) return;

        let total = _driftData.items.length;
        // Sumar también corruptos
        if (_driftData.corrupt) {
            total += (_driftData.corrupt.eventos_sin_google_id || 0) +
                     (_driftData.corrupt.eventos_duplicados || 0) +
                     (_driftData.corrupt.reviews_pendientes || 0) +
                     (_driftData.corrupt.cancelled_visibles || 0);
        }

        if (total > 0) {
            badge.classList.add('has-reviews'); // Reusar clase de poll para animación
            if (countSpan) { countSpan.textContent = total; countSpan.classList.remove('hidden'); }
        } else {
            badge.classList.remove('has-reviews');
            if (countSpan) countSpan.classList.add('hidden');
        }
    }

    function switchTab(btn) {
        document.querySelectorAll('#modal-drift .tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('#modal-drift .config-tab-content').forEach(c => c.classList.add('hidden'));
        
        btn.classList.add('active');
        const target = btn.dataset.tab;
        document.getElementById(target)?.classList.remove('hidden');
    }

    async function openModal() {
        await fetchDriftData(); // Asegurar datos frescos
        renderTabs();
        document.getElementById('modal-drift')?.classList.remove('hidden');
    }

    function renderTabs() {
        renderCorruptList();
    }



    function renderCorruptList() {
        const c = document.getElementById('drift-list-corrupt');
        if (!c) return;

        const { corrupt } = _driftData;
        if (!corrupt) return;

        let html = '';
        const blocks = [
            { k: 'eventos_sin_google_id', label: 'Eventos sin Google ID (Nunca sincaron)', icon: 'fa-link-slash' },
            { k: 'eventos_duplicados', label: 'Eventos Duplicados en SQL', icon: 'fa-copy' },
            { k: 'cancelled_visibles', label: 'Eventos Cancelados (Pero visibles)', icon: 'fa-ban' }
        ];

        blocks.forEach(b => {
            const count = corrupt[b.k] || 0;
            if (count > 0) {
                html += `
                    <div style="margin-bottom:15px; border-left:3px solid var(--warning); padding-left:10px;">
                        <div style="font-weight:bold; font-size:12px; color:var(--warning);"><i class="fa-solid ${b.icon}"></i> ${b.label} (${count})</div>
                        <div style="font-size:11px; color:var(--text-muted); margin-top:4px;">Para resolver estos problemas, ingresa a la vista técnica o solicita al administrador correr un script correctivo. Próximamente se agregarán botones de auto-resolución aquí.</div>
                    </div>
                `;
            }
        });

        if (html === '') {
            html = `<div style="text-align:center; padding: 20px; color: var(--text-muted);"><i class="fa-solid fa-check-circle" style="color:var(--success); font-size:24px; margin-bottom:10px; display:block;"></i>La base de datos se encuentra saludable y sin corrupción estructural detectada.</div>`;
        }

        c.innerHTML = html;
    }

    return {
        init
    };
})();
