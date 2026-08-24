import sys

def patch_crear_evento():
    with open('api_server.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    start_idx = -1
    end_idx = -1
    for i, line in enumerate(lines):
        if line.startswith('@app.post("/api/eventos/crear")'):
            start_idx = i
        if start_idx != -1 and i > start_idx + 10 and line.startswith('        return {'):
            # Find the end of the return dict
            for j in range(i, len(lines)):
                if lines[j].strip() == "}":
                    end_idx = j + 1
                    break
            break

    if start_idx != -1 and end_idx != -1:
        new_content = '''@app.post("/api/eventos/crear")
async def crear_evento(params: CrearEventoParams):
    await check_authorization()
    try:
        fecha = datetime.date.fromisoformat(params.fecha)
        h_int = int(params.h_start)
        m_int = int((params.h_start % 1) * 60)
        h_fin = params.h_start + params.h_dur
        h_fin_int = int(h_fin)
        m_fin_int = int((h_fin % 1) * 60)

        metadata = {
            "app_ots": json.dumps(params.ots),
            "app_patrones": json.dumps(params.patrones),
        }
        if params.vehiculo:
            metadata["app_vehiculo"] = params.vehiculo
        if params.requiere_vehiculo:
            metadata["app_requiere_vehiculo"] = str(params.requiere_vehiculo).lower()

        inicio_str = f"{params.fecha}T{h_int:02d}:{m_int:02d}:00-03:00"
        fin_str    = f"{params.fecha}T{h_fin_int:02d}:{m_fin_int:02d}:00-03:00"

        desc_enriquecida = generar_descripcion_enriquecida(params.descripcion, params.patrones, params.vehiculo)

        # LOCAL-ONLY: Generar un ID local y omitir Google Calendar
        event_id = f"local_{uuid.uuid4().hex[:12]}"

        tec_nombre = params.correo_tecnico
        tecs = db.obtener_tecnicos()
        t_match = next((t for t in tecs if t['correo'] == params.correo_tecnico or t['nombre'] == params.correo_tecnico), None)
        if t_match:
            tec_nombre = t_match['nombre']

        # Persistir en SQLite con sync_status=LOCAL
        db.guardar_evento_individual({
            "id": event_id,
            "calendar_id": params.correo_tecnico,
            "tecnico_nombre": tec_nombre,
            "summary": params.titulo,
            "inicio": inicio_str,
            "fin": fin_str,
            "ubicacion": params.direccion,
            "descripcion": desc_enriquecida,
            "extendedProperties": {'private': {**metadata, 'source': 'internal', 'version': '1'}},
            "version": 1,
            "sync_status": "LOCAL",
            "source": "internal",
            "updated_at": datetime.datetime.now().isoformat(),
        })
        db.update_last_sync()

        # Intentar auto-agrupar localmente (sin svc_cal)
        try:
            # _auto_agrupar_evento_local(event_id, params.correo_tecnico, tec_nombre, params.fecha, params.ots)
            pass
        except Exception as ge:
            print(f"Error auto-agrupando evento nuevo: {ge}")

        return {
            "status": "ok",
            "id": event_id,
            "event_id": event_id,
            "resourceId": tec_nombre,
            "title": params.titulo,
            "start": inicio_str,
            "end": fin_str,
            "extendedProperties": {'private': {**metadata, 'source': 'internal', 'version': '1'}},
            "version": 1,
            "sync_status": "LOCAL"
        }

    except Exception as e:
        import traceback
        print("Error en crear_evento:", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
'''
        lines = lines[:start_idx] + [new_content] + lines[end_idx:]
        with open('api_server.py', 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print("crear_evento replaced successfully.")
    else:
        print(f"Could not find bounds for crear_evento: start={start_idx}, end={end_idx}")

patch_crear_evento()
