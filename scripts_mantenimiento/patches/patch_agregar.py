import sys

def patch_agregar_tecnico():
    with open('api_server.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    start_idx = -1
    end_idx = -1
    for i, line in enumerate(lines):
        if line.startswith('@app.post("/api/eventos/{event_id}/agregar_tecnico")'):
            start_idx = i
        if start_idx != -1 and i > start_idx + 1 and line.startswith('    except Exception as e:'):
            for j in range(i, len(lines)):
                if lines[j].startswith("    return "):
                    end_idx = j + 1
                    break
            break

    if start_idx != -1 and end_idx != -1:
        new_content = '''@app.post("/api/eventos/{event_id}/agregar_tecnico")
async def agregar_tecnico_a_grupo(event_id: str, tecnico_correo: str = Query(...), calendar_id: str = Query(...)):
    await check_authorization()
    """Agrega a un nuevo técnico a la misma OT/fecha de un evento existente localmente."""
    try:
        # 1. Obtener datos del evento base
        eventos = db.obtener_eventos_dict()
        base_ev = next((e for e in eventos if e["id"] == event_id), None)
        if not base_ev:
            raise HTTPException(status_code=404, detail="Evento base no encontrado")

        # 2. Resolver nombre del nuevo técnico
        tecnicos = db.obtener_tecnicos()
        t_new = next((t for t in tecnicos if t['correo'] == tecnico_correo), None)
        if not t_new:
            raise HTTPException(status_code=404, detail="Técnico no encontrado")
        
        nuevo_nombre = t_new['nombre']
        
        # 3. Crear el nuevo evento localmente
        new_ev_id = f"local_{uuid.uuid4().hex[:12]}"
        db.guardar_evento_individual({
            "id": new_ev_id,
            "calendar_id": tecnico_correo,
            "tecnico_nombre": nuevo_nombre,
            "summary": base_ev['Evento'],
            "inicio": base_ev['Inicio'],
            "fin": base_ev['Fin'],
            "ubicacion": base_ev.get('Ubicaci\u00f3n', ''),
            "descripcion": base_ev.get('Descripci\u00f3n', ''),
            "extendedProperties": base_ev.get('extendedProperties', {}),
            "version": 1,
            "sync_status": "LOCAL"
        })

        # 4. Gestión de Grupos
        grupo = db.obtener_grupo_de_evento(event_id)
        if grupo:
            # Añadir al grupo existente
            new_ids = list(grupo['event_ids']) + [new_ev_id]
            new_nombres = list(grupo['tecnico_nombres']) + [nuevo_nombre]
            db.crear_o_actualizar_grupo(grupo['grupo_id'], grupo['fecha'], new_ids, new_nombres)
        else:
            # Crear grupo nuevo con ambos
            nuevo_grupo_id = str(uuid.uuid4())
            new_ids = [event_id, new_ev_id]
            new_nombres = [base_ev['T\u00e9cnico'], nuevo_nombre]
            db.crear_o_actualizar_grupo(nuevo_grupo_id, base_ev['Inicio'][:10], new_ids, new_nombres)

        db.update_last_sync()
        return {"status": "ok", "new_event_id": new_ev_id}
    except Exception as e:
        print("Error en agregar_tecnico:", e)
        raise HTTPException(status_code=500, detail=str(e))
'''
        lines = lines[:start_idx] + [new_content] + lines[end_idx:]
        with open('api_server.py', 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print("agregar_tecnico replaced successfully.")
    else:
        print(f"Could not find bounds for agregar_tecnico: start={start_idx}, end={end_idx}")

patch_agregar_tecnico()
