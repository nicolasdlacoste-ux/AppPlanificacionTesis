"""gen_poll_js.py — genera webapp/poll.js con el modulo PollManager completo."""
import os, textwrap

CONTENT = textwrap.dedent("""\
// ============================================================
// poll.js — PollManager
// Gestiona el polling de Google Calendar y la UI de arbitraje
// ============================================================

const PollManager = (() => {
    let _pendingItems = [];

    // ── INIT ─────────────────────────────────────────────────
    function init() {
        const badge = document.getElementById('poll-status-badge');
        if (badge) badge.addEventListener('click', openReviewModal);

        document.addEventListener('click', e => {
            if (e.target.id === 'btn-poll-toggle')       togglePoll();
            if (e.target.id === 'btn-poll-trigger')      triggerNow();
            if (e.target.id === 'btn-save-poll-interval') savePollInterval();
            if (e.target.id === 'btn-open-review-queue') openReviewModal();
        });

        document.getElementById('btn-accept-all')?.addEventListener('click', acceptAll);
        document.getElementById('btn-reject-all')?.addEventListener('click', rejectAll);

        refreshStatus();
        setInterval(refreshStatus, 60000);
    }

    // ── STATUS ───────────────────────────────────────────────
    async function refreshStatus() {
        try {
            const res = await fetch('/api/poll/status');
            if (!res.ok) return;
            const data = await res.json();
            _renderBadge(data.polling_active, data.pending_reviews);
            _renderCalendarTable(data.calendars || []);
            const pb = document.getElementById('sync-pending-badge');
            if (pb) pb.textContent = data.pending_reviews;
            _updateToggleBtn(data.polling_active);
        } catch (e) { console.warn('[PollManager] refreshStatus:', e); }
    }

    function _renderBadge(active, pending) {
        const badge = document.getElementById('poll-status-badge');
        const label = document.getElementById('poll-badge-label');
        const count = document.getElementById('poll-pending-count');
        if (!badge) return;
        badge.classList.remove('hidden', 'poll-active', 'poll-inactive');
        badge.classList.add(active ? 'poll-active' : 'poll-inactive');
        label.textContent = active ? 'Polling activo' : 'Polling inactivo';
        if (pending > 0) { count.textContent = pending; count.classList.remove('hidden'); }
        else { count.classList.add('hidden'); }
    }

    function _renderCalendarTable(calendars) {
        const tbody = document.getElementById('sync-calendars-tbody');
        if (!tbody) return;
        if (!calendars.length) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--text-muted)">Sin datos — inicia el polling</td></tr>';
            return;
        }
        tbody.innerHTML = calendars.map(c => {
            const ts = c.last_poll_time
                ? new Date(c.last_poll_time).toLocaleTimeString('es-AR', {hour:'2-digit', minute:'2-digit'})
                : '—';
            const ok = c.ok
                ? '<span style="color:#4caf50">OK</span>'
                : '<span style="color:#f44336">Error</span>';
            const shortId = c.calendar_id.length > 24 ? c.calendar_id.substring(0,24)+'...' : c.calendar_id;
            return `<tr><td title="${c.calendar_id}">${shortId}</td><td>${ts}</td><td>${ok}</td><td>${c.error_count||0}</td></tr>`;
        }).join('');
    }

    function _updateToggleBtn(active) {
        const btn = document.getElementById('btn-poll-toggle');
        if (!btn) return;
        btn.textContent = active ? 'Detener polling' : 'Activar polling';
        btn.className   = active ? 'btn-danger btn-sm' : 'btn-primary btn-sm';
    }

    // ── CONTROLES ────────────────────────────────────────────
    async function togglePoll() {
        try {
            const st = await (await fetch('/api/poll/status')).json();
            const endpoint = st.polling_active ? '/api/poll/stop' : '/api/poll/start';
            await fetch(endpoint, { method: 'POST' });
            App.toast(st.polling_active ? 'Polling detenido' : 'Polling activado', 'info');
            await refreshStatus();
        } catch (e) { App.toast(e, 'error'); }
    }

    async function triggerNow() {
        const btn = document.getElementById('btn-poll-trigger');
        const orig = btn?.innerHTML;
        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Ejecutando...'; }
        try {
            await fetch('/api/poll/trigger', { method: 'POST' });
            App.toast('Ciclo de polling ejecutado', 'success');
            await refreshStatus();
        } catch (e) { App.toast(e, 'error'); }
        finally { if (btn) { btn.disabled = false; btn.innerHTML = orig; } }
    }

    async function savePollInterval() {
        const input = document.getElementById('cfg-poll-interval');
        if (!input) return;
        const val = parseInt(input.value);
        if (isNaN(val) || val < 60 || val > 3600) {
            App.toast('Intervalo debe ser entre 60 y 3600 segundos', 'warning'); return;
        }
        try {
            const r = await fetch('/api/poll/config?interval_seconds=' + val, { method: 'POST' });
            if (!r.ok) throw new Error(await r.text());
            App.toast('Intervalo guardado: ' + val + 's', 'success');
        } catch (e) { App.toast(e, 'error'); }
    }

    async function loadPollConfig() {
        try {
            const data = await (await fetch('/api/poll/config')).json();
            const input = document.getElementById('cfg-poll-interval');
            if (input) input.value = data.interval_seconds;
        } catch(e) {}
    }

    // ── REVIEW QUEUE ─────────────────────────────────────────
    async function openReviewModal() {
        try {
            _pendingItems = await (await fetch('/api/poll/review_queue?limit=50')).json();
            _renderReviewModal(_pendingItems);
            document.getElementById('modal-review-queue')?.classList.remove('hidden');
        } catch (e) { App.toast(e, 'error'); }
    }

    function _renderReviewModal(items) {
        const body = document.getElementById('review-queue-body');
        if (!body) return;
        if (!items.length) {
            body.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-muted)"><i class="fa-solid fa-inbox fa-2x"></i><p style="margin-top:12px">No hay cambios pendientes de revision</p></div>';
            return;
        }
        body.innerHTML = items.map(item => {
            let diff = {};
            try { diff = JSON.parse(item.diff); } catch(e) {}
            const ts = new Date(item.detected_at).toLocaleString('es-AR');
            const isDelete = diff._action?.new === 'DELETE';
            const typeIcon = isDelete
                ? '<span style="color:#f44336;font-weight:600"><i class="fa-solid fa-trash"></i> EVENTO CANCELADO EN GOOGLE</span>'
                : '<span style="color:#ff9800;font-weight:600"><i class="fa-solid fa-triangle-exclamation"></i> CAMBIO DETECTADO</span>';

            const fieldRows = Object.entries(diff)
                .filter(([k]) => k !== '_action')
                .map(([k,v]) =>
                    `<tr><td style="font-weight:600;padding:4px 8px;color:var(--text-muted)">${k}</td>` +
                    `<td style="padding:4px 8px;color:#f44336;text-decoration:line-through">${v.old||'—'}</td>` +
                    `<td style="padding:4px 8px;color:#4caf50">${v.new||'—'}</td></tr>`
                ).join('');

            const fieldsHtml = isDelete
                ? '<p style="color:var(--text-muted);margin:8px 0">El evento fue eliminado en Google Calendar.</p>'
                : fieldRows
                    ? `<table style="width:100%;border-collapse:collapse;margin:8px 0;font-size:12px">
                        <thead><tr>
                          <th style="text-align:left;padding:4px 8px;color:var(--text-muted)">Campo</th>
                          <th style="text-align:left;padding:4px 8px;color:var(--text-muted)">Version local</th>
                          <th style="text-align:left;padding:4px 8px;color:var(--text-muted)">Google</th>
                        </tr></thead><tbody>${fieldRows}</tbody></table>`
                    : '<p style="color:var(--text-muted)">Sin campos modificados</p>';

            const shortCal = item.calendar_id.length > 35
                ? item.calendar_id.substring(0,35)+'...' : item.calendar_id;

            return `<div class="review-item" data-id="${item.review_id}"
                style="border:1px solid var(--border);border-radius:8px;padding:14px;margin-bottom:12px;background:var(--bg-card)">
                ${typeIcon}
                <div style="font-size:11px;color:var(--text-muted);margin:4px 0">${shortCal} &bull; ${ts}</div>
                ${fieldsHtml}
                <div style="display:flex;gap:8px;margin-top:10px;justify-content:flex-end">
                    <button class="btn-secondary btn-sm" onclick="PollManager.rejectChange('${item.review_id}')">
                        <i class="fa-solid fa-xmark"></i> Rechazar
                    </button>
                    <button class="btn-primary btn-sm" onclick="PollManager.acceptChange('${item.review_id}')">
                        <i class="fa-solid fa-check"></i> Aceptar de Google
                    </button>
                </div></div>`;
        }).join('');
    }

    async function acceptChange(reviewId) {
        const el = document.querySelector(`[data-id="${reviewId}"]`);
        if (el) el.style.opacity = '0.5';
        try {
            const r = await fetch(`/api/poll/review_queue/${reviewId}/apply`, { method: 'POST' });
            if (!r.ok) {
                let msg = await r.text();
                try { msg = JSON.parse(msg).detail || msg; } catch(_) {}
                throw new Error(msg);
            }
            App.toast('Cambio aplicado correctamente', 'success');
            await App.refreshEvents();
            await openReviewModal();
        } catch (e) {
            if (el) el.style.opacity = '1';
            App.toast(e, 'error');
        }
    }

    async function rejectChange(reviewId) {
        try {
            await fetch(`/api/poll/review_queue/${reviewId}/resolve?action=IGNORED`, { method: 'PATCH' });
            App.toast('Cambio rechazado', 'info');
            await openReviewModal();
        } catch (e) { App.toast(e, 'error'); }
    }

    async function acceptAll() {
        if (!_pendingItems.length) return;
        if (!confirm('Aceptar TODOS los cambios de Google? Esta accion no se puede deshacer.')) return;
        for (const item of [..._pendingItems]) await acceptChange(item.review_id);
    }

    async function rejectAll() {
        if (!_pendingItems.length) return;
        if (!confirm('Rechazar TODOS los cambios pendientes?')) return;
        for (const item of [..._pendingItems]) await rejectChange(item.review_id);
    }

    function onSyncTabOpen() {
        refreshStatus();
        loadPollConfig();
    }

    return { init, refreshStatus, openReviewModal, acceptChange, rejectChange,
             acceptAll, rejectAll, onSyncTabOpen };
})();
""")

out = os.path.join("webapp", "poll.js")
with open(out, "w", encoding="utf-8") as f:
    f.write(CONTENT)
print(f"OK: {out} ({len(CONTENT)} chars)")
