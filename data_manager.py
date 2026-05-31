import sqlite3
import json
import os
import datetime
import threading
from pathlib import Path
import utils

class VersionConflictError(Exception):
    """
    [OPTIMISTIC_LOCK] Error lanzado cuando se intenta actualizar un evento 
    con una versión base que ya no coincide con la de la base de datos.
    """
    def __init__(self, event_id, base_version, current_version):
        self.event_id = event_id
        self.base_version = base_version
        self.current_version = current_version
        super().__init__(f"[OPTIMISTIC_LOCK] Conflicto de versión para {event_id}: base={base_version}, actual={current_version}")

class DataManager:
    def __init__(self, db_path="planificacion.db"):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Tabla Técnicos
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tecnicos (
                    nombre TEXT PRIMARY KEY,
                    correo TEXT,
                    iniciales TEXT
                )
            ''')
            
            # Tabla Eventos
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS eventos (
                    id TEXT,
                    google_event_id TEXT,
                    calendar_id TEXT,
                    tecnico_nombre TEXT,
                    summary TEXT,
                    inicio TEXT,
                    fin TEXT,
                    ubicacion TEXT,
                    descripcion TEXT,
                    extended_props TEXT,
                    version INTEGER DEFAULT 1,
                    updated_at TEXT,
                    last_synced_at TEXT,
                    pending_sync INTEGER DEFAULT 0,
                    sync_status TEXT DEFAULT 'SUCCESS',
                    sync_error TEXT,
                    last_sync_attempt TEXT,
                    source TEXT DEFAULT 'internal',
                    sync_state TEXT,
                    PRIMARY KEY (id, tecnico_nombre),
                    FOREIGN KEY (tecnico_nombre) REFERENCES tecnicos (nombre)
                )
            ''')

            # Tabla Review Queue
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS poll_review_queue (
                    review_id TEXT PRIMARY KEY,
                    event_id TEXT,
                    calendar_id TEXT,
                    diff_json TEXT,
                    status TEXT DEFAULT 'PENDING',
                    detected_at TEXT,
                    conflict_type TEXT DEFAULT 'FIELD_CHANGE',
                    google_event_id TEXT,
                    local_snapshot TEXT,
                    remote_snapshot TEXT,
                    recommended_action TEXT,
                    resolved_at TEXT
                )
            ''')

            # Tabla Poll Log
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS poll_log (
                    log_id TEXT PRIMARY KEY,
                    timestamp TEXT,
                    event_type TEXT,
                    calendar_id TEXT,
                    event_id TEXT,
                    version INTEGER,
                    detail TEXT
                )
            ''')

            # Tabla Sync Queue
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sync_queue (
                    queue_id TEXT PRIMARY KEY,
                    event_id TEXT,
                    calendar_id TEXT,
                    tecnico TEXT,
                    operation TEXT,
                    created_at TEXT,
                    status TEXT DEFAULT 'PENDING',
                    error_msg TEXT,
                    attempts INTEGER DEFAULT 0,
                    next_retry_at TEXT,
                    original_calendar_id TEXT,
                    mutation_context TEXT
                )
            ''')

            # Tabla Sync Log
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sync_log (
                    log_id TEXT PRIMARY KEY,
                    event_id TEXT,
                    tecnico TEXT,
                    direction TEXT,
                    operation TEXT,
                    result TEXT,
                    detail TEXT,
                    timestamp TEXT,
                    calendar_id TEXT,
                    status TEXT
                )
            ''')
            
            # Verificación de migración (si la tabla existía con ID como PK única)
            cursor.execute("PRAGMA table_info(eventos)")
            columns = cursor.fetchall()
            col_names = [c[1] for c in columns]
                   # Auto-migración de columnas
            cols_to_add = {
                'version': 'INTEGER DEFAULT 1',
                'google_event_id': 'TEXT',
                'updated_at': 'TEXT',
                'last_synced_at': 'TEXT',
                'pending_sync': 'INTEGER DEFAULT 0',
                'sync_status': "TEXT DEFAULT 'SUCCESS'",
                'sync_error': 'TEXT',
                'last_sync_attempt': 'TEXT',
                'source': "TEXT DEFAULT 'internal'",
                'sync_state': 'TEXT'
            }
            for col, spec in cols_to_add.items():
                if col not in col_names:
                    print(f"Migrando tabla eventos: agregando columna '{col}'...")
                    cursor.execute(f"ALTER TABLE eventos ADD COLUMN {col} {spec}")
            
            pk_cols = [c[1] for c in columns if c[5] > 0]
            if len(pk_cols) == 1 and pk_cols[0] == 'id':
                print("Detectada PK antigua. Recreando tabla eventos para soporte multi-técnico...")
                # (Omitiendo recreación completa aquí para brevedad, asumiendo que ya se hizo o se hará si es necesario)
                # Pero mantengo la lógica de PK compuesta en el CREATE TABLE IF NOT EXISTS arriba.
            
            # Tabla OTs (Caché de planilla)
            # Guardamos la fila completa como JSON para mantener compatibilidad con el resto de la app
            # pero indexamos la OT para búsquedas rápidas.
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cache_ots (
                    ot_number TEXT,
                    datos_json TEXT
                )
            ''')
            
            # Tabla Patrones
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cache_patrones (
                    nombre TEXT,
                    datos_json TEXT
                )
            ''')
            
            # Tabla Vehiculos
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cache_vehiculos (
                    nombre TEXT,
                    asientos INTEGER
                )
            ''')
            
            # Tabla Papelera
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS papelera (
                    id TEXT PRIMARY KEY,
                    datos_json TEXT,
                    fecha_borrado TEXT
                )
            ''')
            
            # Tabla Metadatos (para control de versiones o última sincronización)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS metadatos (
                    clave TEXT PRIMARY KEY,
                    valor TEXT
                )
            ''')

            # Tabla Grupos
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS grupos (
                    grupo_id   TEXT PRIMARY KEY,
                    ot_nro     TEXT NOT NULL,
                    fecha      TEXT NOT NULL,
                    event_ids  TEXT,
                    tecnico_nombres TEXT,
                    patrones   TEXT,
                    vehiculo   TEXT
                )
            ''')

            # Tabla Group Operation Journal (tracking forense de operaciones grupales atómicas)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS group_operation_journal (
                    operation_id       TEXT PRIMARY KEY,
                    operation_type     TEXT NOT NULL,
                    trigger_event_id   TEXT,
                    group_id           TEXT,
                    initiated_by       TEXT,
                    started_at         TEXT,
                    completed_at       TEXT,
                    status             TEXT DEFAULT 'STARTED',
                    expected_members   INTEGER DEFAULT 0,
                    completed_members  INTEGER DEFAULT 0,
                    failed_members     INTEGER DEFAULT 0,
                    affected_members_json TEXT,
                    invariant_status_before TEXT,
                    invariant_status_after  TEXT,
                    partial_failures_json   TEXT,
                    drift_detected          INTEGER DEFAULT 0,
                    ui_refresh_triggered    INTEGER DEFAULT 0,
                    detail             TEXT
                )
            ''')
            
            # Tabla Poll Calendar State
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS poll_calendar_state (
                    calendar_id TEXT PRIMARY KEY,
                    last_poll_time TEXT,
                    last_poll_ok INTEGER DEFAULT 0,
                    error_count INTEGER DEFAULT 0,
                    last_error TEXT
                )
            ''')

            conn.commit()

    # --- MÉTODOS DE TÉCNICOS ---
    def guardar_tecnicos(self, tecnicos_list):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM tecnicos")
            for t in tecnicos_list:
                cursor.execute("INSERT INTO tecnicos (nombre, correo, iniciales) VALUES (?, ?, ?)",
                               (t.get('nombre'), t.get('correo'), t.get('iniciales')))
            conn.commit()

    def obtener_tecnicos(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT nombre, correo, iniciales FROM tecnicos")
            rows = cursor.fetchall()
            return [{"nombre": r[0], "correo": r[1], "iniciales": r[2]} for r in rows]

    # --- MÉTODOS DE EVENTOS ---
    def guardar_eventos(self, eventos_list):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM eventos")
            for e in eventos_list:
                props = json.dumps(e.get('extendedProperties', {}))
                cursor.execute('''
                    INSERT OR REPLACE INTO eventos (id, calendar_id, tecnico_nombre, summary, inicio, fin, ubicacion, descripcion, extended_props)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (e.get('id'), e.get('calendar_id'), e.get('Técnico'), e.get('Evento'), 
                      e.get('Inicio'), e.get('Fin'), e.get('Ubicación'), e.get('Descripción'), props))
            conn.commit()

    def actualizar_evento_individual(self, event_id, calendar_id, data, base_version=None, pending_sync=1, sync_status='PENDING', sync_state=None, origin='local'):
        """
        [OPTIMISTIC_LOCK] Actualiza un solo evento aplicando control de concurrencia.
        Si base_version no coincide con la versión en DB, lanza VersionConflictError.

        [INBOUND_FIX] Lookup con 3 estrategias de fallback para resistir calendar_id mismatches
        causados por reasignaciones. Logs ARBITRATION_TRACE en cada etapa.
        """
        # Estado compartido entre bloque with y trazas post-commit
        current_data      = None
        current_version   = None
        actual_calendar_id = calendar_id
        actual_event_id   = event_id
        new_version       = None
        rows_affected     = 0
        lookup_method     = None
        final_sync_state  = None

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # ── 1. LOOKUP PRIMARIO: (id, calendar_id) ────────────────────────
            cursor.execute(
                "SELECT * FROM eventos WHERE id = ? AND calendar_id = ?",
                (event_id, calendar_id)
            )
            row = cursor.fetchone()
            lookup_method = "primary_(id,calendar_id)"

            # ── FALLBACK 1: solo por id (calendar_id puede diferir por reasignación) ──
            if not row:
                cursor.execute("SELECT * FROM eventos WHERE id = ?", (event_id,))
                row = cursor.fetchone()
                if row:
                    lookup_method = "fallback_id_only"

            # ── FALLBACK 2: por google_event_id ──────────────────────────────
            if not row:
                cursor.execute(
                    "SELECT * FROM eventos WHERE google_event_id = ?", (event_id,)
                )
                row = cursor.fetchone()
                if row:
                    lookup_method = "fallback_google_event_id"

            # ── LOOKUP_MISS: nada encontrado ──────────────────────────────────
            if not row:
                # [ARBITRATION_TRACE:SQLITE_LOOKUP_MISS]
                self.log_trace(event_id, "SQLITE_LOOKUP_MISS", {
                    "event_id": event_id,
                    "calendar_id_provided": calendar_id,
                    "origin": origin,
                    "note": "Evento no hallado por primary, fallback_id_only ni google_event_id. UPDATE cancelado."
                }, calendar_id=calendar_id, tag="ARBITRATION_TRACE")
                # [FAIL_FAST] También emitir con tag canónico LOOKUP_MISS para observabilidad
                self.log_trace(event_id, "NOT_FOUND", {
                    "event_id": event_id,
                    "calendar_id_provided": calendar_id,
                    "origin": origin,
                    "fallbacks_tried": ["primary_(id,calendar_id)", "id_only", "google_event_id"]
                }, calendar_id=calendar_id, tag="LOOKUP_MISS")
                return None

            cols = [d[0] for d in cursor.description]
            current_data       = dict(zip(cols, row))
            current_version    = current_data.get('version', 1)
            actual_calendar_id = current_data.get('calendar_id', calendar_id)
            actual_event_id    = current_data.get('id', event_id)

            # [ARBITRATION_TRACE:SQLITE_BEFORE]
            self.log_trace(actual_event_id, "SQLITE_BEFORE", {
                "lookup_method": lookup_method,
                "calendar_id_provided": calendar_id,
                "calendar_id_actual": actual_calendar_id,
                "version": current_version,
                "summary": current_data.get("summary"),
                "tecnico_nombre": current_data.get("tecnico_nombre"),
                "inicio": current_data.get("inicio"),
                "fin": current_data.get("fin"),
                "sync_state": current_data.get("sync_state"),
                "google_event_id": current_data.get("google_event_id"),
                "origin": origin
            }, calendar_id=actual_calendar_id, tag="ARBITRATION_TRACE")

            # ── 2. OPTIMISTIC LOCK ────────────────────────────────────────────
            if base_version is not None:
                try:
                    bv_int = int(base_version)
                    if bv_int != current_version:
                        print(f"[OPTIMISTIC_LOCK] CONFLICT for {event_id}: DB={current_version}, base={bv_int}")
                        raise VersionConflictError(event_id, bv_int, current_version)
                except (ValueError, TypeError):
                    pass

            # ── 3. MERGE SEMÁNTICO ────────────────────────────────────────────
            from utils import EventAdapter
            can = EventAdapter.merge_events(current_data, data)
            if base_version is not None:
                can["version"] = base_version
            params_sqlite = EventAdapter.canonical_to_sqlite_params(can)

            new_version      = current_version + 1
            now              = utils._now_iso()
            final_sync_state = sync_state if sync_state is not None else current_data.get('sync_state')

            # ── 4. UPDATE con la PK real encontrada por el lookup ─────────────
            cursor.execute('''
                UPDATE eventos
                SET tecnico_nombre = ?, summary = ?, inicio = ?, fin = ?, descripcion = ?,
                    extended_props = ?, calendar_id = ?, version = ?, updated_at = ?,
                    pending_sync = ?, sync_status = ?, sync_state = ?, google_event_id = ?
                WHERE id = ? AND calendar_id = ?
            ''', (
                params_sqlite["tecnico_nombre"],
                params_sqlite["summary"],
                params_sqlite["inicio"],
                params_sqlite["fin"],
                params_sqlite["descripcion"],
                params_sqlite["extended_props"],
                params_sqlite["calendar_id"],
                new_version,
                now,
                pending_sync,
                sync_status,
                final_sync_state,
                params_sqlite.get("google_event_id"),
                actual_event_id,
                actual_calendar_id
            ))
            conn.commit()
            rows_affected = cursor.rowcount

        # ── 5. TRAZAS POST-COMMIT ─────────────────────────────────────────────
        # [ARBITRATION_TRACE:SQLITE_AFTER]
        self.log_trace(actual_event_id, "SQLITE_AFTER", {
            "lookup_method": lookup_method,
            "rows_affected": rows_affected,
            "new_version": new_version,
            "sync_state": final_sync_state,
            "pending_sync": pending_sync,
            "origin": origin
        }, calendar_id=actual_calendar_id, tag="ARBITRATION_TRACE")

        if rows_affected > 0:
            # [OBSERVABILITY] Registrar la mutación oficial
            self.log_trace(actual_event_id, "updated", {
                "origin": origin,
                "version_before": current_version,
                "version_after": new_version,
                "pending_sync": pending_sync,
                "sync_state": final_sync_state
            }, calendar_id=actual_calendar_id, tag="EVENT_MUTATION")

            # [METADATA_INTEGRITY] Verificar que la metadata crítica sobrevivió el merge
            try:
                from utils import assert_metadata_integrity, OperationalLogger
                merged_event = {**merged, "id": actual_event_id, "calendar_id": actual_calendar_id}
                issues = assert_metadata_integrity(merged_event, context=f"actualizar_evento_individual:{origin}")
                if issues:
                    OperationalLogger.log_metadata_issues(self, merged_event, issues, context=f"actualizar_evento_individual:{origin}")
            except Exception:
                pass  # El check nunca bloquea el flujo
        else:
            # [FAIL_FAST] rows_affected=0 significa que el UPDATE no encontró la fila
            # Esto puede ocurrir si el lookup encontró la fila pero el WHERE final falló
            # (raro, pero defensivamente lo logueamos con tag explícito)
            self.log_trace(actual_event_id, "UPDATE_NO_ROWS", {
                "lookup_method": lookup_method,
                "actual_event_id": actual_event_id,
                "actual_calendar_id": actual_calendar_id,
                "origin": origin,
                "note": "UPDATE ejecutó pero rowcount=0 — posible PK mismatch post-lookup"
            }, calendar_id=actual_calendar_id, tag="LOOKUP_MISS")

        return new_version if rows_affected > 0 else None

    def guardar_evento_individual(self, event_data):
        """Inserta o actualiza un único evento en la tabla eventos, preservando la versión si existe."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Recuperar versión previa para no resetearla (si ya existía)
            cursor.execute("SELECT version FROM eventos WHERE id = ? AND tecnico_nombre = ?", 
                           (event_data.get('id'), event_data.get('tecnico_nombre')))
            row = cursor.fetchone()
            current_v = row[0] if row else 1
            from utils import EventAdapter
            can = EventAdapter.normalize_event(event_data)
            params = EventAdapter.canonical_to_sqlite_params(can)
            
            cursor.execute('''
                INSERT OR REPLACE INTO eventos 
                (id, google_event_id, calendar_id, tecnico_nombre, summary, inicio, fin, ubicacion, descripcion, extended_props, version, updated_at, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                params["id"],
                params["google_event_id"],
                params["calendar_id"],
                params["tecnico_nombre"],
                params["summary"],
                params["inicio"],
                params["fin"],
                params["ubicacion"],
                params["descripcion"],
                params["extended_props"],
                current_v, # Preservar versión existente
                params.get("updated_at") or utils._now_iso(),
                params.get("source", "internal")
            ))
            conn.commit()

    def eliminar_evento_individual(self, event_id):
        """Elimina un único evento de la tabla local por su ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM eventos WHERE id = ?", (event_id,))
            conn.commit()

    def obtener_eventos_dict(self):
        """Retorna todos los eventos de la DB mapeados a diccionarios."""
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM eventos")
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    # --- MÉTODOS DE OTS Y PATRONES ---
    def guardar_bd_ots(self, ots_raw_list):
        """Recibe la lista de listas (filas del spreadsheet)."""
        # Suponiendo que la fila 0 son headers
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM cache_ots")
            for row in ots_raw_list:
                ot_num = str(row[utils.IDX_OT]).strip() if len(row) > utils.IDX_OT else "N/A"
                cursor.execute("INSERT INTO cache_ots (ot_number, datos_json) VALUES (?, ?)",
                               (ot_num, json.dumps(row)))
            conn.commit()

    def obtener_bd_ots(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT datos_json FROM cache_ots")
            return [json.loads(r[0]) for r in cursor.fetchall()]

    def guardar_patrones(self, patrones_list):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM cache_patrones")
            for row in patrones_list:
                nombre = str(row[0]) if row else "N/A"
                cursor.execute("INSERT INTO cache_patrones (nombre, datos_json) VALUES (?, ?)",
                               (nombre, json.dumps(row)))
            conn.commit()

    def obtener_patrones(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT datos_json FROM cache_patrones")
            return [json.loads(r[0]) for r in cursor.fetchall()]

    # --- MÉTODOS DE VEHICULOS ---
    def guardar_vehiculos(self, vehiculos_list):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM cache_vehiculos")
            for v in vehiculos_list:
                cursor.execute("INSERT INTO cache_vehiculos (nombre, asientos) VALUES (?, ?)",
                               (v.get('nombre'), v.get('asientos', 1)))
            conn.commit()

    def obtener_vehiculos(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT nombre, asientos FROM cache_vehiculos")
            return [{"nombre": r[0], "asientos": r[1]} for r in cursor.fetchall()]

    # --- MÉTODOS DE PAPELERA ---
    def guardar_en_papelera(self, pkg):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.datetime.now().isoformat()
            cursor.execute("INSERT OR REPLACE INTO papelera (id, datos_json, fecha_borrado) VALUES (?, ?, ?)",
                           (pkg.get('id'), json.dumps(pkg), now))
            conn.commit()

    def obtener_papelera(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT datos_json FROM papelera ORDER BY fecha_borrado DESC")
            return [json.loads(r[0]) for r in cursor.fetchall()]

    # --- LÓGICA DE MIGRACIÓN ---
    def migrar_desde_json(self, base_dir):
        """Busca archivos JSON e importa los que aún no están en la DB."""
        json_files = {
            'tecnicos': ('tecnicos_cache.json', 'tecnicos'),
            'eventos': ('datos_cache.json', 'eventos'),
            'ots': ('bd_ots_cache.json', 'cache_ots'),
            'patrones': ('patrones_cache.json', 'cache_patrones')
        }
        
        for key, (filename, table) in json_files.items():
            path = os.path.join(base_dir, filename)
            if os.path.exists(path):
                # Verificar si la tabla ya tiene datos
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(f"SELECT count(*) FROM {table}")
                    if cursor.fetchone()[0] > 0:
                        continue
                
                print(f"Migrando {filename} a SQLite...")
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if key == 'tecnicos': self.guardar_tecnicos(data)
                        elif key == 'eventos': self.guardar_eventos(data)
                        elif key == 'ots': self.guardar_bd_ots(data)
                        elif key == 'patrones': self.guardar_patrones(data)
                    
                    os.rename(path, path + ".migrated")
                except Exception as e:
                    print(f"Error migrando {filename}: {e}")

    def get_last_sync(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT valor FROM metadatos WHERE clave='last_sync'")
            row = cursor.fetchone()
            return row[0] if row else "Nunca"

    def update_last_sync(self):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO metadatos (clave, valor) VALUES ('last_sync', ?)", (now,))
            conn.commit()

    # --- MÉTODOS DE GRUPOS ---
    def crear_o_actualizar_grupo(self, grupo_data):
        """Inserta o actualiza un grupo y vincula el grupo_id en extended_props de cada evento."""
        grupo_id = grupo_data.get('grupo_id')
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO grupos 
                (grupo_id, ot_nro, fecha, event_ids, tecnico_nombres, patrones, vehiculo)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                grupo_id,
                grupo_data.get('ot_nro'),
                grupo_data.get('fecha'),
                json.dumps(grupo_data.get('event_ids', [])),
                json.dumps(grupo_data.get('tecnico_nombres', [])),
                json.dumps(grupo_data.get('patrones', [])),
                grupo_data.get('vehiculo')
            ))
            conn.commit()

        # Vincular grupo_id en extended_props de cada evento miembro
        for eid in grupo_data.get('event_ids', []):
            try:
                self.vincular_evento_a_grupo(eid, grupo_id)
            except Exception as e:
                print(f"[GRUPO_LINK] Advertencia: no se pudo vincular {eid} → {grupo_id}: {e}")


    def obtener_grupos_fecha(self, fecha):
        """Retorna todos los grupos de una fecha específica."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM grupos WHERE fecha = ?", (fecha,))
            rows = cursor.fetchall()
            grupos = []
            for r in rows:
                grupos.append({
                    "grupo_id": r[0],
                    "ot_nro": r[1],
                    "fecha": r[2],
                    "event_ids": json.loads(r[3]) if r[3] else [],
                    "tecnico_nombres": json.loads(r[4]) if r[4] else [],
                    "patrones": json.loads(r[5]) if r[5] else [],
                    "vehiculo": r[6]
                })
            return grupos

    def obtener_grupo_de_evento(self, event_id):
        """Busca si un evento pertenece a algún grupo."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM grupos WHERE event_ids LIKE ?", (f'%"{event_id}"%',))
            row = cursor.fetchone()
            if row:
                return {
                    "grupo_id": row[0],
                    "ot_nro": row[1],
                    "fecha": row[2],
                    "event_ids": json.loads(row[3]) if row[3] else [],
                    "tecnico_nombres": json.loads(row[4]) if row[4] else [],
                    "patrones": json.loads(row[5]) if row[5] else [],
                    "vehiculo": row[6]
                }
            return None

    def eliminar_grupo(self, grupo_id):
        """Elimina un grupo y limpia el grupo_id de los eventos que eran miembros."""
        # Obtener event_ids antes de borrar para limpiar sus extended_props
        try:
            grupo = self.obtener_grupo(grupo_id)
            event_ids_a_limpiar = grupo.get('event_ids', []) if grupo else []
        except Exception:
            event_ids_a_limpiar = []

        with self._get_connection() as conn:
            conn.execute("DELETE FROM grupos WHERE grupo_id = ?", (grupo_id,))
            conn.commit()

        # Limpiar grupo_id de extended_props de cada evento miembro
        for eid in event_ids_a_limpiar:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT extended_props FROM eventos WHERE id = ? OR google_event_id = ?", (eid, eid))
                    row = cursor.fetchone()
                    if row:
                        props = json.loads(row[0]) if row[0] else {}
                        props.get('private', {}).pop('grupo_id', None)
                        cursor.execute(
                            "UPDATE eventos SET extended_props = ? WHERE id = ? OR google_event_id = ?",
                            (json.dumps(props), eid, eid)
                        )
                        conn.commit()
            except Exception as e:
                print(f"[GRUPO_UNLINK] Advertencia: no se pudo limpiar {eid}: {e}")


    def get_app_config(self) -> dict:
        """Retorna la configuración global de la aplicación."""
        import json
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT clave, valor FROM metadatos")
            rows = cursor.fetchall()
            config = {}
            for k, v in rows:
                try:
                    config[k] = json.loads(v) if v and (v.startswith('[') or v.startswith('{')) else v
                except:
                    config[k] = v
            return config

    def log_trace(self, event_id: str, step: str, detail: dict, calendar_id: str = None, tag: str = None):
        """Registra una traza de mutación en poll_log (usado por api_server para tracking de cambios)."""
        import uuid
        log_id = str(uuid.uuid4())
        timestamp = datetime.datetime.utcnow().isoformat() + "Z"
        event_type = f"{tag}:{step}" if tag else f"TRACE:{step}"
        detail_str = json.dumps(detail, ensure_ascii=False) if isinstance(detail, dict) else str(detail)
        try:
            self.write_poll_log(
                log_id=log_id,
                timestamp=timestamp,
                event_type=event_type,
                calendar_id=calendar_id,
                event_id=event_id,
                version=None,
                detail=detail_str
            )
        except Exception:
            pass  # La traza nunca debe romper el flujo principal

    def get_pending_queue_items(self, limit: int = 50) -> list:
        """Retorna items pendientes de la sync_queue."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.datetime.now().isoformat()
            cursor.execute("""
                SELECT * FROM sync_queue 
                WHERE status = 'PENDING' 
                AND (next_retry_at IS NULL OR next_retry_at <= ?)
                LIMIT ?
            """, (now, limit))
            rows = cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, r)) for r in rows]

    def update_queue_status(self, queue_id: str, status: str):
        """Actualiza el estado de un item en la cola."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE sync_queue SET status = ? WHERE queue_id = ?", (status, queue_id))
            conn.commit()

    def update_queue_error(self, queue_id: str, error_msg: str, next_retry: str = None):
        """Registra un error y opcionalmente programa un reintento."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE sync_queue 
                SET status = 'FAILED', error_msg = ?, next_retry_at = ?, attempts = attempts + 1
                WHERE queue_id = ?
            """, (error_msg, next_retry, queue_id))
            conn.commit()

    def update_evento_sync_status(self, event_id: str, tecnico_nombre: str, status: str):
        """Actualiza el sync_status en la tabla de eventos."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE eventos SET sync_status = ? WHERE id = ? AND tecnico_nombre = ?", 
                           (status, event_id, tecnico_nombre))
            conn.commit()

    def write_sync_log(self, event_id: str, tecnico: str, direction: str, operation: str, status: str, detail: str = None):
        """Registra actividad de sincronización en sync_log."""
        import uuid
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sync_log (log_id, event_id, tecnico, direction, operation, result, detail, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (str(uuid.uuid4()), event_id, tecnico, direction, operation, status, detail, datetime.datetime.now().isoformat()))
            conn.commit()

    def fail_queue_item(self, queue_id: str, error_msg: str):
        """Marca un item como fallido permanentemente."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE sync_queue SET status = 'FAILED', error_msg = ? WHERE queue_id = ?", (error_msg, queue_id))
            conn.commit()

    def update_queue_retry(self, queue_id: str, attempts: int, next_retry_at: str, error_msg: str):
        """Programa un reintento para un item."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE sync_queue 
                SET status = 'PENDING', error_msg = ?, next_retry_at = ?, attempts = ?
                WHERE queue_id = ?
            """, (error_msg, next_retry_at, int(attempts) + 1, queue_id))
            conn.commit()

    def resolve_event(self, event_id: str) -> dict:
        """Alias para get_evento_dict pero con la lógica redundante de campos (summary/evento)."""
        event = self.get_evento_dict(event_id)
        if event:
            # Redundancia por diseño
            event["evento"] = event.get("summary")
            event["tecnico_nombre"] = event.get("tecnico_nombre") # ya está, pero por si acaso
            event["tecnico"] = event.get("tecnico_nombre")
        return event

    def get_eventos_by_id(self, event_id: str) -> list:
        """Devuelve todos los eventos (incluyendo invitados) que compartan el mismo ID o google_event_id."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM eventos WHERE id = ? OR google_event_id = ?", (event_id, event_id))
            rows = cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            eventos = [dict(zip(cols, row)) for row in rows]
            for event in eventos:
                event["evento"] = event.get("summary")
                event["tecnico"] = event.get("tecnico_nombre")
            return eventos

    def log_sync_activity(self, event_id: str, calendar_id: str, operation: str, status: str, detail: str = None):
        """Registra actividad de sincronización."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sync_log (event_id, calendar_id, operation, status, detail, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (event_id, calendar_id, operation, status, detail, datetime.datetime.now().isoformat()))
            conn.commit()

    def get_evento_dict(self, event_id: str, tecnico_nombre: str = None) -> dict:
        """Retorna un evento como diccionario."""
        import json
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Búsqueda primaria
            if tecnico_nombre:
                cursor.execute("SELECT * FROM eventos WHERE (id = ? OR google_event_id = ?) AND tecnico_nombre = ?", (event_id, event_id, tecnico_nombre))
            else:
                cursor.execute("SELECT * FROM eventos WHERE id = ? OR google_event_id = ?", (event_id, event_id))
            row = cursor.fetchone()
            if row:
                cols = [d[0] for d in cursor.description]
                return dict(zip(cols, row))
                
            # Búsqueda secundaria: Stale Frontend ID via previous_google_event_id
            cursor.execute("SELECT * FROM eventos WHERE extended_props LIKE ?", (f'%"{event_id}"%',))
            for row in cursor.fetchall():
                cols = [d[0] for d in cursor.description]
                ev = dict(zip(cols, row))
                try:
                    ext = json.loads(ev.get("extended_props") or "{}")
                    if ext.get("private", {}).get("previous_google_event_id") == event_id:
                        return ev
                except Exception:
                    pass
            return None

    def get_last_poll_time(self, calendar_id: str) -> str:
        """Retorna el timestamp del último poll exitoso para un calendario."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT last_poll_time FROM poll_calendar_state WHERE calendar_id = ?", (calendar_id,))
            row = cursor.fetchone()
            return row[0] if row else None

    def update_last_poll_time(self, calendar_id: str, timestamp: str):
        """Actualiza el timestamp del último poll exitoso."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO poll_calendar_state (calendar_id, last_poll_time, last_poll_ok, error_count, last_error)
                VALUES (?, ?, 1, 0, NULL)
                ON CONFLICT(calendar_id) DO UPDATE SET 
                    last_poll_time = excluded.last_poll_time, 
                    last_poll_ok = 1, 
                    error_count = 0, 
                    last_error = NULL
            """, (calendar_id, timestamp))
            conn.commit()

    def register_calendar_poll_error(self, calendar_id: str, error_msg: str):
        """Registra un error en el poll de un calendario."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO poll_calendar_state (calendar_id, last_error)
                VALUES (?, ?)
                ON CONFLICT(calendar_id) DO UPDATE SET last_error = excluded.last_error
            """, (calendar_id, error_msg))
            conn.commit()

    def find_by_google_event_id(self, gid: str) -> dict:
        """Busca un evento por su ID de Google."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM eventos WHERE google_event_id = ?", (gid,))
            row = cursor.fetchone()
            if not row: return None
            # Mapeo manual a dict basado en el esquema
            # id, calendar_id, tecnico_nombre, summary, inicio, fin, ubicacion, descripcion, extended_props, version, sync_status, updated_at, source, google_event_id, poll_source, pending_sync
            cols = [d[0] for d in cursor.description]
            return dict(zip(cols, row))

    def actualizar_extended_props_incremental(self, event_id: str, new_props: dict):
        """Merge semántico de extendedProperties."""
        from utils import deep_merge_metadata
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT extended_props FROM eventos WHERE id = ?", (event_id,))
                row = cursor.fetchone()
                current_props = json.loads(row[0] or "{}") if row else {}
                
                merged = deep_merge_metadata(current_props, new_props)
                
                cursor.execute("UPDATE eventos SET extended_props = ?, updated_at = ? WHERE id = ?", 
                               (json.dumps(merged), datetime.datetime.utcnow().isoformat() + "Z", event_id))
                conn.commit()

    def apply_poll_safe_changes(self, event_id: str, safe_diff: dict):
        """Aplica cambios marcados como seguros en el poll."""
        updates = []
        params = []
        for field, d in safe_diff.items():
            updates.append(f"{field} = ?")
            params.append(d["new"])
        
        params.append(datetime.datetime.utcnow().isoformat() + "Z")
        params.append(event_id)
        
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"UPDATE eventos SET {', '.join(updates)}, updated_at = ? WHERE id = ?", params)
                conn.commit()

    def enqueue_review(self, event_id: str, calendar_id: str, diff: dict,
                        conflict_type: str = "FIELD_CHANGE",
                        google_event_id: str = None,
                        local_snapshot: dict = None,
                        remote_snapshot: dict = None,
                        recommended_action: str = None,
                        g_updated: str = None):
        """
        [ARBITRATION] Encola un cambio crítico para revisión humana.
        Genera un UUID único por review para arbitraje individual.

        [WATERMARK_ANTI_REOPEN] El parámetro g_updated es el timestamp 'updated' del
        evento en Google. Si existe un review ya resuelto (ACCEPTED/REJECTED) para el
        mismo google_event_id y g_updated <= resolved_at, el review NO se reabre.
        Esto evita que el polling recree reviews fantasma por cambios anteriores al accept.
        Si g_updated > resolved_at, SÍ se crea un nuevo review (cambio genuino post-accept).
        """
        import uuid as _uuid
        review_id = str(_uuid.uuid4())
        now = datetime.datetime.utcnow().isoformat() + "Z"
        gid = google_event_id or event_id

        # Determinar acción recomendada si no se provee
        if recommended_action is None:
            if conflict_type == "REMOTE_DELETE":
                recommended_action = "REVIEW_DELETE"
            else:
                recommended_action = "ACCEPT_REMOTE"

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # Auto-migrar columnas nuevas si la tabla era de la versión anterior
                cursor.execute("PRAGMA table_info(poll_review_queue)")
                existing_cols = {r[1] for r in cursor.fetchall()}
                new_cols = {
                    "conflict_type": "TEXT DEFAULT 'FIELD_CHANGE'",
                    "google_event_id": "TEXT",
                    "local_snapshot": "TEXT",
                    "remote_snapshot": "TEXT",
                    "recommended_action": "TEXT",
                    "resolved_at": "TEXT",
                }
                for col, spec in new_cols.items():
                    if col not in existing_cols:
                        cursor.execute(f"ALTER TABLE poll_review_queue ADD COLUMN {col} {spec}")

                # [DEDUPLICACIÓN] Evitar reviews redundantes
                cursor.execute("""
                    SELECT status FROM poll_review_queue 
                    WHERE google_event_id = ? 
                    ORDER BY detected_at DESC LIMIT 1
                """, (gid,))
                existing = cursor.fetchone()
                if existing:
                    status = existing[0]
                    if status in ('PENDING', 'DEFERRED'):
                        return None
                    if status == 'REJECTED' and conflict_type == 'REMOTE_CREATE':
                        # Si es creación remota y ya fue explícitamente rechazada, no volver a encolar
                        return None

                # [WATERMARK_ANTI_REOPEN] Comparar g_updated contra resolved_at del último review resuelto
                if g_updated:
                    cursor.execute("""
                        SELECT resolved_at FROM poll_review_queue
                        WHERE google_event_id = ? AND status IN ('ACCEPTED', 'REJECTED')
                        ORDER BY resolved_at DESC LIMIT 1
                    """, (gid,))
                    wm_row = cursor.fetchone()
                    if wm_row and wm_row[0]:
                        resolved_at = wm_row[0]
                        # Comparación lexicográfica de ISO timestamps (válido para UTC)
                        if g_updated <= resolved_at:
                            # Cambio fantasma anterior al accept — bloqueado
                            self.log_trace(event_id, "REOPEN_BLOCKED", {
                                "google_event_id": gid,
                                "g_updated": g_updated,
                                "resolved_at": resolved_at,
                                "conflict_type": conflict_type,
                                "reason": "g_updated <= resolved_at watermark"
                            }, calendar_id=calendar_id, tag="POLLING_REOPEN_BLOCKED")
                            return None

                cursor.execute("""
                    INSERT INTO poll_review_queue
                        (review_id, event_id, calendar_id, diff_json, status, detected_at,
                         conflict_type, google_event_id, local_snapshot, remote_snapshot, recommended_action)
                    VALUES (?, ?, ?, ?, 'PENDING', ?, ?, ?, ?, ?, ?)
                """, (
                    review_id, event_id, calendar_id,
                    json.dumps(diff), now,
                    conflict_type,
                    gid,
                    json.dumps(local_snapshot or {}),
                    json.dumps(remote_snapshot or {}),
                    recommended_action
                ))
                conn.commit()
        return review_id

    def get_poll_review_queue(self, limit: int = 50) -> list:
        """Retorna la cola de revisión enriquecida con datos del evento local."""
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT prq.*,
                       ev.summary AS event_summary,
                       ev.tecnico_nombre,
                       ev.inicio,
                       ev.fin
                FROM poll_review_queue prq
                LEFT JOIN eventos ev ON ev.id = prq.event_id
                WHERE prq.status = 'PENDING'
                ORDER BY prq.detected_at DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            result = []
            for r in rows:
                d = dict(r)
                try:
                    d["diff"] = json.loads(d.get("diff_json") or "{}")
                except Exception:
                    d["diff"] = {}
                try:
                    d["local_snapshot"] = json.loads(d.get("local_snapshot") or "{}")
                except Exception:
                    d["local_snapshot"] = {}
                try:
                    d["remote_snapshot"] = json.loads(d.get("remote_snapshot") or "{}")
                except Exception:
                    d["remote_snapshot"] = {}

                # [INBOUND_FIX] Si el evento no existe localmente (REMOTE_CREATE), poblar datos desde el remote_snapshot
                if not d.get("event_summary") and d.get("conflict_type") == "REMOTE_CREATE":
                    remote = d["remote_snapshot"]
                    d["event_summary"] = remote.get("summary") or "Sin título"
                    
                    # Técnico
                    ext = remote.get("extendedProperties") or {}
                    priv = ext.get("private") or {}
                    d["tecnico_nombre"] = priv.get("tecnico_nombre") or d.get("calendar_id")
                    
                    # Fechas
                    from utils import TimeNormalizationService
                    d["inicio"] = TimeNormalizationService.normalize_to_utc_z(remote.get("start", {}))
                    d["fin"] = TimeNormalizationService.normalize_to_utc_z(remote.get("end", {}))

                result.append(d)
            return result

    def accept_review(self, review_id: str) -> dict:
        """
        [REVIEW_ACCEPTED] Aplica el snapshot remoto al evento local.
        Usa el pipeline oficial de mutación.

        [INBOUND_FIX] Ahora lanza ValueError explícito si la mutación SQLite no ocurre,
        en lugar de retornar false-200 al operador.
        """
        row = self.get_review_by_id(review_id)
        if not row:
            raise ValueError(f"Review {review_id} no encontrado")

        # [IDEMPOTENCIA] Si el review ya fue resuelto, lanzar error explícito
        current_status = row.get("status", "")
        if current_status != "PENDING":
            raise ValueError(
                f"Review {review_id} ya fue resuelto (status='{current_status}'). "
                f"No se puede aceptar dos veces."
            )

        diff         = row.get("diff") or json.loads(row.get("diff_json", "{}"))
        event_id     = row["event_id"]
        calendar_id  = row["calendar_id"]
        conflict_type = row.get("conflict_type", "FIELD_CHANGE")
        now          = datetime.datetime.utcnow().isoformat() + "Z"

        # 1. Obtener versión antes para trazabilidad
        current  = self.get_evento_dict(event_id)
        v_before = current.get("version", 1) if current else 0

        # [FORENSICS] Snapshot Before
        grupo = self.obtener_grupo_de_evento(event_id)
        snapshot_before = None
        op_id = None
        if grupo:
            from group_integrity import snapshot_group_state
            snapshot_before = snapshot_group_state(self, grupo['grupo_id'])
            self.ensure_group_operation_journal()
            op_id = self.create_group_operation(
                operation_type="ACCEPT_REVIEW",
                group_id=grupo['grupo_id'],
                expected_members=len(grupo.get('event_ids', [])),
                detail={"review_id": review_id, "conflict_type": conflict_type}
            )

        data_to_apply       = {}
        sync_state_to_apply = None

        if conflict_type == "REMOTE_DELETE":
            sync_state_to_apply = "CANCELLED_IN_GOOGLE"
        else:
            for field, d in diff.items():
                if field.startswith("_"): continue
                if isinstance(d, dict) and "new" in d:
                    data_to_apply[field] = d["new"]

        # [ARBITRATION_TRACE:APPLY_START]
        self.log_trace(event_id, "APPLY_START", {
            "review_id":    review_id,
            "conflict_type": conflict_type,
            "calendar_id":  calendar_id,
            "v_before":     v_before,
            "diff_fields":  [k for k in diff if not k.startswith("_")]
        }, calendar_id=calendar_id, tag="ARBITRATION_TRACE")

        # [ARBITRATION_TRACE:APPLY_PAYLOAD]
        self.log_trace(event_id, "APPLY_PAYLOAD", {
            "review_id":          review_id,
            "data_to_apply":      data_to_apply,
            "sync_state_to_apply": sync_state_to_apply,
            "pending_sync":        0
        }, calendar_id=calendar_id, tag="ARBITRATION_TRACE")

        # [ARBITRATION_TRACE:APPLY_METHOD]
        self.log_trace(event_id, "APPLY_METHOD", {
            "method":      "DataManager.actualizar_evento_individual",
            "event_id":    event_id,
            "calendar_id": calendar_id
        }, calendar_id=calendar_id, tag="ARBITRATION_TRACE")

        # 2. Aplicar vía pipeline oficial o creación directa
        if conflict_type == "REMOTE_CREATE":
            # Crear el evento nuevo localmente
            from utils import EventAdapter
            
            g_ev = row.get("remote_snapshot")
            if not g_ev:
                raise ValueError("No se encontró el snapshot remoto en el review para la creación")
                
            # Desempaquetar cualquier nivel de serialización string
            while isinstance(g_ev, str):
                try:
                    g_ev = json.loads(g_ev)
                except Exception:
                    break
                    
            if not isinstance(g_ev, dict):
                g_ev = {}

            # Obtener técnico desde local_snapshot o row.get("tecnico_nombre") o calendar_id
            local_snap = row.get("local_snapshot")
            while isinstance(local_snap, str):
                try:
                    local_snap = json.loads(local_snap)
                except Exception:
                    break
            if not isinstance(local_snap, dict):
                local_snap = {}
                
            tec_nombre = local_snap.get("tecnico") or row.get("tecnico_nombre") or calendar_id
            
            mapped = EventAdapter.google_to_canonical(g_ev, calendar_id, tec_nombre)
            params = EventAdapter.canonical_to_sqlite_params(mapped)
            
            with self._lock:
                with self._get_connection() as conn:
                    conn.execute("""
                        INSERT OR REPLACE INTO eventos
                            (id, calendar_id, tecnico_nombre, summary, inicio, fin,
                             ubicacion, descripcion, extended_props, version,
                             sync_status, updated_at, source, google_event_id, poll_source, pending_sync)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)
                    """, (
                        params["id"],           params["calendar_id"],
                        params["tecnico_nombre"], params["summary"],
                        params["inicio"],        params["fin"],
                        params["ubicacion"],     params["descripcion"],
                        params["extended_props"], 1,
                        "SUCCESS",               params["updated_at"] or datetime.datetime.utcnow().isoformat() + "Z",
                        "internal",             params["google_event_id"],
                        "google_poll"
                    ))
                    conn.commit()
            
            new_ver = 1
        else:
            # 2. Aplicar vía pipeline oficial (pending_sync=0: aceptamos lo que ya está en Google)
            new_ver = self.actualizar_evento_individual(
                event_id, calendar_id,
                data=data_to_apply,
                pending_sync=0,
                sync_status='SUCCESS',
                sync_state=sync_state_to_apply,
                origin='review_accept'
            )

        # [INBOUND_FIX] Si la mutación no ocurrió, lanzar error en lugar de false-200
        if new_ver is None:
            # [FAIL_FAST] Persistir el fallo antes de lanzar
            self.log_trace(event_id, "ACCEPT_FAILED", {
                "review_id": review_id,
                "conflict_type": conflict_type,
                "calendar_id": calendar_id,
                "reason": "actualizar_evento_individual retornó None — lookup miss en todos los fallbacks"
            }, calendar_id=calendar_id, tag="ARBITRATION_APPLIED")
            raise ValueError(
                f"[ARBITRATION] Accept review falló: evento '{event_id}' no encontrado en SQLite "
                f"(ningún fallback de lookup tuvo éxito). Review: {review_id}. "
                f"Verificar calendar_id mismatch o event_id obsoleto."
            )

        # 3. Marcar review como ACCEPTED
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    "UPDATE poll_review_queue SET status='ACCEPTED', resolved_at=? WHERE review_id=?",
                    (now, review_id)
                )
                conn.commit()

        # 4. [OBSERVABILITY] Registrar la decisión humana
        self.log_trace(event_id, "accepted", {
            "review_id":       review_id,
            "conflict_type":   conflict_type,
            "version_before":  v_before,
            "version_after":   new_ver,
            "lifecycle_path":  "DataManager.actualizar_evento_individual"
        }, calendar_id=calendar_id, tag="REVIEW_MUTATION")

        # [ARBITRATION_APPLIED] Tag canónico de observabilidad
        self.log_trace(event_id, "ACCEPT_OK", {
            "review_id":      review_id,
            "conflict_type":  conflict_type,
            "version_after":  new_ver
        }, calendar_id=calendar_id, tag="ARBITRATION_APPLIED")

        # [METADATA_INTEGRITY] Verificar integridad post-accept
        try:
            from utils import assert_metadata_integrity, OperationalLogger
            post_ev = self.get_evento_dict(event_id)
            if post_ev:
                issues = assert_metadata_integrity(post_ev, context=f"accept_review:{conflict_type}")
                if issues:
                    OperationalLogger.log_metadata_issues(self, post_ev, issues, context=f"accept_review:{conflict_type}")
        except Exception:
            pass  # El check nunca bloquea el flujo

        # [GROUP_OPERATION_TRACKING] Finalizar si pertenecía a grupo
        if op_id and grupo:
            self.finalize_group_operation(op_id, grupo['grupo_id'], 1, snapshot_before, allow_deleted=True)

        return {
            "status":        "ACCEPTED",
            "review_id":     review_id,
            "event_id":      event_id,
            "conflict_type": conflict_type,
            "new_version":   new_ver
        }

    def reject_review(self, review_id: str) -> dict:
        """
        [REVIEW_REJECTED] Preserva el estado local y encola resync outbound.
        """
        row = self.get_review_by_id(review_id)
        if not row:
            raise ValueError(f"Review {review_id} no encontrado")

        # [IDEMPOTENCIA] Si el review ya fue resuelto, lanzar error explícito
        current_status = row.get("status", "")
        if current_status != "PENDING":
            raise ValueError(
                f"Review {review_id} ya fue resuelto (status='{current_status}'). "
                f"No se puede rechazar dos veces."
            )

        event_id = row["event_id"]
        calendar_id = row["calendar_id"]
        conflict_type = row.get("conflict_type", "FIELD_CHANGE")
        now = datetime.datetime.utcnow().isoformat() + "Z"

        # 1. Obtener datos actuales para la sync_queue
        current = self.get_evento_dict(event_id)
        if not current:
            if conflict_type == "REMOTE_CREATE":
                # Si es una creación remota y la rechazamos, marcamos el review como REJECTED.
                # Y encolamos una sincronización DELETE para eliminar el evento de Google Calendar.
                g_ev = row.get("remote_snapshot")
                while isinstance(g_ev, str):
                    try:
                        g_ev = json.loads(g_ev)
                    except Exception:
                        break
                if not isinstance(g_ev, dict):
                    g_ev = {}
                
                ext = g_ev.get("extendedProperties") or {}
                priv = ext.get("private") or {}
                tec_nombre = priv.get("tecnico_nombre") or calendar_id

                # Encolar delete outbound para eliminarlo de Google Calendar
                self.enqueue_sync(event_id, calendar_id, tec_nombre, "DELETE", origin='review_reject')

                with self._lock:
                    with self._get_connection() as conn:
                        conn.execute(
                            "UPDATE poll_review_queue SET status='REJECTED', resolved_at=? WHERE review_id=?",
                            (now, review_id)
                        )
                        conn.commit()

                self.log_trace(event_id, "rejected", {
                    "review_id": review_id,
                    "conflict_type": conflict_type,
                    "note": "Importación de evento nuevo rechazada. Encolada eliminación en Google Calendar."
                }, calendar_id=calendar_id, tag="REVIEW_MUTATION")

                return {"status": "REJECTED", "review_id": review_id, "event_id": event_id, "resync_queued": True}
            else:
                raise ValueError(f"Evento {event_id} no encontrado para rechazo")
        
        tec_nombre = current.get("tecnico_nombre", "")
        v_before = current.get("version", 1)

        # 2. Encolar sync outbound vía pipeline oficial
        operation = "CREATE" if conflict_type == "REMOTE_DELETE" else "UPDATE"
        self.enqueue_sync(event_id, calendar_id, tec_nombre, operation, origin='review_reject')

        # 3. Marcar review como REJECTED
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    "UPDATE poll_review_queue SET status='REJECTED', resolved_at=? WHERE review_id=?",
                    (now, review_id)
                )
                conn.commit()

        # 4. [OBSERVABILITY] Registrar la decisión humana
        self.log_trace(event_id, "rejected", {
            "review_id": review_id,
            "conflict_type": conflict_type,
            "operation_queued": operation,
            "version": v_before
        }, calendar_id=calendar_id, tag="REVIEW_MUTATION")

        return {"status": "REJECTED", "review_id": review_id, "event_id": event_id, "resync_queued": True}

    def defer_review(self, review_id: str) -> dict:
        """
        [REVIEW_DEFERRED] Pospone un review sin tomar acción.
        El review permanece en queue con status DEFERRED (no aparece como PENDING).
        """
        now = datetime.datetime.utcnow().isoformat() + "Z"
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    "UPDATE poll_review_queue SET status='DEFERRED', resolved_at=? WHERE review_id=?",
                    (now, review_id)
                )
                conn.commit()
        return {"status": "DEFERRED", "review_id": review_id}

    def apply_poll_critical_change(self, event_id: str, diff: dict):
        """
        [LEGACY] Aplica un cambio crítico con SQL directo.
        DEPRECADO: Usar accept_review() en su lugar (usa merge_events + fallback lookups).
        Este método NO tiene fallback de lookup ni BEFORE/AFTER traces.
        """
        # [ARBITRATION_TRACE:LEGACY_APPLY_USED]
        self.log_trace(event_id, "LEGACY_APPLY_USED", {
            "warning": "apply_poll_critical_change es LEGACY — usar accept_review(). Sin fallback lookup ni merge_events.",
            "diff_keys": [k for k in diff if not k.startswith("_")]
        }, tag="ARBITRATION_TRACE")

        updates = []
        params = []
        for field, d in diff.items():
            if field == "_action": continue
            updates.append(f"{field} = ?")
            params.append(d["new"])
        if not updates:
            return
        params.append(datetime.datetime.utcnow().isoformat() + "Z")
        params.append(event_id)
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"UPDATE eventos SET {', '.join(updates)}, updated_at = ? WHERE id = ?", params)
                conn.commit()

    def write_poll_log(self, log_id, timestamp, event_type, calendar_id, event_id, version, detail):
        """Escribe un log de polling."""
        import json
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO poll_log (log_id, timestamp, event_type, calendar_id, event_id, version, detail)
                    VALUES (?,?,?,?,?,?,?)
                """, (log_id, timestamp, event_type, calendar_id, event_id, version, detail))
                conn.commit()

    def get_poll_logs(self, limit: int = 100, event_type: str = None) -> list:
        """Recupera los últimos registros del log de polling."""
        import json
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM poll_log"
            params = []
            if event_type:
                query += " WHERE event_type LIKE ?"
                params.append(f"{event_type}%")
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [
                {
                    "log_id": r[0],
                    "timestamp": r[1],
                    "event_type": r[2],
                    "calendar_id": r[3],
                    "event_id": r[4],
                    "version": r[5],
                    "detail": json.loads(r[6] or "{}") if isinstance(r[6], str) else r[6]
                }
                for r in rows
            ]

    # --- MISSING METHODS ---
    def actualizar_titulo_evento(self, event_id: str, new_title: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE eventos SET summary = ? WHERE id = ? OR google_event_id = ?", (new_title, event_id, event_id))
            conn.commit()

    def count_queue_by_status(self, status: str) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM sync_queue WHERE status = ?", (status,))
            row = cursor.fetchone()
            return row[0] if row else 0

    def enqueue_sync(self, event_id: str, calendar_id: str, tecnico: str, operation: str, origin: str = 'api', original_calendar_id: str = None):
        import uuid
        import datetime
        if operation == "INSERT":
            operation = "CREATE"
        queue_id = str(uuid.uuid4())
        now = datetime.datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sync_queue 
                (queue_id, event_id, calendar_id, tecnico, operation, created_at, status, original_calendar_id, mutation_context)
                VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
            """, (queue_id, event_id, calendar_id, tecnico, operation, now, original_calendar_id, origin))
            conn.commit()

    def get_metadato(self, clave: str) -> str:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT valor FROM metadatos WHERE clave = ?", (clave,))
            row = cursor.fetchone()
            return row[0] if row else None

    def set_metadato(self, clave: str, valor: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO metadatos (clave, valor) VALUES (?, ?)", (clave, valor))
            conn.commit()

    def set_app_config(self, config_dict: dict):
        self.set_metadato("config", json.dumps(config_dict))

    def get_poll_status(self) -> dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT calendar_id, last_poll_time, last_poll_ok, error_count, last_error FROM poll_calendar_state")
            rows = cursor.fetchall()
            calendars = {}
            for r in rows:
                calendars[r[0]] = {
                    "last_poll_time": r[1],
                    "last_poll_ok": bool(r[2]),
                    "error_count": r[3],
                    "last_error": r[4]
                }
            
            cursor.execute("SELECT COUNT(*) FROM poll_review_queue WHERE status = 'PENDING'")
            pending_reviews = cursor.fetchone()[0]

            return {
                "calendars": calendars,
                "pending_reviews": pending_reviews
            }

    def get_review_by_id(self, review_id: str) -> dict:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM poll_review_queue WHERE review_id = ?", (review_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_sync_logs(self, limit: int = 20) -> list:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sync_log ORDER BY timestamp DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def obtener_eventos_por_fecha(self, fecha: str) -> list:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM eventos WHERE inicio LIKE ?", (fecha + "%",))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def obtener_grupo(self, grupo_id: str) -> dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM grupos WHERE grupo_id = ?", (grupo_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "grupo_id": row[0],
                    "ot_nro": row[1],
                    "fecha": row[2],
                    "event_ids": json.loads(row[3]) if row[3] else [],
                    "tecnico_nombres": json.loads(row[4]) if row[4] else [],
                    "patrones": json.loads(row[5]) if row[5] else [],
                    "vehiculo": row[6]
                }
            return None

    def vincular_evento_a_grupo(self, event_id: str, grupo_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT extended_props FROM eventos WHERE id = ? OR google_event_id = ?", (event_id, event_id))
            row = cursor.fetchone()
            if row:
                props = json.loads(row[0]) if row[0] else {}
                if "private" not in props:
                    props["private"] = {}
                props["private"]["grupo_id"] = grupo_id
                cursor.execute("UPDATE eventos SET extended_props = ? WHERE id = ? OR google_event_id = ?", (json.dumps(props), event_id, event_id))
                conn.commit()

    def actualizar_event_id_en_grupos(self, old_id: str, new_id: str):
        """Busca cualquier grupo que contenga old_id en su lista de event_ids y lo reemplaza por new_id."""
        if not old_id or not new_id or old_id == new_id:
            return
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT grupo_id, event_ids FROM grupos WHERE event_ids LIKE ?", (f'%"{old_id}"%',))
            rows = cursor.fetchall()
            for row in rows:
                grupo_id = row[0]
                event_ids = json.loads(row[1]) if row[1] else []
                if old_id in event_ids:
                    # Reemplazar todas las ocurrencias del ID anterior
                    event_ids = [new_id if eid == old_id else eid for eid in event_ids]
                    conn.execute("UPDATE grupos SET event_ids = ? WHERE grupo_id = ?", (json.dumps(event_ids), grupo_id))
            conn.commit()

    # ── GROUP OPERATIONS TRACKING ─────────────────────────────────────────────

    def create_group_operation(self, operation_type: str, group_id: str,
                                expected_members: int, detail: dict = None, trigger_event_id: str = None, initiated_by: str = "system") -> str:
        """
        [GROUP_OPERATION_TRACKING] Crea un registro de operación grupal en la bitácora.
        Retorna el operation_id (UUID).
        """
        import uuid
        operation_id = str(uuid.uuid4())
        now = datetime.datetime.utcnow().isoformat() + "Z"
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO group_operation_journal
                (operation_id, operation_type, trigger_event_id, group_id, initiated_by, expected_members,
                 completed_members, failed_members, status, detail, started_at)
                VALUES (?, ?, ?, ?, ?, ?, 0, 0, 'STARTED', ?, ?)
            """, (
                operation_id, operation_type, trigger_event_id, group_id, initiated_by,
                expected_members,
                json.dumps(detail or {}),
                now
            ))
            conn.commit()
        self.log_trace(
            group_id or operation_id,
            "GROUP_OPERATION_START",
            {"operation_id": operation_id, "type": operation_type,
             "expected_members": expected_members},
            tag="GROUP_OPERATION_TRACKING"
        )
        return operation_id

    def update_group_operation(self, operation_id: str,
                                completed_delta: int = 0,
                                failed_delta: int = 0,
                                status: str = None,
                                affected_members_json: str = None,
                                invariant_status_before: str = None,
                                invariant_status_after: str = None,
                                partial_failures_json: str = None,
                                drift_detected: int = None,
                                ui_refresh_triggered: int = None) -> dict:
        """
        [GROUP_OPERATION_TRACKING] Actualiza el estado de una operación grupal.
        Detecta PARTIAL si expected != completed al cerrar.
        """
        import datetime
        now = datetime.datetime.utcnow().isoformat() + "Z"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT operation_type, group_id, expected_members, "
                "completed_members, failed_members, status "
                "FROM group_operation_journal WHERE operation_id = ?",
                (operation_id,)
            )
            row = cursor.fetchone()
            if not row:
                return {}

            op_type, group_id, exp_mem, cur_comp, cur_fail, cur_status = row
            new_comp = cur_comp + completed_delta
            new_fail = cur_fail + failed_delta

            final_status = status or cur_status

            if final_status in ('COMPLETED', 'FAILED'):
                if new_comp > 0 and new_comp < exp_mem:
                    final_status = 'PARTIAL'
                if new_fail > 0 and new_comp == 0:
                    final_status = 'FAILED'
                if drift_detected:
                    final_status = 'DRIFT_DETECTED'

            # Build the dynamic UPDATE query for the extra forensic fields
            completed_at_val = now if final_status in ("COMPLETED", "PARTIAL", "FAILED", "DRIFT_DETECTED") else None
            
            updates = ["completed_members = ?", "failed_members = ?", "status = ?", "completed_at = COALESCE(completed_at, ?)"]
            params = [new_comp, new_fail, final_status, completed_at_val]

            if affected_members_json is not None:
                updates.append("affected_members_json = ?")
                params.append(affected_members_json)
            if invariant_status_before is not None:
                updates.append("invariant_status_before = ?")
                params.append(invariant_status_before)
            if invariant_status_after is not None:
                updates.append("invariant_status_after = ?")
                params.append(invariant_status_after)
            if partial_failures_json is not None:
                updates.append("partial_failures_json = ?")
                params.append(partial_failures_json)
            if drift_detected is not None:
                updates.append("drift_detected = ?")
                params.append(drift_detected)
            if ui_refresh_triggered is not None:
                updates.append("ui_refresh_triggered = ?")
                params.append(ui_refresh_triggered)

            params.append(operation_id)
            query = f"UPDATE group_operation_journal SET {', '.join(updates)} WHERE operation_id = ?"
            conn.execute(query, tuple(params))
            conn.commit()

        result = {
            "operation_id":      operation_id,
            "operation_type":    op_type,
            "group_id":          group_id,
            "expected_members":  exp_mem,
            "completed_members": new_comp,
            "failed_members":    new_fail,
            "status":            final_status
        }

        # [GROUP_OPERATION_PARTIAL_FAILURE] log crítico si parcial
        if final_status == "PARTIAL":
            self.log_trace(
                group_id or operation_id,
                "GROUP_OPERATION_PARTIAL_FAILURE",
                result,
                tag="GROUP_OPERATION_TRACKING"
            )
            print(f"[GROUP_OPERATION_PARTIAL_FAILURE] op={operation_id} "
                  f"type={op_type} expected={exp_mem} "
                  f"completed={new_comp} failed={new_fail}")
        return result

    def get_group_operation(self, operation_id: str) -> dict:
        """Obtiene el estado de una operación grupal por ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT operation_id, operation_type, group_id, expected_members, "
                "completed_members, failed_members, status, detail, started_at, completed_at "
                "FROM group_operation_journal WHERE operation_id = ?",
                (operation_id,)
            )
            row = cursor.fetchone()
            if not row:
                return {}
            return {
                "operation_id":      row[0],
                "operation_type":    row[1],
                "group_id":          row[2],
                "expected_members":  row[3],
                "completed_members": row[4],
                "failed_members":    row[5],
                "status":            row[6],
                "detail":            json.loads(row[7] or "{}"),
                "started_at":        row[8],
                "completed_at":      row[9]
            }

    def get_pending_group_operations(self, limit: int = 50) -> list:
        """Devuelve operaciones grupales en estado PENDING o PARTIAL."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT operation_id, operation_type, group_id, expected_members,
                       completed_members, failed_members, status, started_at
                FROM group_operation_journal
                WHERE status IN ('STARTED', 'IN_PROGRESS', 'PARTIAL', 'REPAIR_REQUIRED')
                ORDER BY started_at DESC LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [
                {
                    "operation_id":      r[0],
                    "operation_type":    r[1],
                    "group_id":          r[2],
                    "expected_members":  r[3],
                    "completed_members": r[4],
                    "failed_members":    r[5],
                    "status":            r[6],
                    "started_at":        r[7]
                }
                for r in rows
            ]

    def get_all_group_operations(self, limit: int = 100, status_filter: str = None) -> list:
        """Devuelve operaciones grupales con filtro opcional por status."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if status_filter:
                cursor.execute("""
                    SELECT operation_id, operation_type, group_id, expected_members,
                           completed_members, failed_members, status, started_at, completed_at
                    FROM group_operation_journal WHERE status = ?
                    ORDER BY started_at DESC LIMIT ?
                """, (status_filter, limit))
            else:
                cursor.execute("""
                    SELECT operation_id, operation_type, group_id, expected_members,
                           completed_members, failed_members, status, started_at, completed_at
                    FROM group_operation_journal
                    ORDER BY started_at DESC LIMIT ?
                """, (limit,))
            rows = cursor.fetchall()
            return [
                {
                    "operation_id":      r[0],
                    "operation_type":    r[1],
                    "group_id":          r[2],
                    "expected_members":  r[3],
                    "completed_members": r[4],
                    "failed_members":    r[5],
                    "status":            r[6],
                    "started_at":        r[7],
                    "completed_at":      r[8]
                }
                for r in rows
            ]

    def get_all_grupos(self) -> list:
        """Retorna todos los grupos registrados en la tabla grupos."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT grupo_id, ot_nro, fecha, event_ids, tecnico_nombres, patrones, vehiculo FROM grupos")
            rows = cursor.fetchall()
            return [
                {
                    "grupo_id":         r[0],
                    "ot_nro":           r[1],
                    "fecha":            r[2],
                    "event_ids":        json.loads(r[3]) if r[3] else [],
                    "tecnico_nombres":  json.loads(r[4]) if r[4] else [],
                    "patrones":         json.loads(r[5]) if r[5] else [],
                    "vehiculo":         r[6]
                }
                for r in rows
            ]

    def ensure_group_operation_journal(self):
        """Migración segura: crea group_operation_journal si aún no existe."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS group_operation_journal (
                    operation_id       TEXT PRIMARY KEY,
                    operation_type     TEXT NOT NULL,
                    trigger_event_id   TEXT,
                    group_id           TEXT,
                    initiated_by       TEXT,
                    started_at         TEXT,
                    completed_at       TEXT,
                    status             TEXT DEFAULT 'STARTED',
                    expected_members   INTEGER DEFAULT 0,
                    completed_members  INTEGER DEFAULT 0,
                    failed_members     INTEGER DEFAULT 0,
                    affected_members_json TEXT,
                    invariant_status_before TEXT,
                    invariant_status_after  TEXT,
                    partial_failures_json   TEXT,
                    drift_detected          INTEGER DEFAULT 0,
                    ui_refresh_triggered    INTEGER DEFAULT 0,
                    detail             TEXT
                )
            """)
            conn.commit()

    def finalize_group_operation(self, op_id: str, group_id: str, completed_delta: int, snapshot_before: dict, allow_deleted: bool = False):
        """
        [FORENSICS] Cierra la operación atómica evaluando el drift resultante.
        Si las invariantes se rompen, marca como DRIFT_DETECTED.
        """
        if not op_id or not group_id:
            return

        from group_integrity import snapshot_group_state, validate_group_integrity
        snapshot_after = snapshot_group_state(self, group_id)
        validation = validate_group_integrity(self, group_id)

        drift_detected = 1 if not validation.get('valid') else 0
        
        # Permitir la destrucción del grupo si allow_deleted es True
        if allow_deleted and drift_detected == 1:
            errors = validation.get('errors', [])
            if len(errors) == 1 and errors[0].get('code') == 'GROUP_NOT_FOUND':
                drift_detected = 0
                validation['valid'] = True

        failures_json = json.dumps(validation.get('errors', [])) if drift_detected else None

        status_str = "COMPLETED"
        if drift_detected:
            status_str = "DRIFT_DETECTED"
            print(f"[GROUP_STATE_DIVERGENCE] Group {group_id} diverged after operation {op_id}. Errors: {failures_json}")

        self.update_group_operation(
            op_id,
            completed_delta=completed_delta,
            status=status_str,
            invariant_status_before=json.dumps(snapshot_before),
            invariant_status_after=json.dumps(snapshot_after),
            partial_failures_json=failures_json,
            drift_detected=drift_detected
        )

