# Fase E — Functional Observatory Spec (diseño)

> **No implementar aún.** Especificación para un observatorio funcional interno basado en capacidades ya parciales (`sync_observatory.py`, admin endpoints, traces).

---

## Objetivo

Unificar en una sola superficie (UI admin o panel dedicado) la **visibilidad operacional** del sistema distribuido Planner ↔ SQLite ↔ Google, sin depender de logs dispersos en consola.

---

## Principios de diseño

1. **Read-only por defecto** — no muta estado; acciones correctivas en endpoints existentes (`accept`, `trigger poll`, `sync retry`).
2. **Fuente de verdad declarada** — cada vista etiqueta si muestra SQLite, Google o estado derivado.
3. **Correlación por identidad** — navegación por `local id`, `google_event_id`, `grupo_id`, `reassignment_id`, `review_id`, `queue_id`.
4. **Legacy vs canonical** — badge en eventos con keys `evento` vs `summary`, operaciones `INSERT` vs `CREATE`.
5. **Tiempo real opcional** — poll cada 30s en métricas agregadas; detalle bajo demanda.

---

## Arquitectura propuesta

```
┌─────────────────────────────────────────────────────────────┐
│              Functional Observatory UI (admin.html v2)       │
├─────────────┬─────────────┬─────────────┬──────────────────┤
│  Dashboard  │  Explorer   │  Drift Lab  │  Timeline        │
│  (métricas) │  (entidad)  │  (reportes) │  (correlación)   │
└──────┬──────┴──────┬──────┴──────┬──────┴────────┬─────────┘
       │             │             │                │
       ▼             ▼             ▼                ▼
 SyncObservatoryService   data_manager   poll_log / sync_log / trace
       │             │             │                │
       └─────────────┴─────────────┴────────────────┘
                         planificacion.db
```

### Backend (extender existente)

| Servicio actual | Extensión propuesta |
|-----------------|-------------------|
| `SyncObservatoryService.get_dashboard_snapshot` | Añadir `reassign_pending`, `insert_queue_items`, `complex_events_count` |
| `get_full_drift_report` | Exponer en UI con filtros por severidad |
| `get_event_timeline` | Unificar `log_trace` + poll + sync (hoy parcial) |
| Nuevo `get_group_health(grupo_id)` | Miembros, sync_status por miembro, título hash |
| Nuevo `get_convergence_status(event_id)` | Semáforo STATE_CONVERGED (ver abajo) |

---

## Vistas requeridas

### 1. Dashboard global

**Debe mostrar:**

| Métrica | Fuente | Umbral alerta |
|---------|--------|---------------|
| sync_queue PENDING/FAILED | `sync_queue` | FAILED > 0 |
| eventos PENDING / REASSIGN_PENDING | `eventos.sync_status` | REASSIGN_PENDING > 5 min |
| reviews PENDING | `poll_review_queue` | > 0 |
| auto_applied_reviews | `poll_log` | INFO (routing rate) | | `poll_review_queue` | > 0 |
| reopened_reviews | drift SQL | > 0 crítico |
| polling_lag calendars | `poll_calendar_state` | > 12 min |
| lookup_misses_24h | trace tag LOOKUP_MISS | > 0 |
| events_without_google_id | drift | > 0 |
| duplicate_events | drift | > 0 |

**API existente:** `GET /api/admin/sync_health`, `GET /api/admin/drift_report`

---

### 2. Explorer — evento

**Debe mostrar por `event_id` (resuelto):**

- Fila SQLite canonical (`EventAdapter.normalize_event`)
- `google_event_id`, `calendar_id`, `tecnico_nombre`, `version`, `sync_status`, `pending_sync`
- `extended_props.private` con ownership por campo (colores: PLANNER / SHARED / GOOGLE)
- Grupo asociado (`grupos` + otros miembros)
- Ítems `sync_queue` activos para ese id
- Reviews PENDING/ACCEPTED vinculados
- Flags: `reassignment_in_progress`, `is_complex`, `CANCELLED_IN_GOOGLE`

**API:** `GET /api/admin/event_timeline/{id}` + nuevo `GET /api/admin/event_snapshot/{id}`

---

### 3. Explorer — grupo

- `grupo_id`, `fecha`, `event_ids`, `tecnico_nombres`
- Tabla miembros: summary, sync_status, calendar, último poll
- Invariantes G1–G4: semáforo (min members, title match, fecha alineada)
- Acciones rápidas (links): abrir cada evento en Explorer

---

### 4. Drift Lab

Reutilizar `get_full_drift_report()` con:

| Indicador | UI |
|-----------|-----|
| events_without_google_id | Lista + botón “ver cola INSERT/CREATE” |
| duplicate_events | Lista + merge sugerido (manual) |
| orphan_events | grupo_id huérfano |
| pending_reviews | Link a arbitration |
| reopened_reviews | **Crítico** — destacar |
| cancelled_visible | Filtro planner |
| sync_failures | Detalle error_msg |
| polling_lag | Por calendario |

**API:** `GET /api/system/drift_report`, `GET /api/admin/drift_report`

---

### 5. Arbitration panel (extensión poll.js)

Ya existe en `webapp/poll.js`. Observatory debe añadir:

- Historial de reviews resueltos (últimos 50)
- Diff con ownership badges por campo
- Indicador “reopened” si `resolved_at` presente
- Link a Timeline del evento

---

### 6. Sync & polling status

| Campo | Fuente |
|-------|--------|
| polling_active | `poll_manager._running` |
| last cycle per calendar | `poll_calendar_state` |
| last 20 poll_log entries | `GET /api/poll/log` |
| last 20 sync_log entries | `GET /api/sync/status` |

---

### 7. Convergence status (nuevo concepto UI)

Algoritmo **read-only** `compute_convergence(event)`:

```
CONVERGED si:
  - sync_status in (SUCCESS, REASSIGN_COMPLETED)
  - pending_sync == 0
  - not reassignment_in_progress
  - google_event_id not like 'local_%'
  - no PENDING review for this event_id
  - not in sync_queue PENDING/PROCESSING

PARTIAL si:
  - pending_sync == 1 OR queue PENDING OR REASSIGN_PENDING

DIVERGED si:
  - FAILED / REASSIGN_*_FAILED
  - duplicate_events includes this gid
  - critical review PENDING

UNKNOWN si:
  - lookup miss o sin fila
```

Mostrar en lista de eventos y en detalle.

---

### 8. Last mutations

Vista agregada de `log_trace` / `OUTBOUND_MUTATION` / `ARBITRATION_APPLIED`:

| Columna | Descripción |
|---------|-------------|
| timestamp | |
| event_id | |
| tag | OUTBOUND_MUTATION, REVIEW_MUTATION, etc. |
| origin | ui_move, split, review_accept, ... |
| payload summary | JSON compacto |

**API nueva sugerida:** `GET /api/admin/traces?limit=100&event_id=`

---

### 9. Metadata integrity

Invocar `assert_metadata_integrity` bajo demanda:

- Issues: missing `app_ots`, invalid JSON `app_patrones`, `grupo_id` sin grupo
- Botón “scan all events” (background, rate-limited)

---

## Modelo de datos UI (JSON agregado sugerido)

```json
{
  "observatory_version": "1.0",
  "generated_at": "ISO-8601",
  "dashboard": { "...": "get_dashboard_snapshot" },
  "drift": { "...": "get_full_drift_report" },
  "entities": {
    "event": { "snapshot": {}, "convergence": "CONVERGED|PARTIAL|DIVERGED|UNKNOWN", "timeline": [] },
    "group": { "health": {}, "members": [] }
  }
}
```

---

## Endpoints existentes a reutilizar

| Endpoint | Uso en observatory |
|----------|-------------------|
| `GET /api/admin/sync_health` | Dashboard |
| `GET /api/admin/drift_report` | Drift Lab |
| `GET /api/admin/event_timeline/{id}` | Timeline |
| `GET /api/admin/sync_queue` | Cola outbound |
| `GET /api/admin/poll_logs` | Inbound trace |
| `GET /api/admin/reconciliation_logs` | Histórico reconciliación |
| `GET /api/review/pending` | Arbitration |
| `GET /api/poll/status` | Polling health |
| `GET /admin` | Shell HTML |

---

## Endpoints nuevos sugeridos (fase implementación futura)

| Método | Ruta | Propósito |
|--------|------|-----------|
| GET | `/api/admin/observatory/snapshot` | JSON único dashboard+drift |
| GET | `/api/admin/event_snapshot/{id}` | Vista explorer completa |
| GET | `/api/admin/group_health/{grupo_id}` | Vista grupo |
| GET | `/api/admin/traces` | Filtrado traces |
| GET | `/api/admin/convergence/{id}` | Semáforo convergencia |

---

## RBAC y seguridad

- Reutilizar `check_authorization()` en todos los endpoints admin.
- No exponer tokens Google ni PII en traces (enmascarar correos opcional).
- Modo compilado (.exe): observatory solo localhost.

---

## Criterios de éxito (aceptación spec)

1. Operador puede responder “¿por qué este evento saltó de técnico?” en < 2 min usando timeline + reassignment flags.
2. Drift report visible sin ejecutar scripts `scratch/`.
3. Distinción clara entre fallo **critico** (INSERT queue) y **warning** (polling lag).
4. Cada campo en diff de review muestra ownership (PLANNER_OWNED vs CRITICAL).

---

## Relación con documentación Fase A–D

| Documento | Uso en observatory |
|-----------|-------------------|
| Operational Inventory | Lista de operaciones con link a explorer |
| Flow Mapping | Diagramas en ayuda contextual |
| Invariant Registry | Semáforos de salud de grupo / evento |
| Failure Matrix | Alertas dashboard mapeadas 1:1 a indicadores drift |

---

*Spec alineada con `sync_observatory.py` y endpoints admin en `api_server.py` (líneas ~2830+).*
