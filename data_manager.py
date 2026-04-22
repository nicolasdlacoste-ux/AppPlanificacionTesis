import sqlite3
import json
import os
import datetime
from pathlib import Path
import utils

class DataManager:
    def __init__(self, db_path="planificacion.db"):
        self.db_path = db_path
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
            # Primary key compuesta para permitir el mismo ID en calendarios de distintos técnicos
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS eventos (
                    id TEXT,
                    calendar_id TEXT,
                    tecnico_nombre TEXT,
                    summary TEXT,
                    inicio TEXT,
                    fin TEXT,
                    ubicacion TEXT,
                    descripcion TEXT,
                    extended_props TEXT,
                    PRIMARY KEY (id, tecnico_nombre),
                    FOREIGN KEY (tecnico_nombre) REFERENCES tecnicos (nombre)
                )
            ''')
            
            # Verificación de migración (si la tabla existía con ID como PK única)
            cursor.execute("PRAGMA table_info(eventos)")
            columns = cursor.fetchall()
            pk_cols = [c[1] for c in columns if c[5] > 0]
            if len(pk_cols) == 1 and pk_cols[0] == 'id':
                print("Detectada PK antigua. Recreando tabla eventos para soporte multi-técnico...")
                cursor.execute("DROP TABLE eventos")
                cursor.execute('''
                    CREATE TABLE eventos (
                        id TEXT,
                        calendar_id TEXT,
                        tecnico_nombre TEXT,
                        summary TEXT,
                        inicio TEXT,
                        fin TEXT,
                        ubicacion TEXT,
                        descripcion TEXT,
                        extended_props TEXT,
                        PRIMARY KEY (id, tecnico_nombre),
                        FOREIGN KEY (tecnico_nombre) REFERENCES tecnicos (nombre)
                    )
                ''')
            
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

    def actualizar_evento_individual(self, event_id, calendar_id, data):
        """Actualiza un solo evento en la tabla local tras una edición exitosa en la nube."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            props_str = json.dumps(data.get('extendedProperties', {}))
            cursor.execute('''
                UPDATE eventos 
                SET tecnico_nombre = ?, summary = ?, inicio = ?, fin = ?, descripcion = ?, extended_props = ?, calendar_id = ?
                WHERE id = ? AND calendar_id = ?
            ''', (data.get('Técnico'), data.get('Evento'), data.get('Inicio'), data.get('Fin'), 
                  data.get('Descripción'), props_str, calendar_id, event_id, calendar_id))
            conn.commit()

    def guardar_evento_individual(self, event_data):
        """Inserta o actualiza un único evento en la tabla eventos (sin borrar los demás)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            props = json.dumps(event_data.get('extendedProperties', {}))
            cursor.execute('''
                INSERT OR REPLACE INTO eventos 
                (id, calendar_id, tecnico_nombre, summary, inicio, fin, ubicacion, descripcion, extended_props)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                event_data.get('id'),
                event_data.get('calendar_id'),
                event_data.get('tecnico_nombre'),
                event_data.get('summary'),
                event_data.get('inicio'),
                event_data.get('fin'),
                event_data.get('ubicacion', ''),
                event_data.get('descripcion', ''),
                props
            ))
            conn.commit()

    def eliminar_evento_individual(self, event_id):
        """Elimina un único evento de la tabla local por su ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM eventos WHERE id = ?", (event_id,))
            conn.commit()

    def obtener_eventos_dict(self):
        """Retorna los eventos en el formato original de la app (lista de dicts)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM eventos")
            rows = cursor.fetchall()
            eventos = []
            for r in rows:
                eventos.append({
                    "id": r[0],
                    "calendar_id": r[1],
                    "Técnico": r[2],
                    "Evento": r[3],
                    "Inicio": r[4],
                    "Fin": r[5],
                    "Ubicación": r[6],
                    "Descripción": r[7],
                    "extendedProperties": json.loads(r[8]) if r[8] else {}
                })
            return eventos

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
        """Inserta o actualiza un grupo."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO grupos 
                (grupo_id, ot_nro, fecha, event_ids, tecnico_nombres, patrones, vehiculo)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                grupo_data.get('grupo_id'),
                grupo_data.get('ot_nro'),
                grupo_data.get('fecha'),
                json.dumps(grupo_data.get('event_ids', [])),
                json.dumps(grupo_data.get('tecnico_nombres', [])),
                json.dumps(grupo_data.get('patrones', [])),
                grupo_data.get('vehiculo')
            ))
            conn.commit()

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
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM grupos WHERE grupo_id = ?", (grupo_id,))
            conn.commit()
