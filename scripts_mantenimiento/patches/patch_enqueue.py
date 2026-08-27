import os

text = open('api_server.py', encoding='utf-8').read()

old_str = '''        db.guardar_evento_individual(event_obj)
        db.log_trace(event_id, "mutation_created", {"title": params.titulo}, params.correo_tecnico, "EVENT_CREATE")
        eventos_creados.append(event_obj)
        ids_creados.append(event_id)

        if params.ots and len(params.ots) > 0:
            for ev_id in ids_creados:
                await _auto_agrupar_evento(ev_id, params.correo_tecnico, tec_nombre, str(fecha_inicio_dt), params.ots)

        return {"status": "ok", "ids": ids_creados, "count": len(ids_creados)}'''

new_str = '''        # Primero normalizamos y convertimos el diccionario para que tenga el sync_status y pending_sync correctos
        from utils import EventAdapter, _now_iso
        can = EventAdapter.normalize_event(event_obj)
        params_db = EventAdapter.canonical_to_sqlite_params(can)
        
        # Guardar en SQLite (usando el método seguro)
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO eventos 
                (id, google_event_id, calendar_id, tecnico_nombre, summary, inicio, fin, ubicacion, descripcion, extended_props, version, updated_at, source, sync_status, pending_sync)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                params_db["id"], params_db["google_event_id"], params_db["calendar_id"], params_db["tecnico_nombre"],
                params_db["summary"], params_db["inicio"], params_db["fin"], params_db["ubicacion"], params_db["descripcion"],
                params_db["extended_props"], params_db["version"], params_db.get("updated_at") or _now_iso(), 
                params_db.get("source", "internal"), "PENDING", 1
            ))
            conn.commit()

        db.enqueue_sync(event_id, params.correo_tecnico, tec_nombre, "CREATE")
        db.update_last_sync()

        db.log_trace(event_id, "mutation_created", {"title": params.titulo}, params.correo_tecnico, "EVENT_CREATE")
        eventos_creados.append(event_obj)
        ids_creados.append(event_id)

        if params.ots and len(params.ots) > 0:
            for ev_id in ids_creados:
                await _auto_agrupar_evento(ev_id, params.correo_tecnico, tec_nombre, str(fecha_inicio_dt), params.ots)

        return {"status": "ok", "ids": ids_creados, "count": len(ids_creados)}'''

if old_str in text:
    text = text.replace(old_str, new_str)
    open('api_server.py', 'w', encoding='utf-8').write(text)
    print("Patched api_server.py successfully")
else:
    print("Could not find the block to replace!")
