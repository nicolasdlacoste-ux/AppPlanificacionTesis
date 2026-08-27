import os
import uuid

text = open('api_server.py', encoding='utf-8').read()
start = text.find('dias_totales = (fecha_fin_dt - fecha_inicio_dt).days + 1')
end = text.find('App.broadcast({', start)
old_block = text[start:end]

new_block = """dias_totales = (fecha_fin_dt - fecha_inicio_dt).days + 1
        eventos_creados = []
        ids_creados = []

        if dias_totales > 1:
            inicio_str = params.fecha
            fin_str = (fecha_fin_dt + datetime.timedelta(days=1)).isoformat()
        else:
            inicio_str = TimeNormalizationService.normalize_to_utc_z(f"{fecha_inicio_dt}T{h_int:02d}:{m_int:02d}:00")
            fin_str    = TimeNormalizationService.normalize_to_utc_z(f"{fecha_inicio_dt}T{h_fin_int:02d}:{m_fin_int:02d}:00")

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

        db.guardar_evento_individual(event_obj)
        db.log_trace(event_id, "mutation_created", {"title": params.titulo}, params.correo_tecnico, "EVENT_CREATE")
        eventos_creados.append(event_obj)
        ids_creados.append(event_id)

        """

text = text.replace(old_block, new_block)

# Also apply MoverEventoParams and BatchEditarParams nueva_fecha_fin
text = text.replace("nueva_fecha: Optional[str] = None", "nueva_fecha: Optional[str] = None\n    nueva_fecha_fin: Optional[str] = None")

open('api_server.py', 'w', encoding='utf-8').write(text)
