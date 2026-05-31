// ════════════════════════════════════════
// POLL MANAGER — Human Arbitration Panel
// ════════════════════════════════════════

const PollManager = (() => {
    let _reviewQueue = [];
    let _pollStatusInterval = null;

    // ── FIELD LABELS ───────────────────────────────────────
    const FIELD_LABELS = {
        inicio: 'Inicio',
        fin: 'Fin',
        summary: 'Título',
        tecnico_nombre: 'Técnico',
        descripcion: 'Descripción',
        ubicacion: 'Ubicación',
        extended_props: 'Metadata',
    };

    function init() {
        const badge = document.getElementById('poll-badge');
        if (badge) badge.addEventListener('click', openReviewModal);

        document.querySelectorAll('[data-modal="modal-poll-review"]').forEach(btn => {
            btn.addEventListener('click', () => {
                document.getElementById('modal-poll-review')?.classList.add('hidden');
            });
        });

        const configSelect = document.getElementById('cfg-poll-interval');
        if (configSelect) {
            configSelect.addEventListener('change', async (e) => {
                await updatePollInterval(e.target.value);
            });
        }

        startStatusLoop();
    }

    function startStatusLoop() {
        if (_pollStatusInterval) clearInterval(_pollStatusInterval);
        fetchPollStatus();
        _pollStatusInterval = setInterval(fetchPollStatus, 30000);
    }

    async function fetchPollStatus() {
        try {
            const res = await fetch('/api/review/pending');
            if (!res.ok) return;
            _reviewQueue = await res.json();
            updateBadge();
        } catch (e) {
            console.error('[PollManager] Error fetching reviews:', e);
        }
    }

    function updateBadge() {
        const badge = document.getElementById('poll-badge');
        const countSpan = document.getElementById('poll-review-count');
        const textSpan = document.getElementById('poll-status-text');
        if (!badge) return;

        const count = _reviewQueue.length;
        if (count > 0) {
            badge.classList.add('has-reviews');
            if (countSpan) { countSpan.textContent = count; countSpan.classList.remove('hidden'); }
            if (textSpan) textSpan.textContent = `${count} Conflicto${count > 1 ? 's' : ''} Pendiente${count > 1 ? 's' : ''}`;
        } else {
            badge.classList.remove('has-reviews');
            if (countSpan) countSpan.classList.add('hidden');
            if (textSpan) textSpan.textContent = 'Sincronizado';
        }
    }

    function openReviewModal() {
        if (_reviewQueue.length === 0) {
            App.toast('No hay cambios pendientes de revisión', 'info');
            return;
        }
        renderReviewQueue();
        document.getElementById('modal-poll-review')?.classList.remove('hidden');
    }

    // ── DIFF VISUAL ────────────────────────────────────────
    function renderDiffRow(field, d) {
        const label = FIELD_LABELS[field] || field;
        const oldVal = d.old !== undefined ? d.old : '—';
        const newVal = d.new !== undefined ? d.new : '—';
        return `
            <div style="display:grid;grid-template-columns:120px 1fr auto 1fr;gap:6px;align-items:center;
                        padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.05);font-size:11px;">
                <span style="color:var(--text-muted);font-weight:600;text-transform:uppercase;letter-spacing:.04em">${label}</span>
                <span style="background:rgba(239,68,68,.12);color:#fca5a5;padding:2px 6px;border-radius:4px;word-break:break-all">${oldVal}</span>
                <span style="color:var(--text-muted)">→</span>
                <span style="background:rgba(16,185,129,.12);color:#6ee7b7;padding:2px 6px;border-radius:4px;word-break:break-all">${newVal}</span>
            </div>`;
    }

    function renderCard(item) {
        const isDelete = item.conflict_type === 'REMOTE_DELETE';
        const isCreate = item.conflict_type === 'REMOTE_CREATE';
        const reviewId = item.review_id || '';
        const eventSummary = item.event_summary || item.event_id?.substring(0, 12) + '…';
        const tecnico = item.tecnico_nombre || '—';
        const calendar = item.calendar_id || '—';
        const detectedAt = item.detected_at ? item.detected_at.substring(0, 16).replace('T', ' ') : '—';
        const recommended = item.recommended_action || 'ACCEPT_REMOTE';

        // Header de tipo de conflicto
        let headerColor = 'rgba(245,158,11,.10)';
        let headerBorder = '#f59e0b';
        let headerIcon = 'fa-pen-to-square';
        let headerLabel = '✎ Cambio Externo Detectado';
        let recommendedLabel = recommended === 'REVIEW_DELETE' ? 'Recomendación: Revisar borrado' : 'Recomendación: Aceptar cambio externo';

        if (isDelete) {
            headerColor = 'rgba(239,68,68,.15)';
            headerBorder = '#ef4444';
            headerIcon = 'fa-trash';
            headerLabel = '⚠ Evento Eliminado en Google';
        } else if (isCreate) {
            headerColor = 'rgba(16,185,129,.15)';
            headerBorder = '#10b981';
            headerIcon = 'fa-calendar-plus';
            headerLabel = '★ Nuevo Evento en Google';
            recommendedLabel = 'Recomendación: Aceptar e importar evento nuevo';
        }

        // Diff visual
        let diffHtml = '';
        if (isDelete) {
            diffHtml = `
                <div style="background:rgba(239,68,68,.08);border:1px solid rgba(239,68,68,.25);
                            border-radius:6px;padding:10px;margin:8px 0;font-size:11px;">
                    <div style="font-weight:600;color:#f87171;margin-bottom:4px;">El evento fue eliminado directamente en Google Calendar.</div>
                    <div style="color:var(--text-muted);">Estado local: <strong>ACTIVO</strong> — Google: <strong>CANCELADO</strong></div>
                </div>`;
        } else if (isCreate) {
            const diff = item.diff || {};
            const diffFields = Object.entries(diff).filter(([k]) => !k.startsWith('_'));
            diffHtml = `
                <div style="background:rgba(16,185,129,.08);border:1px solid rgba(16,185,129,.25);
                            border-radius:6px;padding:10px;margin:8px 0;font-size:11px;">
                    <div style="font-weight:600;color:#34d399;margin-bottom:4px;">Se detectó la creación de un nuevo evento en Google Calendar.</div>
                    <div style="color:var(--text-muted);margin-bottom:6px;">Se importarán los siguientes datos:</div>
                    ${diffFields.map(([f, d]) => renderDiffRow(f, d)).join('')}
                </div>`;
        } else {
            const diff = item.diff || {};
            const diffFields = Object.entries(diff).filter(([k]) => !k.startsWith('_'));
            if (diffFields.length > 0) {
                diffHtml = `<div style="margin:8px 0;">${diffFields.map(([f, d]) => renderDiffRow(f, d)).join('')}</div>`;
            }
        }

        // Botones según tipo
        let acceptLabel = '<i class="fa-solid fa-check"></i> Aplicar Cambio';
        let rejectLabel = '<i class="fa-solid fa-xmark"></i> Rechazar / Revertir';

        if (isDelete) {
            acceptLabel = '<i class="fa-solid fa-check"></i> Confirmar Borrado';
            rejectLabel = '<i class="fa-solid fa-rotate-left"></i> Restaurar en Google';
        } else if (isCreate) {
            acceptLabel = '<i class="fa-solid fa-plus"></i> Importar Evento';
            rejectLabel = '<i class="fa-solid fa-trash-can"></i> Rechazar / Eliminar';
        }

        return `
        <div id="review-card-${reviewId}" style="border:1px solid ${headerBorder};border-radius:8px;
             margin-bottom:12px;overflow:hidden;background:var(--bg-hover,#1e293b);">
            <!-- Header -->
            <div style="background:${headerColor};border-left:4px solid ${headerBorder};padding:8px 12px;
                        display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <div style="font-weight:700;font-size:12px;color:${headerBorder};">
                        <i class="fa-solid ${headerIcon}"></i> ${headerLabel}
                    </div>
                    <div style="font-size:10px;color:var(--text-muted);margin-top:2px;">${recommendedLabel}</div>
                </div>
                <div style="font-size:10px;color:var(--text-muted);text-align:right;">
                    ${detectedAt}
                </div>
            </div>
            <!-- Body -->
            <div style="padding:10px 12px;">
                <div style="font-weight:600;font-size:13px;margin-bottom:2px;">${eventSummary}</div>
                <div style="font-size:11px;color:var(--text-muted);">
                    <i class="fa-solid fa-user"></i> ${tecnico} &nbsp;·&nbsp;
                    <i class="fa-solid fa-calendar"></i> ${calendar}
                </div>
                ${diffHtml}
            </div>
            <!-- Actions -->
            <div style="padding:8px 12px;border-top:1px solid rgba(255,255,255,0.06);
                        display:flex;gap:8px;justify-content:flex-end;background:rgba(0,0,0,.15);">
                <button class="btn-secondary btn-sm" onclick="PollManager.deferChange('${reviewId}')">
                    <i class="fa-solid fa-clock"></i> Posponer
                </button>
                <button class="btn-secondary btn-sm" style="border-color:var(--danger,#ef4444);color:var(--danger,#ef4444);"
                        onclick="PollManager.rejectChange('${reviewId}')">
                    ${rejectLabel}
                </button>
                <button class="btn-primary btn-sm" onclick="PollManager.acceptChange('${reviewId}')">
                    ${acceptLabel}
                </button>
            </div>
        </div>`;
    }

    function renderReviewQueue() {
        const list = document.getElementById('poll-review-list');
        if (!list) return;

        if (_reviewQueue.length === 0) {
            list.innerHTML = '<p style="text-align:center;color:var(--text-muted);padding:20px;">No hay conflictos pendientes.</p>';
            return;
        }

        list.innerHTML = _reviewQueue.map(item => renderCard(item)).join('');
    }

    // ── ACCIONES ───────────────────────────────────────────
    async function acceptChange(reviewId) {
        try {
            const res = await fetch(`/api/review/${reviewId}/accept`, { method: 'POST' });
            const data = await res.json();
            if (!res.ok) {
                // [INBOUND_FIX] 422 = SQLite mutation failed — mostrar diagnóstico específico
                if (res.status === 422 && data.detail?.error === 'SQLITE_MUTATION_FAILED') {
                    App.toast(
                        '⚠ El cambio NO se aplicó: el evento no fue localizado en la base de datos local. ' +
                        'Revisar logs ARBITRATION_TRACE para diagnóstico.',
                        'error'
                    );
                } else {
                    throw new Error(data.detail || JSON.stringify(data));
                }
                return;
            }
            App.toast('Cambio aplicado ✓', 'success');
            _removeFromQueue(reviewId);
            if (window.App) App.refreshEvents();
        } catch (e) {
            App.toast('Error al aplicar: ' + e.message, 'error');
        }
    }

    async function rejectChange(reviewId) {
        try {
            const res = await fetch(`/api/review/${reviewId}/reject`, { method: 'POST' });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
            App.toast('Cambio rechazado — resync encolado', 'info');
            _removeFromQueue(reviewId);
        } catch (e) {
            App.toast('Error al rechazar: ' + e.message, 'error');
        }
    }

    async function deferChange(reviewId) {
        try {
            const res = await fetch(`/api/review/${reviewId}/defer`, { method: 'POST' });
            if (!res.ok) throw new Error(await res.text());
            App.toast('Review pospuesto', 'info');
            _removeFromQueue(reviewId);
        } catch (e) {
            App.toast('Error al posponer: ' + e.message, 'error');
        }
    }

    function _removeFromQueue(reviewId) {
        _reviewQueue = _reviewQueue.filter(r => r.review_id !== reviewId);
        updateBadge();
        renderReviewQueue();
        if (_reviewQueue.length === 0) {
            document.getElementById('modal-poll-review')?.classList.add('hidden');
        }
    }

    // ── CONFIG ─────────────────────────────────────────────
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
            console.error('[PollManager] Error cargando config:', e);
        }
    }

    async function updatePollInterval(seconds) {
        try {
            const res = await fetch(`/api/poll/config?interval_seconds=${seconds}`, { method: 'POST' });
            if (res.ok) App.toast('Intervalo de polling actualizado', 'success');
            else App.toast('Error al actualizar intervalo', 'error');
        } catch (e) {
            App.toast('Error de conexión', 'error');
        }
    }

    return { init, fetchPollStatus, acceptChange, rejectChange, deferChange, loadConfig };
})();
