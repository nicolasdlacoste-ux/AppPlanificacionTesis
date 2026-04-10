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
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS eventos (
                    id TEXT PRIMARY KEY,
                    calendar_id TEXT,
                    tecnico_nombre TEXT,
                    summary TEXT,
                    inicio TEXT,
                    fin TEXT,
                    ubicacion TEXT,
                    descripcion TEXT,
                    extended_props TEXT,
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
