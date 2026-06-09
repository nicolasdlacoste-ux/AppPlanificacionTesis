# Fase B — Flow Mapping

> Flujos basados en el comportamiento **efectivo** del código.  
> Distingue rutas **canonical** (SQLite-first + cola) vs **legacy** (sync masivo, endpoints deprecados).

---

## Convenciones

| Símbolo | Significado |
|---------|-------------|
| `→` | Llamada síncrona / siguiente paso |
| `[OPT]` | Actualización optimista en frontend |
| `[Q]` | Encolado en `sync_queue` |
| `[P]` | Procesado por `poll_manager` |
| `[W]` | Procesado por `sync_manager` worker |

**STATE_CONVERGED (global):** para una operación outbound, el evento tiene `sync_status=SUCCESS`, `pending_sync=0`, `google_event_id` estable (no `local_*`), metadata sin `reassignment_in_progress`, y el estado visible en Google coincide con SQLite según `field_ownership` para campos críticos. Para inbound aceptado: review `ACCEPTED` y diff aplicado en SQLite.

---

## 1. Reasignar técnico (individual) — PRIORIDAD 1

### Entry points

| Origen | Ruta |
|--------|------|
| Drag & drop a otra fila (técnico) | `scheduler.js` → `App.moveEvent` → `PATCH /api/eventos/{id}/mover` |
| Panel edición técnico | `right-panel.saveEventEdit` → `_doMove('mover')` |
| Batch editar con `correo_destino` | `POST /api/eventos/batch/editar` |

### Sequence flow

```
Usuario (drag / panel)
    ↓
app.js moveEvent / saveEventEdit
    │  [OPT] actualiza tecnico_nombre, calendar_id, fechas en _eventos
    │  logTrace EVENT_MOVE
    ↓
PATCH /api/eventos/{event_id}/mover
    ↓
api_server.mover_evento
    │  resolve_event(event_id)
    │  si grupo → mover_grupo (otro flujo)
    │  _is_complex_event → 400 si multidía/invitados
    │  optimistic lock base_version → 409
    │  merge metadata (ots, patrones, vehiculo)
    │  is_reassignment = target_cal ≠ calendar_id_orig
    │       → flags reassignment_* en extendedProperties.private
    │       → sync_status REASSIGN_PENDING, operation REMOTE_REASSIGNMENT
    │  data_manager.actualizar_evento_individual (SQLite)
    │  log_trace OUTBOUND_MUTATION
    │  enqueue_sync(..., REMOTE_REASSIGNMENT, original_calendar_id)
    │  post: disolución/reformulación grupo si cambio_tecnico o cambio_fecha
    ↓
Respuesta { status, event_id, version }
    ↓
app.js refreshEvents (post-move)
    ↓
[W] sync_manager.process_queue
    │  _do_remote_reassignment
    │       DELETE events().delete(prev_cal, prev_google_id)  [404 → skip]
    │       INSERT events().insert(new_cal, body)
    │       actualizar_evento_individual: new google_event_id, REASSIGN_COMPLETED
    │       actualizar_event_id_en_grupos(old_gid, new_gid)
    │  anti_loop metadata (source internal)
    ↓
[P] poll_manager (ciclo background)
    │  si reassignment_in_progress → IGNORE (race protection)
    │  tras completar → diff normal o NO_OP por timestamps
    ↓
Planner refresh GET /api/eventos
```

### Inputs / outputs por capa

| Capa | Inputs | Outputs |
|------|--------|---------|
| UI | `event_id`, `calendar_id_origen`, `correo_destino`, `nueva_fecha`, `h_start`, metadata opcional | Estado optimista; toast; `_eventos` refrescado |
| API | `MoverEventoParams` | SQLite mutado; ítem cola; versión nueva |
| DataManager | `data` dict con `extendedProperties`, `calendar_id`, `sync_status` | `version++`; traces |
| SyncWorker | evento DB + `original_calendar_id` | Google DELETE+INSERT; nuevo `google_event_id` |
| Poll | evento Google en calendario destino | ignored durante flag; luego reconciliación |

### Mutaciones

| Store | Qué cambia |
|-------|------------|
| SQLite `eventos` | `tecnico_nombre`, `calendar_id`, `inicio/fin`, `summary`, `extended_props`, `sync_status`, `google_event_id` (post-worker) |
| SQLite `grupos` | Puede disolver o reformular miembros |
| Google Calendar | Evento borrado en calendario A; creado en calendario B |
| `sync_queue` | 1× REMOTE_REASSIGNMENT → DONE/FAILED |
| Frontend | `_eventos` (optimista hasta refresh) |

### Ownership (reasignación)

| Campo | Autoridad durante operación | Post-convergencia |
|-------|----------------------------|-------------------|
| `summary`, `inicio`, `fin` | Planner (outbound) hasta SUCCESS | SHARED_CRITICAL — cambios Google → review |
| `app_ots`, `app_patrones`, `app_vehiculo`, `grupo_id` | PLANNER_OWNED — poll no sobrescribe | Planner |
| `google_event_id` | Sistema (worker reassignment) | Google es source of truth del ID remoto |
| `tecnico_nombre` / calendar | Planner en move | Debe coincidir con calendario destino |
| `version` | SQLite incrementa en cada `actualizar_evento_individual` | Local |

### Convergencia esperada

- `sync_status` ∈ {`REASSIGN_COMPLETED`, `SUCCESS`}
- `pending_sync=0`
- `reassignment_in_progress` ausente en metadata
- Un solo `google_event_id` activo por fila lógica
- Grupo: miembro removido o grupo disuelto según reglas de `mover_evento`
- UI muestra técnico destino tras `refreshEvents`

---

## 2. Group lifecycle — PRIORIDAD 2

### 2a. Agregar técnico

```
right-panel → POST /api/eventos/{id}/agregar_tecnico?tecnico_correo&calendar_id
    → resolve base event
    → format_group_summary (iniciales)
    → UPDATE títulos miembros existentes + enqueue UPDATE cada uno
    → guardar_evento_individual local_* nuevo técnico + enqueue CREATE
    → crear_o_actualizar_grupo o vincular
    → update_group_title
```

**Mutaciones:** +1 fila `eventos`, tabla `grupos` ampliada, N updates Google en cola.

**Convergencia:** todos los miembros con mismo tag `- ND/LR/...` en summary; cada miembro `SUCCESS` en sync.

### 2b. Quitar técnico / Delete

```
UI delete / quitar
    → POST quitar_tecnico OR DELETE /api/eventos/{id} (alias)
    → enqueue DELETE (google_event_id)
    → eliminar_evento_individual (SQLite)
    → actualizar o eliminar grupo; clean_title si disuelve
    → [W] _do_delete en Google
```

**Convergencia:** fila eliminada localmente; evento ausente en Google; grupo con ≥2 miembros reformulado o eliminado.

### 2c. Mover grupo (fecha)

```
PATCH /api/eventos/{id}/mover_grupo
    → rechaza cambio fecha+técnico simultáneo (400)
    → loop event_ids: actualizar fechas, grupo_id preservado
    → enqueue UPDATE por miembro
    → crear_o_actualizar_grupo (nueva fecha)
    → _auto_agrupar_evento (puede fusionar con otros misma OT)
```

**Entry:** drag con `scope=grupo` y solo cambio fecha; panel `mover_grupo`.

### 2d. Individualizar vs Split

| | Individualizar | Split |
|--|----------------|-------|
| Endpoint | `POST .../individualizar` | `POST .../split` |
| Google | UPDATE título miembro saliente | DELETE originales + CREATE por día |
| Grupo | Reduce miembros o disuelve | Disuelve original; crea grupos por día |
| Uso | Salir del grupo sin borrar | Multidía → eventos editables diarios |

---

## 3. Drag & drop — PRIORIDAD 6

```
scheduler (drop)
    → App.moveEvent(google_event_id, calendarId, destCorreo, nuevaFecha, hora)
    → GET /api/grupos/evento/{id}  (detecta grupo)
    → si grupo y cambio técnico+fecha → toast error (cliente)
    → si grupo → doMove('grupo')
         │  si cambio técnico → endpoint reasignar_tecnico_grupo  ⚠ NO EXISTE
         │  si solo fecha → PATCH mover_grupo
    → si solo → PATCH mover (puede incluir reassignment)
```

**Invariante UI:** no fecha+técnico simultáneo en grupo (validado en cliente y servidor en `mover_grupo`).

---

## 4. Sync / Polling / Arbitration — PRIORIDAD 3

### 4a. Outbound genérico (UPDATE)

```
API mutation → actualizar_evento_individual (pending_sync=1)
    → enqueue_sync(CREATE|UPDATE|DELETE|REMOTE_REASSIGNMENT)
    → [W] process_queue
         CREATE: insert o update 404→insert
         UPDATE: events().update
         DELETE: events().delete
    → sync_status SUCCESS, pending_sync=0
```

### 4b. Inbound poll cycle

```
poll_manager.start → loop cada N seg
    → _poll_all_calendars
    → events().list(calendarId, updatedMin, singleEvents)
    → _process_incoming_event (por evento)
         cancelled → _handle_cancelled → review REMOTE_DELETE
         internal source → IGNORE
         local null → enqueue_review REMOTE_CREATE
         g_updated <= local_updated → NO_OP_STALE
         diff + FieldOwnershipRegistry
         safe → apply_poll_safe_changes
                  critical → evalúa poll_routing_config
              AUTO_APPLY → data_manager.accept_review
              INBOX → enqueue_review FIELD_CHANGE
              IGNORE → marca como ignored
    → UI poll.js badge GET /api/review/pending
```

### 4c. Accept review

```
poll.js → POST /api/review/{id}/accept
    → data_manager.accept_review
         REMOTE_CREATE → INSERT OR REPLACE eventos
         FIELD_CHANGE → actualizar_evento_individual (pending_sync=0)
         REMOTE_DELETE → sync_state CANCELLED_IN_GOOGLE
         lookup fail → ValueError → HTTP 422
    → status ACCEPTED, resolved_at
```

**Reject:** preserva SQLite; encola UPDATE o DELETE outbound para “ganar” Planner.

### 4d. Sync cloud (legacy)

```
GET /api/sync → descarga masiva calendarios
    → upsert eventos SQLite
    → no pasa por review queue
    → puede ejecutarse con app abierta (riesgo de pisar mutaciones pendientes)
```

---

## 5. Crear evento — flujo y gap

```
POST /api/eventos/crear
    → por cada día: local_* en SQLite
    → enqueue_sync(..., "INSERT")   ⚠ worker no implementa INSERT
    → _auto_agrupar_evento
```

**Convergencia esperada (diseño):** CREATE en Google + `google_event_id` real.  
**Comportamiento observado:** cola con operación `INSERT` no dispara `_do_create` (solo ramas `CREATE`/`UPDATE`/`REMOTE_REASSIGNMENT`).

---

## 6. Lifecycle map — estado sync de un evento

```
                    ┌─────────────┐
                    │  local_*    │
                    │  PENDING    │
                    └──────┬──────┘
                           │ enqueue CREATE/UPDATE
                           ▼
                    ┌─────────────┐
              ┌────│ PROCESSING  │────┐
              │    └─────────────┘    │
              │           │           │
         retry│      SUCCESS│    FAILED / REASSIGN_*_FAILED
              │           ▼           │
              │    ┌─────────────┐    │
              └────│   SUCCESS   │    │
                   └─────────────┘    │
                                      ▼
                              (manual / reject resync)

Reassignment branch:
PENDING → REASSIGN_PENDING → [W] DELETE+INSERT → REASSIGN_COMPLETED → SUCCESS
         poll IGNORE while reassignment_in_progress
```

---

## 7. Ownership map (resumen visual)

```
┌──────────────────────────────────────────────────────────────┐
│                     PLANNER_OWNED (private)                   │
│  app_ots, app_patrones, app_vehiculo, grupo_id, version,     │
│  sync_status, reassignment_*, mutation_type, hydrated        │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                   SHARED_CRITICAL (top-level)                 │
│  summary, inicio, fin, tecnico_nombre → review si inbound    │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                      SHARED_SAFE                              │
│  descripcion, ubicacion → auto-merge inbound                 │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                      GOOGLE_OWNED                             │
│  status, etag, updated, organizer, ...                        │
└──────────────────────────────────────────────────────────────┘
```

---

## 8. Operaciones críticas — tabla entry → convergencia

| Operación | Entry point | Convergencia (STATE_CONVERGED) |
|-----------|-------------|--------------------------------|
| Reassignment | drag/panel `mover` | REASSIGN_COMPLETED + gid nuevo + grupo consistente |
| Group move fecha | `mover_grupo` | Todos miembros misma fecha; grupo.fecha actualizado |
| Delete | delete UI | Sin fila local; sin evento Google |
| Accept review | poll modal | SQLite = remote snapshot; review ACCEPTED |
| Polling safe | automático | Campos safe igualados sin review pendiente |
| Sync retry | worker automático | Cola DONE o FAILED terminal |
| Individualize | botón panel | Fuera de grupo; título sin tag grupo |
| Split | botón panel | N eventos día; originales borrados en Google |

---

*Referencias código: `api_server.py`, `sync_manager.py`, `poll_manager.py`, `field_ownership.py`, `webapp/app.js`, `webapp/scheduler.js`.*
