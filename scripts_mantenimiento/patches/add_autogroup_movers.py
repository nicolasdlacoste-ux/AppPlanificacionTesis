import re

def add_autogroup_to_movers():
    with open('api_server.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. En mover_evento
    pattern_mover = r'(db\.update_last_sync\(\))\s+return \{\s+"status": "ok",\s+"event_id": event_id,\s+"version": new_version\s+\}'
    def sub_mover(m):
        return m.group(1) + '''
        # Auto-agrupaci\u00f3n local
        ots_actuales = list(utils.extraer_ots(nuevo_titulo))
        if ots_actuales:
            await _auto_agrupar_evento(event_id, target_cal, tec_nombre, params.nueva_fecha, ots_actuales)

        return {
            "status": "ok",
            "event_id": event_id,
            "version": new_version
        }'''
    
    content = re.sub(pattern_mover, sub_mover, content)

    # 2. En mover_grupo
    pattern_grupo = r'(return \{"status": "ok", "moved": len\(grupo\[\'event_ids\'\]\)\})'
    def sub_grupo(m):
        return '''# Auto-agrupaci\u00f3n local (para el grupo movido)
        ots_actuales = list(utils.extraer_ots(nuevo_titulo))
        if ots_actuales:
            await _auto_agrupar_evento(event_id, cal_target, tec_nombre, params.nueva_fecha, ots_actuales)

        ''' + m.group(1)

    content = re.sub(pattern_grupo, sub_grupo, content)

    with open('api_server.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Auto-grouping calls added to specific mover endpoints.")

add_autogroup_to_movers()
