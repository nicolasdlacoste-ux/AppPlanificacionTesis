import os

with open('poll_manager.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Fix line 461 usage
text = text.replace(
    'local = self.db.find_by_google_event_id(gid)',
    'local = self.db.find_by_google_event_id(gid, calendar_id)'
)

# 2. Fix line 882 usage in _handle_cancelled
text = text.replace(
    'local = self.db.find_by_google_event_id(event_id)',
    'local = self.db.find_by_google_event_id(event_id, calendar_id)'
)

# 3. Fix _create_from_google to check existence per calendar_id
target_create = """        mapped = _map_google_to_local(g_ev, calendar_id, tec_nombre)
        with self.db._lock:
            with self.db._get_connection() as conn:
                conn.execute(\"\"\"
                    INSERT OR IGNORE INTO eventos
                        (id, calendar_id, tecnico_nombre, summary, inicio, fin,
                         ubicacion, descripcion, extended_props, version,
                         sync_status, updated_at, source, google_event_id, poll_source, pending_sync)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)
                \"\"\", (
                    mapped["id"],           mapped["calendar_id"],
                    mapped["tecnico_nombre"], mapped["summary"],
                    mapped["inicio"],        mapped["fin"],
                    mapped["ubicacion"],     mapped["descripcion"],
                    mapped["extended_props"], 1,
                    "SUCCESS",               mapped["updated_at"],
                    "internal",             mapped["google_event_id"],
                    "google_poll"
                ))
                conn.commit()"""

replace_create = """        local = self.db.find_by_google_event_id(g_ev.get("id"), calendar_id)
        if not local:
            mapped = _map_google_to_local(g_ev, calendar_id, tec_nombre)
            with self.db._lock:
                with self.db._get_connection() as conn:
                    conn.execute(\"\"\"
                        INSERT OR IGNORE INTO eventos
                            (id, calendar_id, tecnico_nombre, summary, inicio, fin,
                             ubicacion, descripcion, extended_props, version,
                             sync_status, updated_at, source, google_event_id, poll_source, pending_sync)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)
                    \"\"\", (
                        mapped["id"],           mapped["calendar_id"],
                        mapped["tecnico_nombre"], mapped["summary"],
                        mapped["inicio"],        mapped["fin"],
                        mapped["ubicacion"],     mapped["descripcion"],
                        mapped["extended_props"], 1,
                        "SUCCESS",               mapped["updated_at"],
                        "internal",             mapped["google_event_id"],
                        "google_poll"
                    ))
                    conn.commit()"""

text = text.replace(target_create, replace_create)

with open('poll_manager.py', 'w', encoding='utf-8') as f:
    f.write(text)

print("Patch applied to poll_manager.py successfully.")
