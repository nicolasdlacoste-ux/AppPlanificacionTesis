# coding=utf-8
import sys
import re

with open("api_server.py", "r", encoding="utf-8") as f:
    js = f.read()

changes = 0

# 1. agregar_tecnico_a_grupo
target1 = """        if grupo:
            new_ids = list(grupo['event_ids']) + [new_ev_id]
            new_nombres = list(grupo['tecnico_nombres']) + [nuevo_nombre]
            db.crear_o_actualizar_grupo({**grupo, "event_ids": new_ids, "tecnico_nombres": new_nombres})
            
            # Vincular el evento del técnico agregado al grupo
            db.vincular_evento_a_grupo(new_ev_id, grupo['grupo_id'])"""
            
replacement1 = """        if grupo:
            new_ids = list(grupo['event_ids']) + [new_ev_id]
            new_nombres = list(grupo['tecnico_nombres']) + [nuevo_nombre]
            db.crear_o_actualizar_grupo({**grupo, "event_ids": new_ids, "tecnico_nombres": new_nombres})
            
            # Vincular el evento del técnico agregado al grupo
            db.vincular_evento_a_grupo(new_ev_id, grupo['grupo_id'])
            await update_group_title(grupo['grupo_id'])"""

if target1 in js:
    js = js.replace(target1, replacement1)
    changes += 1

# 2. individualizar_evento
target2 = """            db.crear_o_actualizar_grupo({
                **grupo, "event_ids": remaining_ids, "tecnico_nombres": remaining_names
            })"""

replacement2 = """            db.crear_o_actualizar_grupo({
                **grupo, "event_ids": remaining_ids, "tecnico_nombres": remaining_names
            })
            await update_group_title(grupo['grupo_id'])"""

if target2 in js:
    js = js.replace(target2, replacement2)
    changes += 1

# 3. eliminar_grupo_completo
target3 = """            db.eliminar_grupo(grupo_id)
        
        return {"status": "ok"}"""

replacement3 = """            db.eliminar_grupo(grupo_id)
            
            # Remove title tags for remaining individual events
            for eid in event_ids:
                ev = db.resolve_event(eid)
                if ev:
                    import re
                    titulo_orig = ev.get('evento', '')
                    clean_title = re.sub(r'\s*-\s*[A-Z0-9/]+\s*$', '', titulo_orig).strip()
                    if clean_title != titulo_orig:
                        db.actualizar_titulo_evento(eid, clean_title)
                        db.enqueue_sync(eid, ev.get('calendar_id'), ev.get('tecnico_nombre'), "UPDATE")
        
        return {"status": "ok"}"""

if target3 in js:
    js = js.replace(target3, replacement3)
    changes += 1

# 4. _eliminar_evento_logico (where it removes from group)
target4 = """            db.crear_o_actualizar_grupo({
                **grupo,
                "event_ids": n_ids,
                "tecnico_nombres": n_nombres
            })"""

replacement4 = """            db.crear_o_actualizar_grupo({
                **grupo,
                "event_ids": n_ids,
                "tecnico_nombres": n_nombres
            })
            await update_group_title(grupo['grupo_id'])"""

if target4 in js:
    js = js.replace(target4, replacement4)
    changes += 1

with open("api_server.py", "w", encoding="utf-8") as f:
    f.write(js)
    
print(f"Patched {changes} locations")

