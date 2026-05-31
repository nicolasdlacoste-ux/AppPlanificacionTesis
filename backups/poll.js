// ════════════════════════════════════════
// POLL MANAGER
// Gestiona el polling de Google Calendar y la UI de arbitraje
// ════════════════════════════════════════

const PollManager = (() => {
    let _reviewQueue = [];
    let _pollStatusInterval = null;

    function init() {
        // Enlazar eventos de UI
        const badge = document.getElementById('poll-badge');
        if (badge) {
            badge.addEventListener('click', openReviewModal);
        }

        const modalCloseBtns = document.querySelectorAll('[data-modal="modal-poll-review"]');
        modalCloseBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const modal = document.getElementById('modal-poll-review');
                if (modal) modal.classList.add('hidden');
            });
        });

        // Configuración de Polling en Modal de Configuración
        const configSelect = document.getElementById('cfg-poll-interval');
        if (configSelect) {
            configSelect.addEventListener('change', async (e) => {
                await updatePollInterval(e.target.value);
            });
        }

        // Iniciar status refresh loop
        startStatusLoop();
    }

    function startStatusLoop() {
        if (_pollStatusInterval) clearInterval(_pollStatusInterval);
        fetchPollStatus(); // Llamada inmediata
        _pollStatusInterval = setInterval(fetchPollStatus, 30000); // Cada 30 segs consultar status
    }

    async function fetchPollStatus() {
        try {
            const res = await fetch('/api/poll/review_queue');
            if (!res.ok) return;
            const data = await res.json();
            _reviewQueue = data;
            updateBadge();
        } catch (e) {
            console.error("Error consultando poll status:", e);
        }
    }

    function updateBadge() {
        const badge = document.getElementById('poll-badge');
        const countSpan = document.getElementById('poll-review-count');
        const textSpan = document.getElementById('poll-status-text');
        
        if (!badge) return;

        if (_reviewQueue.length > 0) {
            badge.classList.add('has-reviews');
            if (countSpan) {
                countSpan.textContent = _reviewQueue.length;
                countSpan.classList.remove('hidden');
            }
            if (textSpan) textSpan.textContent = "Cambios Pendientes";
        } else {
            badge.classList.remove('has-reviews');
            if (countSpan) countSpan.classList.add('hidden');
            if (textSpan) textSpan.textContent = "Sincronizado";
        }
    }

    function openReviewModal() {
        if (_reviewQueue.length === 0) {
            toast("No hay cambios pendientes de revisión", "info");
            return;
        }
        renderReviewQueue();
        const modal = document.getElementById('modal-poll-review');
        if (modal) modal.classList.remove('hidden');
    }

    function renderReviewQueue() {
        const list = document.getElementById('poll-review-list');
        if (!list) return;
        list.innerHTML = '';

        if (_reviewQueue.length === 0) {
            list.innerHTML = '<p style="text-align:center; color:var(--text-muted);">No hay cambios pendientes.</p>';
            return;
        }

        _reviewQueue.forEach(item => {
            const changes = item.diff || {};
            const action = changes._action || {};
            
            let changeHtml = '';
            if (action.new === 'DELETE') {
                changeHtml = `<div style="color: var(--danger); font-weight: bold;"><i class="fa-solid fa-trash"></i> Evento Eliminado en Google</div>`;
            } else {
                changeHtml = `<div style="color: var(--warning); font-weight: bold;"><i class="fa-solid fa-pen"></i> Evento Modificado</div>`;
                // Mostrar diffs importantes
                if (changes.start || changes.end) {
                    changeHtml += `<div style="font-size: 11px;"><b>Horario:</b> Modificado</div>`;
                }
                if (changes.summary) {
                    changeHtml += `<div style="font-size: 11px;"><b>Título:</b> ${changes.summary.new}</div>`;
                }
            }

            const card = document.createElement('div');
            card.className = 'poll-review-card';
            card.style.cssText = 'border: 1px solid var(--border); padding: 10px; margin-bottom: 10px; border-radius: 4px; display: flex; justify-content: space-between; align-items: center; background: var(--bg-hover);';
            card.innerHTML = `
                <div>
                    <div style="font-size: 11px; color: var(--text-muted);">Calendario: ${item.calendar_id}</div>
                    ${changeHtml}
                </div>
                <div style="display: flex; gap: 8px;">
                    <button class="btn-secondary btn-sm" onclick="PollManager.rejectChange('${item.review_id}')"><i class="fa-solid fa-xmark"></i> Rechazar</button>
                    <button class="btn-primary btn-sm" onclick="PollManager.acceptChange('${item.review_id}')"><i class="fa-solid fa-check"></i> Aplicar</button>
                </div>
            `;
            list.appendChild(card);
        });
    }

    async function acceptChange(reviewId) {
        try {
            const res = await fetch(`/api/poll/review_queue/${reviewId}/apply`, { method: 'POST' });
            if (!res.ok) throw new Error(await res.text());
            toast("Cambio aplicado ✓", "success");
            
            // Recargar eventos si estamos en la app
            if (window.App) {
                // Remove from queue locally
                _reviewQueue = _reviewQueue.filter(r => r.review_id !== reviewId);
                updateBadge();
                renderReviewQueue();
                if (_reviewQueue.length === 0) {
                    const modal = document.getElementById('modal-poll-review');
                    if (modal) modal.classList.add('hidden');
                }
                // Refrescar el scheduler
                App.refreshEvents(); 
            }
        } catch (e) {
            toast("Error al aplicar: " + e.message, "error");
        }
    }

    async function rejectChange(reviewId) {
        try {
            // Un DELETE en review_queue lo elimina
            const res = await fetch(`/api/poll/review_queue/${reviewId}`, { method: 'DELETE' });
            if (!res.ok) throw new Error(await res.text());
            toast("Cambio ignorado", "info");
            
            const item = _reviewQueue.find(r => r.review_id === reviewId);
            _reviewQueue = _reviewQueue.filter(r => r.review_id !== reviewId);
            updateBadge();
            renderReviewQueue();
            if (_reviewQueue.length === 0) {
                const modal = document.getElementById('modal-poll-review');
                if (modal) modal.classList.add('hidden');
            }
            
            if (item && window.App) {
                // Re-sync event to google
                fetch(`/api/eventos/${item.event_id}/resync`, { method: 'POST' });
            }

        } catch (e) {
            toast("Error al rechazar: " + e.message, "error");
        }
    }

    async function loadConfig() {
        const configSelect = document.getElementById('cfg-poll-interval');
        if (!configSelect) return;
        try {
            const res = await fetch('/api/poll/config');
            if (res.ok) {
                const data = await res.json();
                configSelect.value = data.interval_seconds;
            }
        } catch (e) {
            console.error("Error cargando config de poll", e);
        }
    }

    async function updatePollInterval(seconds) {
        try {
            const res = await fetch(`/api/poll/config?interval_seconds=${seconds}`, { method: 'POST' });
            if (res.ok) {
                toast("Intervalo de polling actualizado", "success");
            } else {
                toast("Error al actualizar intervalo", "error");
            }
        } catch (e) {
            toast("Error de conexión", "error");
        }
    }

    return {
        init,
        fetchPollStatus,
        acceptChange,
        rejectChange,
        loadConfig
    };
})();
