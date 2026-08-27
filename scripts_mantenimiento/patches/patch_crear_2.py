import os, re

text = open('api_server.py', encoding='utf-8').read()

old_pattern = r'        dias_totales = \(fecha_fin_dt - fecha_inicio_dt\)\.days \+ 1\s+eventos_creados = \[\]\s+ids_creados = \[\]\s+for offset in range\(dias_totales\):.*?ids_creados\.append\(event_id\)'

new_block = '''        eventos_creados = []
        ids_creados = []
        dias_totales = (fecha_fin_dt - fecha_inicio_dt).days + 1

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
        ids_creados.append(event_id)'''

text = re.sub(old_pattern, new_block, text, flags=re.DOTALL)
open('api_server.py', 'w', encoding='utf-8').write(text)
print('Replaced api_server.py!')

# AND NOW webapp/right-panel.js
js_text = open('webapp/right-panel.js', encoding='utf-8').read()
js_old = r'''                                fecha: fdata\.date,\s*h_start: fdata\.h_start,'''
js_new = '''                                fecha: fdata.date,
                                fecha_fin: fdata.fecha_fin || null,
                                h_start: fdata.h_start,'''
js_text = re.sub(js_old, js_new, js_text)
open('webapp/right-panel.js', 'w', encoding='utf-8').write(js_text)
print('Replaced webapp/right-panel.js!')
