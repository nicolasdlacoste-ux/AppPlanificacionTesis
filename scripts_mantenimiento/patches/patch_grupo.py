import sys
import re

def patch_mover_grupo():
    with open('api_server.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Buscar el inicio del bucle for en mover_grupo
    # Queremos insertar la l\u00f3gica de metadatos dentro del bucle
    
    old_code = r'''                if params.titulo is not None:
                    body["summary"] = params.titulo

                new_id = eid'''
    
    new_code = r'''                if params.titulo is not None:
                    body["summary"] = params.titulo
                
                # --- Actualizaci\u00f3n de metadatos en grupo ---
                metadata = ev_act.get('extendedProperties', {}).get('private', {}).copy()
                meta_changed = False
                if params.ots is not None:
                    metadata["app_ots"] = json.dumps(params.ots); meta_changed = True
                if params.patrones is not None:
                    metadata["app_patrones"] = json.dumps(params.patrones); meta_changed = True
                if params.vehiculo is not None:
                    metadata["app_vehiculo"] = params.vehiculo; meta_changed = True
                if params.requiere_vehiculo is not None:
                    metadata["app_requiere_vehiculo"] = str(params.requiere_vehiculo).lower(); meta_changed = True
                
                if meta_changed:
                    body["extendedProperties"] = {"private": metadata}
                    # Actualizar descripci\u00f3n si cambiaron patrones o veh\u00edculo
                    try:
                        pats = json.loads(metadata.get('app_patrones', '[]') or '[]')
                    except:
                        pats = []
                    base_d = params.descripcion if params.descripcion is not None else ev_act.get('description', '')
                    body["description"] = generar_descripcion_enriquecida(
                        base_d,
                        params.patrones if params.patrones is not None else pats,
                        params.vehiculo if params.vehiculo is not None else metadata.get('app_vehiculo', '')
                    )

                new_id = eid'''

    if old_code in content:
        content = content.replace(old_code, new_code)
        
        # Tambi\u00e9n debemos actualizar la llamada a db.actualizar_evento_individual al final del bucle para pasar los extendedProperties actualizados
        old_db_call = r'''                else:
                    db.actualizar_evento_individual(eid, cal_target, {
                        "T\u01ed\u00fcnico": tec_nombre, "Evento": ev_act.get('summary', ''),
                        "Inicio": nuevo_s, "Fin": nuevo_e,
                        "Ubicaci\u00f3n": ev_act.get('location', ''), "Descripci\u00f3n": ev_act.get('description', ''),
                        "extendedProperties": ev_act.get('extendedProperties', {})
                    })'''
        
        new_db_call = r'''                else:
                    db.actualizar_evento_individual(eid, cal_target, {
                        "T\u01ed\u00fcnico": tec_nombre, "Evento": body.get('summary', ev_act.get('summary', '')),
                        "Inicio": nuevo_s, "Fin": nuevo_e,
                        "Ubicaci\u00f3n": ev_act.get('location', ''), "Descripci\u00f3n": body.get('description', ev_act.get('description', '')),
                        "extendedProperties": body.get('extendedProperties', ev_act.get('extendedProperties', {}))
                    })'''
        
        # Usar re.escape para evitar problemas con caracteres especiales en el regex
        content = content.replace(old_db_call, new_db_call)

        with open('api_server.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print("mover_grupo patched successfully.")
    else:
        print("Could not find anchor in api_server.py")

patch_mover_grupo()
