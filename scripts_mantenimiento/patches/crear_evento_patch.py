
import sys

with open("api_server.py", "r", encoding="utf-8") as f:
    js = f.read()

start_str = "async def crear_evento"
end_str = "async def duplicar_evento"

start_idx = js.find(start_str)
end_idx = js.find(end_str)

if start_idx == -1 or end_idx == -1:
    print("Not found")
    sys.exit(1)

# Backtrack to the @app.post decorator for crear_evento if possible
decorator_idx = js.rfind("@app.post(\"/api/eventos/crear\")", 0, start_idx)
if decorator_idx != -1:
    start_idx = decorator_idx

new_func = """@app.post("/api/eventos/crear")
async def crear_evento(params: CrearEventoParams):
    await check_authorization()
    try:
        from utils import TimeNormalizationService
        import uuid
        
        fecha_inicio_dt = datetime.date.fromisoformat(params.fecha)
        fecha_fin_dt = datetime.date.fromisoformat(params.fecha_fin) if params.fecha_fin else fecha_inicio_dt
        
        if fecha_fin_dt < fecha_inicio_dt:
            raise HTTPException(400, "La fecha de fin no puede ser anterior a la fecha de inicio")

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

        desc_enriquecida = generar_descripcion_enriquecida(params.descripcion, params.patrones, params.vehiculo)

        tec_nombre = params.correo_tecnico
        tecs = db.obtener_tecnicos()
        t_match = next((t for t in tecs if t["correo"] == params.correo_tecnico or t["nombre"] == params.correo_tecnico), None)
        if t_match:
            tec_nombre = t_match["nombre"]
            
        dias_totales = (fecha_fin_dt - fecha_inicio_dt).days + 1
        eventos_creados = []
        ids_creados = []

        for offset in range(dias_totales):
            fecha_actual = fecha_inicio_dt + datetime.timedelta(days=offset)
            
            inicio_str = TimeNormalizationService.normalize_to_utc_z(f"{fecha_actual}T{h_int:02d}:{m_int:02d}:00")
            fin_str    = TimeNormalizationService.normalize_to_utc_z(f"{fecha_actual}T{h_fin_int:02d}:{m_fin_int:02d}:00")

            event_id = f"local_{uuid.uuid4().hex[:12]}"

            event_obj = {
                "id": event_id,
                "google_event_id": event_id,
                "calendar_id": params.correo_tecnico,
                "tecnico": tec_nombre,
                "tecnico_nombre": tec_nombre,
                "summary": params.titulo,
                "evento": params.titulo,
                "inicio": inicio_str,
                "fin": fin_str,
                "descripcion": desc_enriquecida,
                "ubicacion": params.direccion,
                "extendedProperties": { "private": metadata.copy() },
                "sync_status": "PENDING",
                "pending_sync": 1
            }

            db.insert_event(event_obj)
            
            db.log_trace(event_id, "mutation_created", {
                "type": "INSERT",
                "new_tecnico": tec_nombre,
                "new_calendar": params.correo_tecnico,
            }, calendar_id=params.correo_tecnico, tag="OUTBOUND_MUTATION")

            db.enqueue_sync(event_id, params.correo_tecnico, tec_nombre, "INSERT")
            eventos_creados.append(event_obj)
            ids_creados.append(event_id)

        if params.ots and len(params.ots) > 0:
            for ev_id in ids_creados:
                await _auto_agrupar_evento(ev_id, params.correo_tecnico, tec_nombre, str(fecha_inicio_dt), params.ots)

        return {"status": "ok", "ids": ids_creados, "count": len(ids_creados)}

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/eventos/{event_id}/duplicar")
"""

js = js[:start_idx] + new_func + js[end_idx + len("async def duplicar_evento(event_id: str):") - len("@app.post(\"/api/eventos/{event_id}/duplicar\")\nasync def duplicar_evento(event_id: str):\n"):]

with open("api_server.py", "w", encoding="utf-8") as f:
    f.write(js)
print("api_server.py patched.")

