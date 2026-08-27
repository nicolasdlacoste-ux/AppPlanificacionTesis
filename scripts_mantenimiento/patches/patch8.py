import os
import re

text = open('api_server.py', encoding='utf-8').read()

func = '''
async def actualizar_titulos_grupo_local(grupo_id: str):
    import re
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
        titulo_orig = ev.get('Evento', '')
        clean_title = re.sub(r'\\s*-\\s*[A-Z0-9/]+\\s*$', '', titulo_orig).strip()
        new_title = f"{clean_title} - {tag}" if tag else clean_title
        if new_title != titulo_orig:
            db.actualizar_titulo_evento(eid, new_title)

async def _auto_agrupar_evento'''

if 'def actualizar_titulos_grupo_local' not in text:
    text = text.replace('async def _auto_agrupar_evento', func)
    open('api_server.py', 'w', encoding='utf-8').write(text)
    print("Patched successfully")
else:
    print("Already patched")
