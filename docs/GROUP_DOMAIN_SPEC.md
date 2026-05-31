# GROUP DOMAIN SPECIFICATION

> **Modo**: Read-only Forensic Analysis
> **Objetivo**: Modelar funcionalmente el dominio de Grupos en el sistema AppPlanificacion, mapeando arquitectura, riesgos, state machines, source of truth e invariantes.

---

## FASE 1 — CONCEPTUAL MODEL

### ¿Qué representa realmente un grupo?
En el dominio de la aplicación, un **grupo** representa una **salida operacional conjunta**: múltiples técnicos asignados para trabajar colaborativamente en una misma Orden de Trabajo (OT) durante la misma franja horaria.

A nivel de software, el grupo actúa como una **agrupación lógica** que envuelve entidades físicas individuales (los eventos). 

### Logical Group vs Physical Events
Existe una dicotomía estricta en el sistema:
1. **Logical Group**: Entidad virtual que existe únicamente en la base de datos de AppPlanificacion. Actúa como el "pegamento" que dice "estos 3 eventos pertenecen a la misma intervención".
2. **Physical Events**: Los eventos reales que residen en Google Calendar. El grupo **no es dueño** de los eventos en Google Calendar; los eventos son independientes y cada uno pertenece a un técnico (`calendar_id`).

### Modelos Coexistentes
El sistema actualmente sufre de complejidad porque mezcla 3 modelos de agrupación que no siempre convergen:
* **Operational Grouping (Local)**: Técnicos agrupados intencionalmente desde el frontend de AppPlanificacion. Tienen una entrada explícita en la tabla `grupos`.
* **Sync Grouping (Google Guests)**: Eventos creados directamente desde Google Calendar añadiendo invitados (Attendees). Google usa un modelo de "Shared Event" (mismo `iCalUID` y `google_event_id`), pero AppPlanificacion los descarga (Sync) y "aplana", tratándolos a priori como eventos separados (`has_guests=true`), sin insertarlos automáticamente en la tabla lógica `grupos` hasta que haya una mutación local.
* **Visual Grouping**: El Frontend (CSS `.ev-grouped` y en renders) los pinta como una unidad cuando comparten OT o `grupo_id`.

---

## FASE 2 — PHYSICAL REPRESENTATION

| Layer | Representación de Grupo | Riesgo Principal | Source of Truth |
|-------|-------------------------|------------------|-----------------|
| **SQLite** | Tabla independiente `grupos` (`event_ids`, `tecnico_nombres`, `ot_nro`) + Campo metadata en `eventos`: `extended_props.private.grupo_id` | Desincronización (Orphan IDs en tabla `grupos` si el evento físico se elimina). | Local Database |
| **Frontend** | Estado global en UI (`currentEvent`), modales de edición unificados. Oculta la complejidad física. | Asume que todos los miembros comparten fecha/hora rígidamente. | UI State |
| **API** | Endpoints de mutación explícita (`agregar_tecnico_a_grupo`, `mover_grupo`). Recalcula títulos grupales masivamente. | Operaciones parciales (falla en el miembro N de N). | API Server |
| **Sync** | **Inexistente**. La capa de Sync NO entiende de grupos. Envía mutaciones evento a evento de forma aislada. | Que el request para el técnico A pase, pero el request para el técnico B falle (Parcial Sync). | Outbound Queue |
| **Polling** | Detecta cambios (ej. Drag & drop en GCal) de forma individual. Genera un *Review* para UN técnico aislado. | No regenera ni reconstruye la intención grupal. | Google Calendar |
| **Arbitration**| El usuario aprueba un cambio desde la cola de polling (`accept_review`) y este muta solo el evento individual local. | **Divergencia temporal severa** (miembros del mismo grupo terminan en días distintos). | Polling Review |

---

## FASE 3 — GROUP STATE MACHINE

### Estados Reales
* **SINGLE**: Evento independiente, sin `grupo_id`.
* **GROUPED**: Múltiples eventos vinculados consistentemente a un `grupo_id`.
* **GROUP_INCONSISTENT** *(Failure State)*: Eventos vinculados a un grupo lógico, pero cuyas fechas/horas físicas han divergido debido a mutaciones parciales (ej. Polling individual).
* **GROUP_ORPHAN** *(Failure State)*: La tabla `grupos` apunta a IDs de eventos que ya fueron borrados por la sincronización (Hard Deletes remotos).
* **GROUP_REASSIGN**: Estado transitorio donde un evento está cambiando de propietario (calendar_id), generando la creación de uno nuevo y la destrucción del viejo.

### Transiciones Principales
* **SINGLE → GROUPED**: `agregar_tecnico_a_grupo` (API crea sibling y registro en tabla `grupos`).
* **GROUPED → GROUPED (Move)**: `mover_grupo` (Loop que mueve N eventos individualmente).
* **GROUPED → SINGLE**: `split_evento` ("Individualizar" rompe el vínculo y destruye el registro lógico).
* **GROUPED → GROUP_INCONSISTENT**: Operador mueve evento en Google Calendar → Polling detecta conflicto individual → `accept_review` altera un solo evento físico del grupo.

---

## FASE 4 — GROUP OPERATIONS ANALYSIS

| Operación | Componentes/Layers afectados | Side Effects Clave | Drift Potential / Riesgo | Estado Actual |
|-----------|------------------------------|--------------------|--------------------------|---------------|
| **Agregar Técnico** | API, SQLite | Crea evento local, inyecta `grupo_id`, recalcula `format_group_summary` en N eventos, encola 1 CREATE y N-1 UPDATEs. | **Medio**: Si falla encolar los UPDATEs, los títulos quedan inconsistentes (Stale Titles). | Soportado |
| **Quitar Técnico** | API, SQLite | Elimina un evento local, borra de la lista grupal, recalcula títulos, encola DELETE. | **Medio**: Orphan event en Google si falla el DELETE. | Soportado |
| **Move Date** | API, Sync | Mueve todos los miembros en un `for-loop`. | **Alto**: Drift parcial si un miembro choca y el otro no. | Soportado |
| **Drag & Drop** | UI, API | Invoca `mover_grupo`. Bloqueado explícitamente si intenta mover Fecha + Técnico al mismo tiempo en eventos grupales. | **Bajo**: Restringido por diseño. | Soportado |
| **Reassign** | API, Sync, SQLite | Remueve del viejo calendario, inyecta en el nuevo. | **Muy Alto**: Ownership transfer en modelos distribuidos sin transacciones atómicas. | Frágil |
| **Individualizar**| API, SQLite | Limpia el flag grupal, recalcula OTs, en multi-días los fragmenta. Elimina evento padre. | **Medio**: Lógica compleja con UUIDs nuevos. | Recién fix |
| **Polling Accept**| Arbitration | Modifica 1 evento. **Rompe Invariante Grupal.** | **Crítico**: Genera divergencia de fechas/horas sin desagrupar lógicamente. | Fallido |

---

## FASE 5 — GROUP INVARIANTS

Reglas de negocio que **nunca** deberían romperse:

| Invariant | Descripción | ¿Se rompe hoy? | Severidad |
|-----------|-------------|----------------|-----------|
| **Integridad Temporal** | Todos los miembros de un `grupo_id` deben tener el mismo `inicio` y `fin`. | **SÍ** (vía Google Calendar Polling). | Crítica |
| **Unicidad de Miembros**| Un `calendar_id` no puede tener 2 eventos asignados al mismo `grupo_id`. | Rara vez (salvo duplicados por reassignment fallido). | Alta |
| **Orphan Protection** | Todo `event_id` dentro del JSON de la tabla `grupos` debe existir físicamente en la tabla `eventos`. | **SÍ** (cuando Sync borra eventos desde un REMOTE_DELETE). | Media |
| **Metadata Consistency**| Títulos (summary) deben reflejar unánimemente a todos los miembros presentes. | **SÍ** (Stale titles por race conditions o fallas de Sync loop). | Baja (Cosmética/Confusión) |
| **Prohibición Multidía**| Eventos complejos no deben editarse directamente sin individualizar. | No (controlado en UI y validación en API). | - |

---

## FASE 6 — FAILURE MODES (Modos de falla reales)

| Síntoma Visible | Root Cause / Trigger | Drift Risk |
|-----------------|----------------------|------------|
| **Stale Titles** (El título dice OT-123(JD+RP) pero RP ya no está) | **Partial Sync**: Quitar a RP fue exitoso, pero el `UPDATE` a Juan (JD) falló o quedó trabado en Sync Queue. | Bajo |
| **Eventos "Saltando" (Divergencia temporal)** | **Polling Race**: RP mueve su evento en Google Calendar. AppPlanificacion recibe el webhook, crea el Review, el usuario lo acepta. AppPlanificacion actualiza a RP, pero JD se queda en el Lunes. Ambos siguen en el mismo `grupo_id`. | **Muy Alto** (Inconsistencia Estructural) |
| **Orphan Groups** (Errores al cargar UI o intentar mover) | **Lineage Corruption**: Evento borrado en Google → remoto DELETE aceptado → Físico borrado, pero `grupos.event_ids` no se limpió. | Medio |
| **Ownership Inconsistente** (Técnico duplicado tras Reassign) | **Reassignment Failure**: Se crea el evento en el nuevo técnico, pero la instrucción `DELETE` en el viejo falla o es rechazada por Google. | Alto |

---

## FASE 7 — SOURCE OF TRUTH ANALYSIS

| Campo / Entidad | ¿Quién es dueño actualmente? (Owner) | Conflictos Notables |
|-----------------|--------------------------------------|---------------------|
| **La Estructura de Grupo**| **AppPlanificacion (SQLite)** | Google Calendar la ignora completamente. Si Google altera la estructura (ej. usuario invita a alguien nativamente), hay cortocircuito conceptual. |
| **Fecha y Horario** | **Ownership Compartido** | SQLite dicta el de todo el grupo, pero Google puede dictar unilateralmente el de 1 solo miembro. Conflicto mortal. |
| **Técnico (calendar_id)** | **Google Calendar** | Es inmutable en Google. Para cambiarlo, hay que destruirlo y recrearlo (Reassignment). |
| **Títulos y OTs** | **AppPlanificacion (SQLite)** | El Backend recalcula constantemente `format_group_summary()`. Si Google lo edita, el sistema prefiere sobreescribirlo u obligar un merge. |

---

## FASE 8 — GOOGLE CALENDAR MODEL

¿Cómo se proyecta el grupo en Google?
AppPlanificacion utiliza estrictamente un modelo de **Mirrored Events (Eventos Espejo)**, NO un modelo centralizado de "Shared Event / Attendees" puro.

* **La ilusión del grupo**: Si la operadora asigna 3 técnicos, el motor de Sync no crea "1 evento e invita a 2". El motor crea **3 eventos idénticos e independientes**, inyectando a cada uno un payload directo en Google Calendar.
* **Beneficio**: Garantiza que si la API de invitaciones falla, el operario igual ve el evento.
* **Perjuicio**: Como Google Calendar los ve independientes, si un técnico arrastra su evento 2 horas más tarde, los otros 2 técnicos NO sufren cambios automáticos en Google. AppPlanificacion asume la titánica tarea de mantener estos "espejos" perfectamente alineados. 

### Conclusión Final
El problema medular del dominio "Group" radica en que **la aplicación intenta imponer un comportamiento transaccional y relacional (el grupo) sobre una infraestructura distribuida e independiente (Google Calendars aislados)**. Cualquier operación sobre el grupo debe tratarse como una "Transacción Distribuida". El mayor vector de falla actualmente es que el componente de **Polling y Arbitration** trata a las entidades de manera aislada, fracturando el estado del grupo sin alertar al sistema.
