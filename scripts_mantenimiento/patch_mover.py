import sys

def patch_file():
    with open('api_server.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Find start and end indices
    start_idx = -1
    end_idx = -1
    for i, line in enumerate(lines):
        if line.startswith('@app.patch("/api/eventos/{event_id}/mover")'):
            start_idx = i
        if line.startswith('@app.patch("/api/eventos/{event_id}/mover_grupo")'):
            # The comments before mover_grupo start around i-5, let's find the exact line.
            for j in range(i-1, -1, -1):
                if lines[j].strip() == "" or lines[j].startswith("#"):
                    end_idx = j
                else:
                    end_idx = j + 1
                    break
            break

    if start_idx != -1 and end_idx != -1:
        new_content = '''@app.patch("/api/eventos/{event_id}/mover")
async def mover_evento(event_id: str, params: MoverEventoParams):
    await check_authorization()

    if params.base_version is not None:
        with db._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT version FROM eventos WHERE id = ?", (event_id,))
            row = cur.fetchone()
            if row and row[0] > params.base_version:
                raise HTTPException(status_code=409, detail=f"Conflicto de concurrencia. Version local: {params.base_version}, Version DB: {row[0]}")
                
    try:
        # 1. Leer de BD local
        eventos_db = db.obtener_eventos_dict()
        ev_actual_db = next((e for e in eventos_db if e["id"] == event_id), None)
        if not ev_actual_db:
            raise HTTPException(404, "Evento no encontrado")
            
        start_orig = ev_actual_db["Inicio"]
        end_orig = ev_actual_db["Fin"]
        
        ev_actual = {
            "extendedProperties": ev_actual_db.get("extendedProperties", {}),
            "description": ev_actual_db.get("Descripción", ""),
            "summary": ev_actual_db.get("Evento", ""),
            "location": ev_actual_db.get("Ubicación", "")
        }

        nueva_f = datetime.date.fromisoformat(params.nueva_fecha)
        tz_suffix = "-03:00"

        if params.h_start is not None:
            dur = params.h_dur
            if dur is None:
                try:
                    dt_s_orig = datetime.datetime.fromisoformat(start_orig.replace('Z', '+00:00'))
                    dt_e_orig = datetime.datetime.fromisoformat(end_orig.replace('Z', '+00:00'))
                    dur = (dt_e_orig - dt_s_orig).total_seconds() / 3600.0
                except:
                    dur = 1.0 
            
            dt_base = datetime.datetime.combine(nueva_f, datetime.time(0, 0))
            dt_s_new = dt_base + datetime.timedelta(hours=params.h_start)
            dt_e_new = dt_base + datetime.timedelta(hours=params.h_start + dur)
            
            nuevo_s = dt_s_new.strftime(f"%Y-%m-%dT%H:%M:%S{tz_suffix}")
            nuevo_e = dt_e_new.strftime(f"%Y-%m-%dT%H:%M:%S{tz_suffix}")
        elif "T" in start_orig:
            dt_s = datetime.datetime.fromisoformat(start_orig.replace('Z', '+00:00'))
            dt_e = datetime.datetime.fromisoformat(end_orig.replace('Z', '+00:00'))
            delta = (nueva_f - dt_s.date()).days
            new_s_dt = dt_s + datetime.timedelta(days=delta)
            new_e_dt = dt_e + datetime.timedelta(days=delta)
            nuevo_s = new_s_dt.strftime(f"%Y-%m-%dT%H:%M:%S{tz_suffix}")
            nuevo_e = new_e_dt.strftime(f"%Y-%m-%dT%H:%M:%S{tz_suffix}")
        else:
            nuevo_s = nueva_f.isoformat()
            nuevo_e = (nueva_f + datetime.timedelta(days=1)).isoformat()

        metadata = ev_actual.get('extendedProperties', {}).get('private', {})
        if params.ots is not None:
            metadata["app_ots"] = json.dumps(params.ots)
        if params.patrones is not None:
            metadata["app_patrones"] = json.dumps(params.patrones)
        if params.vehiculo is not None:
            metadata["app_vehiculo"] = params.vehiculo
        if params.requiere_vehiculo is not None:
            metadata["app_requiere_vehiculo"] = str(params.requiere_vehiculo).lower()

        full_props = ev_actual.get('extendedProperties', {}).copy()
        full_props["private"] = metadata

        try:
            pats_actuales = json.loads(metadata.get('app_patrones', '[]') or '[]')
        except:
            pats_actuales = []

        base_desc = params.descripcion if params.descripcion is not None else ev_actual.get('description', '')
        if any(x is not None for x in [params.descripcion, params.patrones, params.vehiculo]):
            desc_final = generar_descripcion_enriquecida(
                base_desc,
                params.patrones if params.patrones is not None else pats_actuales,
                params.vehiculo if params.vehiculo is not None else metadata.get('app_vehiculo', '')
            )
        else:
            desc_final = base_desc

        target_cal = params.correo_destino or ev_actual_db["calendar_id"]
        tecs = db.obtener_tecnicos()
        t_match = next((t for t in tecs if t['correo'] == target_cal or t['nombre'] == target_cal), None)
        tec_nombre = t_match['nombre'] if t_match else target_cal

        nuevo_titulo = params.titulo if params.titulo is not None else ev_actual.get('summary', '')
        
        # VALIDACIÓN ETAPA 5
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
            ignore_event_ids=[event_id]
        )
        if error_conflicto:
            raise HTTPException(status_code=409, detail=error_conflicto)

        # PERSISTENCIA LOCAL (Simulando API de Google)
        try:
            new_version = db.actualizar_evento_individual(event_id, target_cal, {
                "Técnico":    tec_nombre,
                "Evento":     nuevo_titulo,
                "Inicio":     nuevo_s,
                "Fin":        nuevo_e,
                "Ubicación":  params.direccion if params.direccion is not None else ev_actual.get('location', ''),
                "Descripción": desc_final,
                "extendedProperties": full_props
            }, base_version=params.base_version)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))

        grupo = db.obtener_grupo_de_evento(event_id)
        if grupo:
            nueva_f_str = nuevo_s[:10]
            cambio_fecha = (nueva_f_str != grupo['fecha'])
            cambio_tecnico = (target_cal != ev_actual_db["calendar_id"])
            
            if cambio_fecha:
                new_event_ids = [eid for eid in grupo['event_ids'] if eid != event_id]
                try:
                    idx_rem = grupo['event_ids'].index(event_id)
                    new_tecnico_nombres = [n for i, n in enumerate(grupo['tecnico_nombres']) if i != idx_rem]
                except:
                    new_tecnico_nombres = [n for n in grupo['tecnico_nombres'] if n != tec_nombre]

                if not new_event_ids or len(new_event_ids) <= 1:
                    db.eliminar_grupo(grupo['grupo_id'])
                else:
                    db.crear_o_actualizar_grupo(grupo['grupo_id'], grupo['fecha'], new_event_ids, new_tecnico_nombres)

        return {
            "status": "ok",
            "event_id": event_id,
            "version": new_version
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print("Error global en mover:", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

'''
        lines = lines[:start_idx] + [new_content] + lines[end_idx:]
        with open('api_server.py', 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print("mover_evento replaced successfully.")
    else:
        print(f"Could not find bounds: start={start_idx}, end={end_idx}")

patch_file()
