import sys
import re

def update_autogroup_logic():
    with open('api_server.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Reemplazar la l\u00f3gica interna de _auto_agrupar_evento para que sea local-first
    old_logic_pattern = r'async def _auto_agrupar_evento\(event_id, cal_id, tec_nombre, fecha, ots, svc_cal=None\):.*?await sync_group_events\(new_gid, svc_cal=svc_cal\)'
    
    new_logic = '''async def _auto_agrupar_evento(event_id, cal_id, tec_nombre, fecha, ots, svc_cal=None):
    """
    Busca otros eventos en el mismo d\u00eda con la misma OT para formar un grupo autom\u00e1ticamente.
    Prioriza la consistencia en SQLite y evita llamadas innecesarias a Google.
    """
    if not ots: return
    
    # 1. Buscar eventos en SQLite para ese d\u00eda con alguna de esas OTs
    candidatos = []
    eventos_dia = db.obtener_eventos_por_fecha(fecha)
    
    for ev in eventos_dia:
        if ev['id'] == event_id: continue
        ev_ots = list(utils.extraer_ots(ev['summary'] or ev['Evento']))
        if any(ot in ev_ots for ot in ots):
            candidatos.append(ev)
    
    if not candidatos: return
    
    # 2. Decidir si unirse a un grupo existente o crear uno nuevo
    target_grupo_id = None
    for c in candidatos:
        props = c.get('extendedProperties', {})
        gid = props.get('private', {}).get('grupo_id')
        if gid:
            target_grupo_id = gid
            break
            
    if target_grupo_id:
        # Unirse a grupo existente
        grupo = db.obtener_grupo(target_grupo_id)
        if grupo:
            if event_id not in grupo['event_ids']:
                grupo['event_ids'].append(event_id)
                grupo['tecnico_nombres'].append(tec_nombre)
                db.crear_o_actualizar_grupo(grupo)
                
                # Actualizar metadatos del evento reci\u00e9n unido para que tenga el grupo_id
                db.vincular_evento_a_grupo(event_id, target_grupo_id)
                
                await actualizar_titulos_grupo_local(target_grupo_id)
                # Opcional: sync_group_events en background si svc_cal est\u00e1
    else:
        # Crear grupo nuevo con el primero que encontramos
        c = candidatos[0]
        c_id = c['id']
        c_tec = c.get('tecnico_nombre') or c.get('T\u00e9cnico')
        
        new_gid = str(uuid.uuid4())
        db.crear_o_actualizar_grupo({
            "grupo_id": new_gid,
            "ot_nro": ots[0],
            "fecha": fecha,
            "event_ids": [c_id, event_id],
            "tecnico_nombres": [c_tec, tec_nombre],
            "vehiculo": c.get("app_vehiculo", ""),
            "patrones": []
        })
        
        # Vincular ambos eventos en SQLite (guarda el grupo_id en sus extendedProperties)
        db.vincular_evento_a_grupo(c_id, new_gid)
        db.vincular_evento_a_grupo(event_id, new_gid)
        
        await actualizar_titulos_grupo_local(new_gid)'''

    content = re.sub(old_logic_pattern, new_logic, content, flags=re.DOTALL)

    # 3. Insertar llamada en mover_evento
    # Antes del return en mover_evento
    call_group_logic = '''
        # Auto-agrupaci\u00f3n si coincide con otra OT en el mismo d\u00eda
        ots_actuales = list(utils.extraer_ots(nuevo_titulo))
        if ots_actuales:
            await _auto_agrupar_evento(event_id, target_cal, tec_nombre, params.nueva_fecha, ots_actuales)

        return {'''
    content = content.replace('        return {', call_group_logic)

    # 4. Insertar llamada en crear_evento
    # Reactivar la llamada comentada
    content = content.replace('# _auto_agrupar_evento_local(event_id, params.correo_tecnico, tec_nombre, params.fecha, params.ots)',
                              'await _auto_agrupar_evento(event_id, params.correo_tecnico, tec_nombre, params.fecha, params.ots)')

    with open('api_server.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Auto-grouping logic updated and integrated.")

update_autogroup_logic()
