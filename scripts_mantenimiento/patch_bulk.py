import sys

def patch_endpoint(endpoint_decorator, next_endpoint_decorator, new_body):
    with open('api_server.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    start_idx = -1
    end_idx = -1
    for i, line in enumerate(lines):
        if line.startswith(endpoint_decorator):
            start_idx = i
        if start_idx != -1 and i > start_idx and line.startswith(next_endpoint_decorator):
            # Backtrack to the start of the next endpoint (comments/decorator)
            for j in range(i-1, -1, -1):
                if lines[j].strip() == "" or lines[j].startswith("#"):
                    end_idx = j
                else:
                    end_idx = j + 1
                    break
            break
            
    if start_idx != -1 and end_idx != -1:
        lines = lines[:start_idx] + [new_body] + lines[end_idx:]
        with open('api_server.py', 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print(f"{endpoint_decorator} replaced successfully.")
        return True
    else:
        print(f"Could not find bounds for {endpoint_decorator}: start={start_idx}, end={end_idx}")
        return False

# 1. Agregar tecnico
patch_endpoint(
    '@app.post("/api/eventos/{event_id}/agregar_tecnico")',
    '@app.post("/api/grupos/registrar")',
    '''@app.post("/api/eventos/{event_id}/agregar_tecnico")
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
            "ubicacion": base_ev.get('Ubicación', ''),
            "descripcion": base_ev.get('Descripción', ''),
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
            new_nombres = [base_ev['Técnico'], nuevo_nombre]
            db.crear_o_actualizar_grupo(nuevo_grupo_id, base_ev['Inicio'][:10], new_ids, new_nombres)

        db.update_last_sync()
        return {"status": "ok", "new_event_id": new_ev_id}
    except Exception as e:
        import traceback; print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
'''
)

# 2. Eliminar grupo completo
patch_endpoint(
    '@app.delete("/api/grupos/{grupo_id}")',
    '@app.post("/api/eventos/{event_id}/split")',
    '''@app.delete("/api/grupos/{grupo_id}")
async def eliminar_grupo_completo(grupo_id: str):
    await check_authorization()
    """Elimina todos los eventos de un grupo localmente."""
    try:
        eventos = db.obtener_eventos_dict()
        # Buscar el grupo en la DB
        # Nota: obtener_eventos_dict no tiene el grupo_id directo en cada evento de forma f\u00e1cil, 
        # pero podemos usar el helper de data_manager si existiera.
        # Por ahora, usemos una conexi\u00f3n directa o busquemos por metadatos.
        with db._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT event_ids FROM grupos WHERE grupo_id = ?", (grupo_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Grupo no encontrado")
            
            event_ids = json.loads(row[0])
            for eid in event_ids:
                db.eliminar_evento_individual(eid)
            
            db.eliminar_grupo(grupo_id)
            
        db.update_last_sync()
        return {"status": "ok"}
    except Exception as e:
        print("Error en eliminar_grupo_completo:", e)
        raise HTTPException(status_code=500, detail=str(e))
'''
)

