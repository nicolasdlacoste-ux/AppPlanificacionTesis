import sys

def patch_file():
    with open('api_server.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    start_idx = -1
    end_idx = -1
    for i, line in enumerate(lines):
        if line.startswith('@app.patch("/api/eventos/{event_id}/mover_grupo")'):
            start_idx = i
        if start_idx != -1 and i > start_idx + 10 and line.startswith('@app.delete("/api/grupos/{grupo_id}")'):
            for j in range(i-1, -1, -1):
                if lines[j].strip() == "" or lines[j].startswith("#"):
                    end_idx = j
                else:
                    end_idx = j + 1
                    break
            break

    if start_idx != -1 and end_idx != -1:
        new_content = '''@app.patch("/api/eventos/{event_id}/mover_grupo")
async def mover_grupo(event_id: str, params: MoverEventoParams):
    await check_authorization()
    if params.base_version is not None:
        with db._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT version FROM eventos WHERE id = ?", (event_id,))
            row = cur.fetchone()
            if row and row[0] > params.base_version:
                raise HTTPException(status_code=409, detail=f"Conflicto de concurrencia en grupo. Version local: {params.base_version}, Version DB: {row[0]}")
    try:
        grupo = db.obtener_grupo_de_evento(event_id)
        if not grupo:
            return await mover_evento(event_id, params)

        eventos_db = db.obtener_eventos_dict()
        map_id_evento = {e["id"]: e for e in eventos_db}
        
        tecs_db = db.obtener_tecnicos()
        map_nombre_correo = {t['nombre']: t['correo'] for t in tecs_db}

        nueva_f = datetime.date.fromisoformat(params.nueva_fecha)
        tz_suffix = "-03:00"

        for i, eid in enumerate(grupo['event_ids']):
            ev_actual_db = map_id_evento.get(eid)
            if not ev_actual_db:
                continue
                
            tec_nombre = grupo['tecnico_nombres'][i] if i < len(grupo['tecnico_nombres']) else ev_actual_db["T\u00e9cnico"]
            cal_target = map_nombre_correo.get(tec_nombre) or ev_actual_db.get("calendar_id", "")
            
            start_orig = ev_actual_db["Inicio"]
            end_orig = ev_actual_db["Fin"]

            if params.h_start is not None:
                dur = params.h_dur
                if dur is None:
                    try:
                        dt_s = datetime.datetime.fromisoformat(start_orig.replace('Z', '+00:00'))
                        dt_e = datetime.datetime.fromisoformat(end_orig.replace('Z', '+00:00'))
                        dur = (dt_e - dt_s).total_seconds() / 3600.0
                    except:
                        dur = 1.0
                hs = params.h_start
                dt_base = datetime.datetime.combine(nueva_f, datetime.time(0, 0))
                dt_s_new = dt_base + datetime.timedelta(hours=hs)
                dt_e_new = dt_base + datetime.timedelta(hours=hs + dur)
                nuevo_s = dt_s_new.strftime(f"%Y-%m-%dT%H:%M:%S{tz_suffix}")
                nuevo_e = dt_e_new.strftime(f"%Y-%m-%dT%H:%M:%S{tz_suffix}")
            elif "T" in start_orig:
                dt_s = datetime.datetime.fromisoformat(start_orig.replace('Z', '+00:00'))
                dt_e = datetime.datetime.fromisoformat(end_orig.replace('Z', '+00:00'))
                delta = (nueva_f - dt_s.date()).days
                nuevo_s = (dt_s + datetime.timedelta(days=delta)).strftime(f"%Y-%m-%dT%H:%M:%S{tz_suffix}")
                nuevo_e = (dt_e + datetime.timedelta(days=delta)).strftime(f"%Y-%m-%dT%H:%M:%S{tz_suffix}")
            else:
                nuevo_s = nueva_f.isoformat()
                nuevo_e = (nueva_f + datetime.timedelta(days=1)).isoformat()

            metadata = ev_actual_db.get('extendedProperties', {}).get('private', {}).copy()
            if params.ots is not None:
                metadata["app_ots"] = json.dumps(params.ots)
            if params.patrones is not None:
                metadata["app_patrones"] = json.dumps(params.patrones)
            if params.vehiculo is not None:
                metadata["app_vehiculo"] = params.vehiculo
            if params.requiere_vehiculo is not None:
                metadata["app_requiere_vehiculo"] = str(params.requiere_vehiculo).lower()
                
            full_props = ev_actual_db.get('extendedProperties', {}).copy()
            full_props["private"] = metadata

            try:
                pats_actuales = json.loads(metadata.get('app_patrones', '[]') or '[]')
            except:
                pats_actuales = []

            base_desc = params.descripcion if params.descripcion is not None else ev_actual_db.get('Descripci\u00f3n', '')
            if any(x is not None for x in [params.descripcion, params.patrones, params.vehiculo]):
                desc_final = generar_descripcion_enriquecida(
                    base_desc,
                    params.patrones if params.patrones is not None else pats_actuales,
                    params.vehiculo if params.vehiculo is not None else metadata.get('app_vehiculo', '')
                )
            else:
                desc_final = base_desc
                
            nuevo_titulo = params.titulo if params.titulo is not None else ev_actual_db.get('Evento', '')

            # VALIDACI\u00d3N ETAPA 5
            h_start_val = params.h_start
            h_end_val = params.h_start + dur if params.h_start is not None else None
            if h_start_val is None:
                try:
                    dt_s_val = datetime.datetime.fromisoformat(nuevo_s.replace('Z', '+00:00'))
                    dt_e_val = datetime.datetime.fromisoformat(nuevo_e.replace('Z', '+00:00'))
                    h_start_val = dt_s_val.hour + dt_s_val.minute / 60.0
                    h_end_val = dt_e_val.hour + dt_e_val.minute / 60.0
                except:
                    h_start_val, h_end_val = 7.0, 16.0
                    
            vehiculo_val = params.vehiculo if params.vehiculo is not None else metadata.get('app_vehiculo', '')
            patrones_val = params.patrones if params.patrones is not None else pats_actuales
            
            error_conflicto = db.check_conflictos_negocio(
                tecnico=tec_nombre,
                vehiculo=vehiculo_val,
                patrones=patrones_val,
                fecha=params.nueva_fecha,
                h_start=h_start_val,
                h_end=h_end_val,
                ignore_event_ids=grupo['event_ids']
            )
            if error_conflicto:
                raise HTTPException(status_code=409, detail=error_conflicto)

            db.actualizar_evento_individual(eid, cal_target, {
                "T\u00e9cnico": tec_nombre, "Evento": nuevo_titulo,
                "Inicio": nuevo_s, "Fin": nuevo_e,
                "Ubicaci\u00f3n": params.direccion if params.direccion is not None else ev_actual_db.get('Ubicaci\u00f3n', ''), 
                "Descripci\u00f3n": desc_final,
                "extendedProperties": full_props
            }, base_version=params.base_version if eid == event_id else None)

        # Actualizar IDs en el grupo si cambiaron
        new_grupo_data = {**grupo, "fecha": params.nueva_fecha}
        
        # PROPAGAR VEH\u00cdCULO Y PATRONES SI CAMBIARON
        if params.vehiculo is not None: new_grupo_data['vehiculo'] = params.vehiculo
        if params.patrones is not None: new_grupo_data['patrones'] = params.patrones

        db.crear_o_actualizar_grupo(
            new_grupo_data['grupo_id'], 
            new_grupo_data['fecha'], 
            new_grupo_data['event_ids'], 
            new_grupo_data['tecnico_nombres']
        )
        
        return {"status": "ok", "moved": len(grupo['event_ids'])}

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print("Error global en mover_grupo:", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

'''
        lines = lines[:start_idx] + [new_content] + lines[end_idx:]
        with open('api_server.py', 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print("mover_grupo replaced successfully.")
    else:
        print(f"Could not find bounds: start={start_idx}, end={end_idx}")

patch_file()
