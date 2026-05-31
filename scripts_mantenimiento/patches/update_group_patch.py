
import sys
import re

with open("api_server.py", "r", encoding="utf-8") as f:
    js = f.read()

target = """async def actualizar_titulos_grupo_local(grupo_id: str):
    \"\"\"Actualiza los títulos de todos los eventos del grupo en SQLite con el tag de iniciales.\"\"\"
    grupo = db.obtener_grupo(grupo_id)
    if not grupo: return
    
    tecnicos = db.obtener_tecnicos()
    map_nombre_init = {t['nombre']: t['iniciales'] for t in tecnicos}
    
    inits = []
    for n in grupo['tecnico_nombres']:
        if n in map_nombre_init: inits.append(map_nombre_init[n])
    tag = "/".join(sorted(list(set(inits)))) if len(inits) > 1 else ""
    
    eventos_dict = db.obtener_eventos_dict()
    map_id_ev = {e['id']: e for e in eventos_dict}
    
    for eid in grupo['event_ids']:
        ev = map_id_ev.get(eid)
        if not ev: continue
        
        titulo_orig = ev.get('evento', '')
        # Limpiar tag previo
        clean_title = re.sub(r'\s*-\s*[A-Z0-9/]+\s*$', '', titulo_orig).strip()
        new_title = f"{clean_title} - {tag}" if tag else clean_title
        
        if new_title != titulo_orig:
            db.actualizar_titulo_evento(eid, new_title)
            
            # [OUTBOUND_MUTATION] mutation_created (Group Title Update)
            db.log_trace(eid, "mutation_created", {
                "type": "UPDATE",
                "origin": "group_title_auto_update",
                "new_title": new_title
            }, calendar_id=ev.get('calendar_id'), tag="OUTBOUND_MUTATION")
            
            # Enqueue sync para que el worker lo propague a Google
            db.enqueue_sync(eid, ev.get('calendar_id'), ev.get('tecnico_nombre'), "UPDATE")"""

replacement = """async def update_group_title(grupo_id: str):
    \"\"\"Actualiza los títulos y metadatos derivados de todos los eventos del grupo.\"\"\"
    grupo = db.obtener_grupo(grupo_id)
    if not grupo: return
    
    tecnicos = db.obtener_tecnicos()
    map_nombre_init = {t['nombre']: t['iniciales'] for t in tecnicos}
    
    inits = []
    for n in grupo['tecnico_nombres']:
        if n in map_nombre_init: inits.append(map_nombre_init[n])
    tag = "/".join(sorted(list(set(inits)))) if len(inits) > 1 else ""
    
    eventos_dict = db.obtener_eventos_dict()
    map_id_ev = {e['id']: e for e in eventos_dict}
    
    # 1. Unificar metadata derivada de todos los miembros
    all_ots = set()
    all_pats = set()
    vehiculo_lider = None
    
    for eid in grupo['event_ids']:
        ev = map_id_ev.get(eid)
        if not ev: continue
        
        ext = ev.get('extendedProperties', {})
        priv = ext.get('private', {}) if isinstance(ext, dict) else {}
        
        # Extraer OTs
        ev_ots = priv.get('app_ots', "[]")
        if isinstance(ev_ots, str):
            import json
            try: ev_ots = json.loads(ev_ots)
            except: ev_ots = []
        if isinstance(ev_ots, list):
            for o in ev_ots: all_ots.add(o)
            
        # Extraer Patrones
        ev_pats = priv.get('app_patrones', "[]")
        if isinstance(ev_pats, str):
            import json
            try: ev_pats = json.loads(ev_pats)
            except: ev_pats = []
        if isinstance(ev_pats, list):
            for p in ev_pats: all_pats.add(p)
            
        # Vehiculo
        if priv.get('app_vehiculo') and not vehiculo_lider:
            vehiculo_lider = priv.get('app_vehiculo')
            
    # 2. Actualizar cada evento del grupo
    import json
    for eid in grupo['event_ids']:
        ev = map_id_ev.get(eid)
        if not ev: continue
        
        titulo_orig = ev.get('evento', '')
        # Limpiar tag previo
        clean_title = re.sub(r'\s*-\s*[A-Z0-9/]+\s*$', '', titulo_orig).strip()
        new_title = f"{clean_title} - {tag}" if tag else clean_title
        
        # Merge de properties
        ext = ev.get('extendedProperties') or {}
        priv = ext.get('private') or {}
        
        priv['app_ots'] = json.dumps(list(all_ots))
        priv['app_patrones'] = json.dumps(list(all_pats))
        if vehiculo_lider:
            priv['app_vehiculo'] = vehiculo_lider
        
        ext['private'] = priv
        
        import copy
        ev_copy = copy.deepcopy(ev)
        ev_copy['evento'] = new_title
        ev_copy['extendedProperties'] = ext
        ev_copy['sync_status'] = 'PENDING'
        ev_copy['pending_sync'] = 1
        
        db.guardar_evento_individual(ev_copy)
            
        db.log_trace(eid, "mutation_created", {
            "type": "UPDATE",
            "origin": "update_group_title",
            "new_title": new_title
        }, calendar_id=ev.get('calendar_id'), tag="OUTBOUND_MUTATION")
        
        db.enqueue_sync(eid, ev.get('calendar_id'), ev.get('tecnico_nombre'), "UPDATE")

# Alias por compatibilidad
async def actualizar_titulos_grupo_local(grupo_id: str):
    await update_group_title(grupo_id)"""

if target in js:
    js = js.replace(target, replacement)
    
    # Check for mover_evento or similar where we must call it
    # We should ensure mover_grupo calls it.
    with open("api_server.py", "w", encoding="utf-8") as f:
        f.write(js)
    print("update_group_title implemented")
else:
    print("actualizar_titulos_grupo_local not found")

