
import sys

with open("api_server.py", "r", encoding="utf-8") as f:
    js = f.read()

changes = 0

validation_snippet = """    if _is_complex_event(ev_interno):
        raise HTTPException(400, "Eventos complejos (multidia o con invitados) estan bloqueados para edicion directa. Deben ser individualizados primero.")
"""

# 1. mover_evento
target1 = """    ev_interno = db.resolve_event(event_id)
    if not ev_interno:
        raise HTTPException(404, f"Evento {event_id} no encontrado")
    
    # Normalizar IDs"""

replacement1 = """    ev_interno = db.resolve_event(event_id)
    if not ev_interno:
        raise HTTPException(404, f"Evento {event_id} no encontrado")
    if _is_complex_event(ev_interno):
        raise HTTPException(400, "Eventos complejos (multidia o con invitados) estan bloqueados para edicion directa. Deben ser individualizados primero.")
        
    # Normalizar IDs"""

if target1 in js:
    js = js.replace(target1, replacement1)
    changes += 1

# 2. mover_grupo
target2 = """    ev_interno = db.resolve_event(event_id)
    if not ev_interno:
        raise HTTPException(404, f"Evento {event_id} no encontrado")
    
    # Normalizar IDs"""

if target2 in js:
    js = js.replace(target2, replacement1) # same replacement
    changes += 1

# 3. reasignar_tecnico_grupo
target3 = """    ev_interno = db.resolve_event(event_id)
    if not ev_interno:
        raise HTTPException(404, f"Evento {event_id} no encontrado")

    if params.base_version is not None:"""

replacement3 = """    ev_interno = db.resolve_event(event_id)
    if not ev_interno:
        raise HTTPException(404, f"Evento {event_id} no encontrado")
    if _is_complex_event(ev_interno):
        raise HTTPException(400, "Eventos complejos (multidia o con invitados) estan bloqueados para edicion directa. Deben ser individualizados primero.")

    if params.base_version is not None:"""

if target3 in js:
    js = js.replace(target3, replacement3)
    changes += 1

# 4. editar_batch
target4 = """        ev_interno = db.resolve_event(eid)
        if not ev_interno:
            continue"""

replacement4 = """        ev_interno = db.resolve_event(eid)
        if not ev_interno:
            continue
        if _is_complex_event(ev_interno):
            raise HTTPException(400, f"El evento {eid} es complejo (multidia o con invitados) y esta bloqueado para edicion. Individualice primero.")"""

if target4 in js:
    js = js.replace(target4, replacement4)
    changes += 1

with open("api_server.py", "w", encoding="utf-8") as f:
    f.write(js)
    
print(f"Patched {changes} locations")

