import sys
import re

def fix_autogroup():
    with open('api_server.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # 1. Eliminar la versi\u00f3n duplicada en la l\u00ednea 806
    # Buscamos por la firma exacta
    start_806 = -1
    end_806 = -1
    for i, line in enumerate(lines):
        if line.startswith('def _auto_agrupar_evento(event_id: str, calendar_id: str, tec_nombre: str, fecha_str: str, ots: list, svc_cal):'):
            start_806 = i
        if start_806 != -1 and i > start_806 and line.startswith('    else:'):
             # Buscar el final de ese bloque else
             for j in range(i+1, len(lines)):
                 if lines[j].startswith('@app.') or lines[j].startswith('def ') or lines[j].startswith('async def '):
                     end_806 = j
                     break
             break

    if start_806 != -1 and end_806 != -1:
        lines = lines[:start_806] + lines[end_806:]
        print(f"Removed duplicate _auto_agrupar_evento from lines {start_806} to {end_806}")

    content = "".join(lines)
    
    # 2. Agregar helper para t\u00edtulos locales (antes de _auto_agrupar_evento async)
    helper_code = '''
async def actualizar_titulos_grupo_local(grupo_id: str):
    """Actualiza los t\u00edtulos de todos los eventos del grupo en SQLite con el tag de iniciales."""
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
        # Limpiar tag previo
        clean_title = re.sub(r'\\s*-\\s*[A-Z0-9/]+\\s*$', '', titulo_orig).strip()
        new_title = f"{clean_title} - {tag}" if tag else clean_title
        
        if new_title != titulo_orig:
            db.actualizar_titulo_evento(eid, new_title)
'''
    content = content.replace('async def _auto_agrupar_evento(event_id, cal_id, tec_nombre, fecha, ots, svc_cal):', 
                              helper_code + '\nasync def _auto_agrupar_evento(event_id, cal_id, tec_nombre, fecha, ots, svc_cal=None):')

    with open('api_server.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed auto-grouping structure.")

fix_autogroup()
