import os

text = open('api_server.py', encoding='utf-8').read()

# 1. Update _is_complex_event
old_complex = '''def _is_complex_event(ev: dict) -> bool:
    """Determina si un evento tiene invitados externos (ya no bloquea multidía)."""
    ext = ev.get('extendedProperties') or {}
    priv = ext.get('private') or {}
    if str(priv.get('has_guests', "false")).lower() == "true":
        return True
        
    inicio = ev.get('inicio', '')
    fin = ev.get('fin', '')
    
    if inicio and fin and len(inicio) == 10 and len(fin) == 10:
        if inicio != fin:
            return True
            
    if inicio and "T" in inicio and fin and "T" in fin:
        import datetime
        try:
            dt_s = datetime.datetime.fromisoformat(inicio.replace('Z', '+00:00'))
            dt_e = datetime.datetime.fromisoformat(fin.replace('Z', '+00:00'))
            if (dt_e - dt_s).total_seconds() > 24 * 3600:
                return True
        except:
            pass
            
    return False'''
new_complex = '''def _is_complex_event(ev: dict) -> bool:
    """Determina si un evento tiene invitados externos (ya no bloquea multidía)."""
    ext = ev.get('extendedProperties') or {}
    priv = ext.get('private') or {}
    if str(priv.get('has_guests', "false")).lower() == "true":
        return True
    return False'''
if old_complex in text:
    text = text.replace(old_complex, new_complex)

# 2. Add nueva_fecha_fin to MoverEventoParams
text = text.replace("    nueva_fecha: str  # YYYY-MM-DD\n    h_start: Optional[float] = None", "    nueva_fecha: str  # YYYY-MM-DD\n    nueva_fecha_fin: Optional[str] = None\n    h_start: Optional[float] = None")

# 3. Add nueva_fecha_fin to BatchEditarParams
text = text.replace("    nueva_fecha: Optional[str] = None\n    h_start: Optional[float] = None", "    nueva_fecha: Optional[str] = None\n    nueva_fecha_fin: Optional[str] = None\n    h_start: Optional[float] = None")

# 4. Refactor crear_evento
old_crear = '''        dias_totales = (fecha_fin_dt - fecha_inicio_dt).days + 1
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

            db.guardar_evento_individual(event_obj)
            
            db.log_trace(event_id, "mutation_created", {
                "title": params.titulo,
                "offset": offset
            }, params.correo_tecnico, "EVENT_CREATE")
            
            eventos_creados.append(event_obj)
            ids_creados.append(event_id)'''

new_crear = '''        eventos_creados = []
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

if old_crear in text:
    text = text.replace(old_crear, new_crear)

open('api_server.py', 'w', encoding='utf-8').write(text)
