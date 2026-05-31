
import sys

with open("api_server.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

new_code = """
class BatchEditarParams(BaseModel):
    event_ids: List[str]
    delta_dias: Optional[int] = None
    correo_destino: Optional[str] = None
    patrones: Optional[List[str]] = None
    ots: Optional[List[str]] = None
    vehiculo: Optional[str] = None

@app.post("/api/eventos/batch/editar")
async def batch_editar(params: BatchEditarParams):
    await check_authorization()
    
    # 1. Expandir grupos para asegurar que todos los miembros se actualicen
    expanded_ids = set()
    for eid in params.event_ids:
        grupo = db.obtener_grupo_de_evento(eid)
        if grupo:
            for geid in grupo["event_ids"]:
                expanded_ids.add(geid)
        else:
            expanded_ids.add(eid)

    eventos_editados = 0
    from utils import TimeNormalizationService
    import json
    import datetime

    tecs = db.obtener_tecnicos()
    target_cal = params.correo_destino
    tec_nombre_destino = None
    if target_cal:
        t_match = next((t for t in tecs if t["correo"] == target_cal or t["nombre"] == target_cal), None)
        if t_match:
            tec_nombre_destino = t_match["nombre"]
            target_cal = t_match["correo"]

    for eid in expanded_ids:
        ev_interno = db.resolve_event(eid)
        if not ev_interno: continue

        start_orig = ev_interno["inicio"]
        end_orig = ev_interno["fin"]
        
        nuevo_s = start_orig
        nuevo_e = end_orig

        if params.delta_dias is not None and params.delta_dias != 0:
            if "T" in start_orig:
                dt_s = datetime.datetime.fromisoformat(start_orig.replace("Z", "+00:00"))
                dt_e = datetime.datetime.fromisoformat(end_orig.replace("Z", "+00:00"))
                new_s_dt = dt_s + datetime.timedelta(days=params.delta_dias)
                new_e_dt = dt_e + datetime.timedelta(days=params.delta_dias)
                nuevo_s = TimeNormalizationService.normalize_to_utc_z(new_s_dt)
                nuevo_e = TimeNormalizationService.normalize_to_utc_z(new_e_dt)
            else:
                dt_s = datetime.datetime.fromisoformat(start_orig)
                new_s_dt = dt_s + datetime.timedelta(days=params.delta_dias)
                nuevo_s = new_s_dt.strftime("%Y-%m-%d")
                dt_e = datetime.datetime.fromisoformat(end_orig)
                new_e_dt = dt_e + datetime.timedelta(days=params.delta_dias)
                nuevo_e = new_e_dt.strftime("%Y-%m-%d")

        metadata = ev_interno.get("extendedProperties", {}).get("private", {})
        if params.ots is not None:
            metadata["app_ots"] = json.dumps(params.ots)
        if params.patrones is not None:
            metadata["app_patrones"] = json.dumps(params.patrones)
        if params.vehiculo is not None:
            metadata["app_vehiculo"] = params.vehiculo

        full_props = ev_interno.get("extendedProperties", {}).copy()
        full_props["private"] = metadata

        base_desc = ev_interno.get("descripcion", "")
        desc_final = generar_descripcion_enriquecida(
            base_desc,
            json.loads(metadata.get("app_patrones", "[]")),
            metadata.get("app_vehiculo", "")
        )

        cal_target = target_cal if target_cal else ev_interno["calendar_id"]
        tec_target = tec_nombre_destino if tec_nombre_destino else ev_interno.get("tecnico_nombre") or ev_interno.get("tecnico")

        is_reassignment = cal_target != ev_interno["calendar_id"]
        reassignment_id = None
        
        if is_reassignment:
            import uuid
            reassignment_id = str(uuid.uuid4())
            full_props["private"]["reassignment_in_progress"] = "true"
            full_props["private"]["reassignment_id"] = reassignment_id
            full_props["private"]["reassignment_started_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            full_props["private"]["previous_google_event_id"] = ev_interno["google_event_id"]
            full_props["private"]["previous_calendar_id"] = ev_interno["calendar_id"]
            full_props["private"]["reassignment_origin"] = "ui_batch"
            sync_status_val = "REASSIGN_PENDING"
            operation_val = "REMOTE_REASSIGNMENT"
        else:
            sync_status_val = "PENDING"
            operation_val = "UPDATE"

        nuevo_titulo = ev_interno.get("summary", "")
        if params.ots is not None and len(params.ots) > 0:
            primera_ot = str(params.ots[0])
            # Podriamos actualizar el titulo aqui si fuera necesario, simplificado para batch.

        db.actualizar_evento_individual(ev_interno["id"], ev_interno["calendar_id"], {
            "tecnico":    tec_target,
            "inicio":     nuevo_s,
            "fin":        nuevo_e,
            "descripcion": desc_final,
            "extendedProperties": full_props,
            "calendar_id": cal_target,
            "sync_status": sync_status_val,
            "pending_sync": 1,
            "updated_at": datetime.datetime.now().isoformat()
        })
        
        db.log_trace(ev_interno["id"], "mutation_batch_edit", {
            "type": "BATCH_EDIT",
            "delta_dias": params.delta_dias,
            "tecnico": tec_target,
            "calendar_id": cal_target,
            "reassignment_id": reassignment_id,
            "original_calendar_id": ev_interno["calendar_id"]
        }, calendar_id=cal_target, tag="OUTBOUND_MUTATION")

        db.enqueue_sync(ev_interno["id"], cal_target, tec_target, operation_val, 
                       origin=reassignment_id if is_reassignment else "batch_edit",
                       original_calendar_id=ev_interno["calendar_id"])

    # Auto agrupar si hubo cambio de tecnico o si movimos grupos, llamando update_group_title luego
    db.update_last_sync()

    return {"status": "ok", "editados": len(expanded_ids)}
"""

for i, line in enumerate(lines):
    if "async def mover_grupo(" in line:
        lines.insert(i-1, new_code + "\n")
        break

with open("api_server.py", "w", encoding="utf-8") as f:
    f.writelines(lines)
print("Patch applied.")

