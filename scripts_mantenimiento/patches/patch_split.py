import sys

def patch_split_evento():
    with open('api_server.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    start_idx = -1
    end_idx = -1
    for i, line in enumerate(lines):
        if line.startswith('@app.post("/api/eventos/{event_id}/split")'):
            start_idx = i
        if start_idx != -1 and i > start_idx + 1 and line.startswith('@app.post("/api/eventos/{event_id}/agregar_tecnico")'):
            # The comments before start around i-2
            for j in range(i-1, -1, -1):
                if lines[j].strip() == "" or lines[j].startswith("#"):
                    end_idx = j
                else:
                    end_idx = j + 1
                    break
            break

    if start_idx != -1 and end_idx != -1:
        new_content = '''@app.post("/api/eventos/{event_id}/split")
async def split_evento(event_id: str, calendar_id: str = Query(...)):
    await check_authorization()
    """Divide un evento multi-día en N eventos de un solo día (07:00-16:00) localmente."""
    try:
        from datetime import datetime, timedelta
        
        # 1. Obtener el evento original de la DB
        eventos = db.obtener_eventos_dict()
        ev = next((e for e in eventos if e["id"] == event_id), None)
        if not ev:
            raise HTTPException(status_code=404, detail="Evento no encontrado")
            
        titulo = ev.get('Evento', 'Sin título')
        desc = ev.get('Descripci\u00f3n', '')
        props = ev.get('extendedProperties', {})
        tec_nombre = ev.get('T\u00e9cnico', '')
        
        s_raw = ev['Inicio']
        e_raw = ev['Fin']
        
        d_start = datetime.strptime(s_raw[:10], "%Y-%m-%d")
        d_end = datetime.strptime(e_raw[:10], "%Y-%m-%d")
        
        # 2. Generar eventos individuales
        current = d_start
        while current < d_end:
            target_day = current.strftime("%Y-%m-%d")
            new_ev_id = f"local_{uuid.uuid4().hex[:12]}"
            
            db.guardar_evento_individual({
                "id": new_ev_id,
                "calendar_id": calendar_id,
                "tecnico_nombre": tec_nombre,
                "summary": titulo,
                "inicio": f"{target_day}T07:00:00-03:00",
                "fin": f"{target_day}T16:00:00-03:00",
                "ubicacion": ev.get('Ubicaci\u00f3n', ''),
                "descripcion": desc,
                "extendedProperties": props,
                "version": 1,
                "sync_status": "LOCAL"
            })
            current += timedelta(days=1)
            
        # 3. Eliminar el original
        db.eliminar_evento_individual(event_id)
        
        db.update_last_sync()
        return {"status": "ok"}
    except Exception as e:
        import traceback; print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
'''
        lines = lines[:start_idx] + [new_content] + lines[end_idx:]
        with open('api_server.py', 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print("split_evento replaced successfully.")
    else:
        print(f"Could not find bounds for split_evento: start={start_idx}, end={end_idx}")

patch_split_evento()
