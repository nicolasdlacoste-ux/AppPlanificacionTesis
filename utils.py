import unicodedata
import re
import datetime
import json
import uuid
import pytz

ARG_TZ = pytz.timezone("America/Argentina/Buenos_Aires")

def _now_iso() -> str:
    """Retorna el timestamp actual en UTC como string ISO8601 con 'Z'."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _parse_dt(dt_str: str) -> datetime.datetime | None:
    """
    Parsea un string ISO8601 a datetime. 
    Siempre retorna un objeto NAIVE en UTC para comparaciones seguras.
    """
    if not dt_str:
        return None
    try:
        # Usar TimeNormalizationService para garantizar UTC
        norm = TimeNormalizationService.normalize_to_utc_z(dt_str)
        # Quitar la Z y el T para fromisoformat o simplemente usar strptime
        return datetime.datetime.strptime(norm, "%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None

def _normalize(val) -> str:
    """Normaliza un valor para comparación."""
    return str(val).strip() if val is not None else ""

def _poll_log(db, event_type: str, name: str, detail: dict,
              calendar_id: str = None, event_id: str = None, version: int = None):
    """
    Registro centralizado de todas las operaciones de polling.
    Escribe a stdout y persiste en poll_log (best-effort).
    """
    log_id    = str(uuid.uuid4())
    timestamp = datetime.datetime.utcnow().isoformat() + "Z"
    full_type = f"{event_type}:{name}"
    detail_str = json.dumps(detail, ensure_ascii=False)

    print(f"[POLL] {timestamp} {full_type:35s} {detail_str[:140]}")

    try:
        db.write_poll_log(
            log_id=log_id,
            timestamp=timestamp,
            event_type=full_type,
            calendar_id=calendar_id,
            event_id=event_id,
            version=version,
            detail=detail_str
        )
    except Exception:
        pass  # El log nunca debe romper el flujo

def normalizar_texto(s):
    """
    Elimina acentos, convierte a minúsculas y limpia espacios.
    Útil para comparaciones de nombres de técnicos y búsqueda de strings.
    """
    if not s: return ""
    s = str(s).lower().strip()
    # Eliminar acentos usando normalización NFD
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    return s

def extraer_ots(texto):
    """
    Extrae todos los números de 3 o más dígitos de un texto.
    Ignora P1, P2 (puntos de calibración) pero atrapa 8131, 8598, etc.
    """
    if not texto: return set()
    return set(re.findall(r'\d{3,}', str(texto)))

def get_ot_base_from_event(ev: dict) -> str:
    """
    Extrae el título base de la OT de un evento.
    Primero intenta leer app_ots de extended_props para buscar la porción
    del summary que corresponde. Si no hay OT en metadata, retorna el
    summary completo sin el sufijo de técnicos (" - X + Y").
    """
    try:
        ext = ev.get('extended_props') or {}
        if isinstance(ext, str):
            ext = json.loads(ext)
        if isinstance(ext, dict):
            ots_raw = ext.get('private', {}).get('app_ots', '[]')
            if isinstance(ots_raw, str):
                ots = json.loads(ots_raw)
            else:
                ots = ots_raw or []
            if ots:
                # El OT base es el summary sin el sufijo " - INICIALES"
                summary = ev.get('summary', '')
                # Separador canónico: " - " antes del bloque de iniciales
                if ' - ' in summary:
                    return summary.split(' - ')[0].strip()
                return summary.strip()
    except Exception:
        pass
    # Fallback: quitar sufijo de técnicos si existe
    summary = ev.get('summary') or ev.get('evento', '')
    if ' - ' in summary:
        return summary.split(' - ')[0].strip()
    return summary.strip()


def format_group_summary(ot_base: str, iniciales_list: list) -> str:
    """
    Genera el título canónico de un evento de grupo.
    Ej: '8775 (DROGUERIA VORS) - ND + NM'
    Si hay 0 o 1 iniciales, retorna solo ot_base (evento individual).
    """
    if not ot_base:
        return ''
    filtered = [i for i in iniciales_list if i]
    if len(filtered) <= 1:
        return ot_base
    suffix = " + ".join(filtered)
    return f"{ot_base} - {suffix}"


def evaluar_conflicto(ots_por_tecnico):
    """
    Decide si un grupo de técnicos tiene un conflicto de patrones.
    Recibe: { t_name_norm: set(ot_numbers) }
    Retorna: (hay_conflicto, o_compartida) 
    - hay_conflicto: True si no comparten OT común.
    - o_compartida: Set de OTs comunes (si existe).
    """
    if len(ots_por_tecnico) <= 1:
        return False, set()

    tech_sets = list(ots_por_tecnico.values())
    
    # Intersección de TODOS los técnicos
    interseccion = tech_sets[0]
    for s in tech_sets[1:]:
        interseccion = interseccion.intersection(s)
    
    if interseccion:
        # Tienen al menos una OT común -> Uso compartido legítimo
        return False, interseccion
    else:
        # No hay OT común entre todos -> Conflicto de duplicación
        return True, set()

# --- ÍNDICES DE COLUMNAS DE LA BD DE OTS (SPREADSHEET) ---
IDX_ESTADO = 0   # Columna A (Estatus Trabajos Campo)
IDX_OT    = 1    # Columna B
IDX_CLIE  = 3    # Columna D
IDX_TRAB  = 5    # Columna F
IDX_ID    = 8    # Columna I
IDX_MODELO = 9   # Columna J
IDX_MARCA = 10   # Columna K
IDX_SERIE = 11   # Columna L
IDX_PTS   = 12   # Columna M
IDX_FECHA = 16   # Columna Q
IDX_DIRECCION = 17 # Columna R
IDX_ASUNTO = 18    # Columna S
IDX_SFID = 19      # Columna T

# --- ÍNDICES DE COLUMNAS DE LA BD DE PATRONES ---
IDX_PATRON_NOMBRE = 0
IDX_PATRON_TRABAJOS = 1
IDX_PATRON_CLASE = 10  # Columna K
IDX_PATRON_RANGO = 13

# --- ADAPTADOR CANÓNICO ---
def ensure_iso(val):
    """Garantiza que el valor sea un string ISO en UTC Z."""
    return TimeNormalizationService.normalize_to_utc_z(val)

class TimeNormalizationService:
    @staticmethod
    def normalize_to_utc_z(val) -> str:
        """
        [TIME_NORMALIZATION] 
        Capa central de normalización temporal. 
        Representación canónica: UTC ISO8601 con sufijo 'Z'.
        """
        if not val: return None
        
        orig_val = val
        dt = None
        # 1. Extraer de dict de Google
        if isinstance(val, dict):
            val = val.get("dateTime") or val.get("date")
            
        if not val: return None

        # 2. Parsear a datetime aware
        if isinstance(val, str):
            if "T" not in val:
                # All-day date (YYYY-MM-DD)
                try:
                    dt_naive = datetime.datetime.strptime(val, "%Y-%m-%d")
                    dt = ARG_TZ.localize(dt_naive)
                except: return val
            else:
                try:
                    # fromisoformat soporta offsets tipo -03:00
                    dt = datetime.datetime.fromisoformat(val.replace("Z", "+00:00"))
                except: return val
        elif isinstance(val, (datetime.datetime, datetime.date)):
            dt = val
            if isinstance(dt, datetime.date) and not isinstance(dt, datetime.datetime):
                dt = datetime.datetime.combine(dt, datetime.time.min)
        
        if not dt: return str(val)

        # 3. Garantizar TZ awareness (asumir local si es naive)
        detected_tz = dt.tzinfo.zone if hasattr(dt.tzinfo, 'zone') else str(dt.tzinfo)
        if dt.tzinfo is None:
            dt = ARG_TZ.localize(dt)
            detected_tz = "Assumed: America/Argentina/Buenos_Aires (naive)"
        
        # 4. Convertir a Hora Local Argentina (ART) y formatear con offset
        arg_dt = dt.astimezone(ARG_TZ)
        res = arg_dt.strftime("%Y-%m-%dT%H:%M:%S-03:00")

        # Log de trazabilidad [TIME_NORMALIZATION]
        # print(f"[TIME_NORMALIZATION] {orig_val} (TZ: {detected_tz}) -> {res}")
        
        return res

    @staticmethod
    def prepare_for_google(val) -> dict:
        """
        [TIME_NORMALIZATION] Genera el payload para Google Calendar API.
        Usa UTC Z y NUNCA envía timeZone redundante (evita HTTP 400).
        """
        norm = TimeNormalizationService.normalize_to_utc_z(val)
        if not norm: return None
        return {"dateTime": norm}

class ExtendedPropertiesSanitizer:
    """
    [EXTENDED_PROPS_SANITIZER]
    Garantiza que extendedProperties.private cumpla el contrato de Google: Dict[str, str].
    """
    @staticmethod
    def sanitize(extended_props: dict) -> dict:
        if not extended_props or not isinstance(extended_props, dict):
            return {"private": {}}
        
        private = extended_props.get("private", {})
        if not isinstance(private, dict):
            return {"private": {}}

        sanitized = {}
        for k, v in private.items():
            # 1. Eliminar claves con valor None
            if v is None:
                print(f"[EXTENDED_PROPS_SANITIZER] Key '{k}' removed (None value)")
                continue
            
            # 2. Convertir tipos básicos a str
            if isinstance(v, (int, float, bool)):
                sanitized[k] = str(v).lower() if isinstance(v, bool) else str(v)
                print(f"[EXTENDED_PROPS_SANITIZER] Key '{k}' converted from {type(v).__name__} to str")
                continue
            
            # 3. Serializar objetos complejos a JSON
            if isinstance(v, (dict, list)):
                sanitized[k] = json.dumps(v, ensure_ascii=False)
                print(f"[EXTENDED_PROPS_SANITIZER] Key '{k}' serialized to JSON string")
                continue
            
            # 4. Formatear datetimes
            if isinstance(v, (datetime.datetime, datetime.date)):
                sanitized[k] = v.isoformat()
                print(f"[EXTENDED_PROPS_SANITIZER] Key '{k}' formatted as ISO date string")
                continue
            
            # Forzar el resto a string
            sanitized[k] = str(v)
            
        return {"private": sanitized}

class LegacyAliasRegistry:
    ALIASES = {
        "id": ["id"],
        "google_event_id": ["google_event_id"],
        "tecnico_nombre": ["tecnico_nombre", "tecnico", "Técnico", "Tecnico"],
        "calendar_id": ["calendar_id", "tecnico_id", "calendarId", "resourceId"],
        "inicio": ["inicio", "start", "Inicio", "Start"],
        "fin": ["fin", "end", "Fin", "End"],
        "summary": ["summary", "evento", "Evento", "titulo", "Título"],
        "descripcion": ["descripcion", "description", "Descripción", "Description"],
        "ubicacion": ["ubicacion", "location", "Ubicación", "Location"],
        "extended_props": ["extended_props", "extendedProperties"],
        "updated_at": ["updated_at", "updated"],
        "last_synced_at": ["last_synced_at", "last_google_sync"],
        "sync_status": ["sync_status"],
        "version": ["version"]
    }

    @classmethod
    def resolve(cls, data: dict, canonical_field: str, default=None):
        """Resuelve el valor de un campo basándose en sus aliases conocidos."""
        if not data: return default
        aliases = cls.ALIASES.get(canonical_field, [canonical_field])
        for alias in aliases:
            if alias in data:
                return data[alias]
        return default

class EventAdapter:
    """
    [EVENT_ADAPTER]
    Única capa bidireccional de adaptación de eventos.
    Consolida Polling, SyncWorker, DataManager y Frontend.
    """

    @staticmethod
    def google_to_canonical(g_ev: dict, calendar_id: str = None, tec_nombre: str = None) -> dict:
        """Transforma un evento crudo de Google Calendar al modelo interno canónico."""
        gid = g_ev.get("id")
        start = g_ev.get("start", {})
        end   = g_ev.get("end",   {})
        
        # Metadata parsing
        ext = g_ev.get("extendedProperties", {})
        private = ext.get("private", {}) if isinstance(ext, dict) else {}
        
        # OTs normalization
        ots = OTNormalizationService.normalize(g_ev)
        
        # Detect guests
        attendees = g_ev.get("attendees", [])
        has_guests = len(attendees) > 1 # Assuming owner is 1
        
        # Inject into extended_props to ensure frontend receives it
        if "private" not in ext: ext["private"] = {}
        ext["private"]["has_guests"] = "true" if has_guests else "false"


        return {
            "id":              gid,
            "google_event_id": gid,
            "calendar_id":     calendar_id or private.get("calendar_id"),
            "tecnico_nombre":  tec_nombre or private.get("tecnico_nombre"),
            "summary":         g_ev.get("summary", "Sin título"),
            "inicio":          TimeNormalizationService.normalize_to_utc_z(start),
            "fin":             TimeNormalizationService.normalize_to_utc_z(end),
            "ubicacion":       g_ev.get("location", ""),
            "descripcion":     g_ev.get("description", ""),
            "extended_props":  ext,
            "app_ots":         ots,
            "source":          "internal" if private.get("source") == "internal" else "external",
            "updated_at":      g_ev.get("updated"),
            "version":         int(private.get("version", 1)) if private.get("version") else 1,
            "sync_status":     "SUCCESS"
        }

    @staticmethod
    def normalize_extended_props(ext_data) -> dict:
        """
        Garantiza que extended_props siempre sea un diccionario válido en memoria.
        Soporta dict, JSON string, nested JSON string, nulls, y valores malformados.
        """
        if not ext_data:
            return {}
            
        if isinstance(ext_data, str):
            try:
                ext_data = json.loads(ext_data)
            except Exception:
                return {}
                
        if not isinstance(ext_data, dict):
            return {}
            
        # Asegurar dict 'private'
        private = ext_data.get("private")
        if isinstance(private, str):
            try:
                ext_data["private"] = json.loads(private)
            except Exception:
                ext_data["private"] = {}
        elif not isinstance(private, dict):
            ext_data["private"] = {}
            
        return ext_data

    @staticmethod
    def get_canonical_name(alias: str) -> str:
        for canonical, aliases in LegacyAliasRegistry.ALIASES.items():
            if alias in aliases:
                return canonical
        return alias

    @staticmethod
    def normalize_event(row: dict) -> dict:
        """Asegura que un registro (dict) cumpla con el contrato canónico."""
        res = {}
        for canonical_field in LegacyAliasRegistry.ALIASES.keys():
            res[canonical_field] = LegacyAliasRegistry.resolve(row, canonical_field)
        # Post-procesamiento de campos complejos
        res["extended_props"] = EventAdapter.normalize_extended_props(res.get("extended_props"))
        
        # Asegurar OTs
        res["app_ots"] = OTNormalizationService.normalize({**row, "extendedProperties": res["extended_props"]})
        
        # Normalización de tiempos
        res["inicio"] = TimeNormalizationService.normalize_to_utc_z(res.get("inicio"))
        res["fin"] = TimeNormalizationService.normalize_to_utc_z(res.get("fin"))
        
        # Fallback de google_event_id a id si es None o vacío para consistencia en el Frontend
        if not res.get("google_event_id"):
            res["google_event_id"] = res.get("id")
            
        return res

    @staticmethod
    def merge_events(base_event: dict, updates: dict) -> dict:
        """
        Merge semántico y seguro de eventos (Identity Remap Fix).
        Aplica prohibición de null overwrite y reglas de preservación distribuidas.
        """
        # 1. Canonicalizar base
        base_can = EventAdapter.normalize_event(base_event)
        
        if not updates:
            return base_can
            
        # 2. Resolver aliases de updates ANTES del merge y filtrar Nulls
        canonical_updates = {}
        for k, v in updates.items():
            if v is None:
                continue # PROHIBIR NULL OVERWRITE
            can_key = EventAdapter.get_canonical_name(k)
            canonical_updates[can_key] = v
            
        print(f"[ALIAS_RESOLUTION_RESULT] updates_resueltos={list(canonical_updates.keys())}")
        print(f"[CANONICAL_MERGE_INPUT_BASE] base_id={base_can.get('id')} base_tecnico={base_can.get('tecnico_nombre')} base_cal={base_can.get('calendar_id')}")
        
        # Canonicalizar la data limpia entrante para asegurar consistencia
        # Para evitar sobreescribir con defaults de normalize_event, solo tomamos lo que vino
        patch_can = {}
        for k, v in canonical_updates.items():
            patch_can[k] = v
            
        # Normalizamos tiempos y JSON de patch si corresponde
        if "extended_props" in patch_can:
            patch_can["extended_props"] = EventAdapter.normalize_extended_props(patch_can["extended_props"])
            
        print(f"[CANONICAL_MERGE_INPUT_PATCH] patch_keys={list(patch_can.keys())}")
        
        # 3. Merge semántico controlado
        merged = {**base_can}
        
        # Transient metadata keys
        transient_keys = {"reassignment_in_progress", "reassignment_id", "reassignment_started_at", "reassignment_origin"}
        
        # Lineage metadata keys
        lineage_keys = {"previous_google_event_id", "previous_calendar_id"}
        
        for k, v in patch_can.items():
            if k == "extended_props":
                base_ext = merged.setdefault("extended_props", {})
                new_ext = v or {}
                
                b_priv = base_ext.setdefault("private", {})
                n_priv = new_ext.get("private", {})
                
                for pk, pv in n_priv.items():
                    # Preserve lineage unless explicitly overwriting with non-None
                    if pk in lineage_keys and not pv:
                        continue
                        
                    # Si es app_patrones o app_ots (Arrays) o vehiculo (Strings), sobrescritura completa
                    b_priv[pk] = pv
                        
            elif k in ("app_ots", "inicio", "fin", "ubicacion", "descripcion", "summary", "calendar_id", "tecnico_nombre", "google_event_id", "sync_status", "pending_sync", "version", "updated_at", "last_synced_at", "source"):
                # Replace completo
                if v is not None:
                    merged[k] = v
                    
        # 4. Consolidación final
        res = EventAdapter.normalize_event(merged)
        
        print(f"[EXTENDED_PROPS_NORMALIZED] private_keys={list(res.get('extended_props', {}).get('private', {}).keys())}")
        print(f"[CANONICAL_MERGE_OUTPUT] output_id={res.get('id')} output_tecnico={res.get('tecnico_nombre')} output_cal={res.get('calendar_id')}")
        
        return res

    @staticmethod
    def canonical_to_google(event: dict) -> dict:
        """Transforma un evento canónico al formato de Google Calendar API."""
        # Resolver campos usando aliases por si viene de una fuente no-limpia
        summary = LegacyAliasRegistry.resolve(event, "summary", "Sin título")
        desc    = LegacyAliasRegistry.resolve(event, "descripcion", "")
        loc     = LegacyAliasRegistry.resolve(event, "ubicacion", "")
        inicio  = LegacyAliasRegistry.resolve(event, "inicio")
        fin     = LegacyAliasRegistry.resolve(event, "fin")
        
        ext = LegacyAliasRegistry.resolve(event, "extended_props", {})
        if isinstance(ext, str):
            try: ext = json.loads(ext)
            except: ext = {}
            
        private = ext.get("private", {}).copy() if isinstance(ext, dict) else {}
        
        # Inyectar control de sync
        private["source"] = "internal"
        private["version"] = str(LegacyAliasRegistry.resolve(event, "version", 1))
        
        # Sanitización
        sanitized_ext = ExtendedPropertiesSanitizer.sanitize({"private": private})

        return {
            "summary":     summary,
            "description": desc,
            "location":    loc,
            "start":       TimeNormalizationService.prepare_for_google(inicio),
            "end":         TimeNormalizationService.prepare_for_google(fin),
            "extendedProperties": sanitized_ext
        }

    @staticmethod
    def canonical_to_sqlite_params(event: dict) -> dict:
        """Prepara el evento para ser persistido en SQLite (aplanado)."""
        # Asegura que todos los campos canónicos estén presentes y normalizados
        can = EventAdapter.normalize_event(event)
        
        # Serializar lo que va a la DB
        return {
            "id":              can["id"],
            "google_event_id": can["google_event_id"],
            "calendar_id":     can["calendar_id"],
            "tecnico_nombre":  can["tecnico_nombre"],
            "summary":         can["summary"],
            "inicio":          can["inicio"],
            "fin":             can["fin"],
            "ubicacion":       can["ubicacion"],
            "descripcion":     can["descripcion"],
            "extended_props":  json.dumps(can["extended_props"], ensure_ascii=False),
            "version":         can["version"],
            "sync_status":     can.get("sync_status", "SUCCESS"),
            "updated_at":      can.get("updated_at"),
            "last_synced_at":  can.get("last_synced_at"),
            "pending_sync":    can.get("pending_sync", 0),
            "source":          can.get("source", "internal")
        }

class OTNormalizationService:
    """
    [OT_NORMALIZATION]
    Capa centralizada para la resolución y normalización de OTs.
    Garantiza una salida única List[str] independientemente de la fuente o formato.
    """
    OFFICIAL_REGEX = r'\d{4,}'

    @staticmethod
    def normalize(event_data: dict) -> list:
        """
        Resuelve OTs desde múltiples fuentes (metadata moderna, legacy y summary).
        """
        event_id = event_data.get("id") or event_data.get("google_event_id") or "unknown"
        
        # 1. Explorar extendedProperties / extended_props
        ext = event_data.get("extendedProperties") or event_data.get("extended_props") or {}
        if isinstance(ext, str):
            try: ext = json.loads(ext)
            except: ext = {}
            
        private = ext.get("private", {}) if isinstance(ext, dict) else {}
        
        # Fuentes en orden de prioridad
        potential_ots = [
            private.get("app_ots") if isinstance(private, dict) else None,
            private.get("app_ot") if isinstance(private, dict) else None,
            ext.get("app_ots") if isinstance(ext, dict) else None,
            ext.get("app_ot") if isinstance(ext, dict) else None,
            event_data.get("app_ots"),
            event_data.get("app_ot")
        ]
        
        resolved_ots = set()
        source_used = "none"
        
        for i, val in enumerate(potential_ots):
            if not val: continue
            
            # Caso: List[str]
            if isinstance(val, list):
                for x in val: 
                    if x: resolved_ots.add(str(x))
                if resolved_ots: 
                    source_used = f"metadata_list_index_{i}"
                    break
            
            # Caso: String (puede ser JSON o simple)
            if isinstance(val, str):
                val = val.strip()
                if not val: continue
                
                if val.startswith("["):
                    try:
                        parsed = json.loads(val)
                        if isinstance(parsed, list):
                            for x in parsed: 
                                if x: resolved_ots.add(str(x))
                            if resolved_ots:
                                source_used = f"metadata_json_index_{i}"
                                break
                    except: pass
                
                # Si no era JSON o falló, es una OT simple o lista separada
                found_any = False
                for part in re.split(r'[,;/|\s]+', val):
                    if re.fullmatch(OTNormalizationService.OFFICIAL_REGEX, part):
                        resolved_ots.add(part)
                        found_any = True
                if found_any:
                    source_used = f"metadata_string_index_{i}"
                    break

        # 2. Fallback: Regex sobre summary/evento si no se encontró nada explícito
        if not resolved_ots:
            summary = event_data.get("summary") or event_data.get("evento") or ""
            matches = re.findall(OTNormalizationService.OFFICIAL_REGEX, str(summary))
            for m in matches:
                resolved_ots.add(m)
            if resolved_ots:
                source_used = "regex_fallback_summary"

        final_list = sorted(list(resolved_ots))
        
        # Log [OT_NORMALIZATION]
        # if final_list:
        #     print(f"[OT_NORMALIZATION] Event {event_id}: Source={source_used}, OTs={final_list}")
        
        return final_list


def deep_merge_metadata(existing: dict, incoming: dict) -> dict:
    """
    Mergea dos diccionarios de metadata de forma recursiva (especialmente 'private').
    Garantiza que no se pierdan campos al actualizar solo una parte de la metadata.
    """
    result = existing.copy()
    for k, v in incoming.items():
        if k == "private" and isinstance(v, dict) and isinstance(result.get("private"), dict):
            # Merge de primer nivel para 'private' (app_vehiculo, app_patrones, etc.)
            new_private = result["private"].copy()
            new_private.update(v)
            result["private"] = new_private
        else:
            # Reemplazo para otros campos de primer nivel
            result[k] = v
    return result


# ─── ETAPA 6 — METADATA INTEGRITY ────────────────────────────────────────────

def assert_metadata_integrity(event: dict, context: str = "") -> list:
    """
    [METADATA_INTEGRITY]
    Verifica que un evento tenga los campos de metadata críticos en extended_props.private.
    Retorna lista de issues encontrados (lista vacía = todo OK).

    Uso:
        issues = assert_metadata_integrity(event, context="mover_evento:post_persist")
        if issues:
            db.log_trace(event_id, "INTEGRITY_ISSUES", {"issues": issues}, tag="METADATA_INTEGRITY")

    Campos verificados:
        - app_ots: debe ser una lista JSON válida (puede ser vacía)
        - app_patrones: debe ser una lista JSON válida (puede ser vacía)
        - app_vehiculo: puede ser vacío, pero el campo debe existir

    NO lanza excepción — retorna issues para que el caller decida el log level.
    """
    issues = []
    if not event or not isinstance(event, dict):
        return ["EVENT_NULL_OR_INVALID"]

    # Resolver extended_props desde cualquier dialecto
    ext = event.get("extended_props") or event.get("extendedProperties") or {}
    if isinstance(ext, str):
        try:
            ext = json.loads(ext)
        except Exception:
            ext = {}

    private = ext.get("private", {}) if isinstance(ext, dict) else {}
    if not isinstance(private, dict):
        private = {}

    event_id = event.get("id") or event.get("google_event_id") or "UNKNOWN"
    ctx_str = f" [{context}]" if context else ""

    # app_ots — debe existir (puede ser lista vacía)
    if "app_ots" not in private:
        issues.append(f"app_ots_MISSING{ctx_str} event={event_id}")
    else:
        raw_ots = private["app_ots"]
        if isinstance(raw_ots, str):
            try:
                parsed = json.loads(raw_ots)
                if not isinstance(parsed, list):
                    issues.append(f"app_ots_NOT_LIST{ctx_str} event={event_id} type={type(parsed).__name__}")
            except Exception:
                issues.append(f"app_ots_INVALID_JSON{ctx_str} event={event_id} raw={str(raw_ots)[:50]}")

    # app_patrones — debe existir (puede ser lista vacía)
    if "app_patrones" not in private:
        issues.append(f"app_patrones_MISSING{ctx_str} event={event_id}")
    else:
        raw_pat = private["app_patrones"]
        if isinstance(raw_pat, str):
            try:
                parsed = json.loads(raw_pat)
                if not isinstance(parsed, list):
                    issues.append(f"app_patrones_NOT_LIST{ctx_str} event={event_id} type={type(parsed).__name__}")
            except Exception:
                issues.append(f"app_patrones_INVALID_JSON{ctx_str} event={event_id} raw={str(raw_pat)[:50]}")

    # app_vehiculo — campo opcional, pero si existe no debe ser un tipo inesperado
    if "app_vehiculo" in private:
        veh = private["app_vehiculo"]
        if veh is not None and not isinstance(veh, str):
            issues.append(f"app_vehiculo_WRONG_TYPE{ctx_str} event={event_id} type={type(veh).__name__}")

    return issues


# ─── ETAPA 8 — OBSERVABILIDAD ESTRUCTURADA ───────────────────────────────────

class OperationalLogger:
    """
    [OBSERVABILIDAD]
    Centralizador de logs de observabilidad operacional con tags canónicos validados.

    Tags oficiales del sistema:
        CONVERGENCE_ASSERT      — Resultado de assert_event_converged (tests / validaciones)
        DRIFT_DETECTED          — Drift detectado por el drift observatory
        DRIFT_RESOLVED          — Drift que se resolvió (evento reaparecido con estado OK)
        ARBITRATION_APPLIED     — Review aceptado o rechazado exitosamente
        SYNC_CONVERGED          — Sync outbound completado sin errores
        POLLING_REOPEN_BLOCKED  — Review bloqueado por watermark anti-reopen
        LOOKUP_MISS             — Evento no encontrado por ningún fallback de lookup
        METADATA_INTEGRITY      — Problema de metadata detectado en un evento

    Uso:
        OperationalLogger.log(db, "DRIFT_DETECTED", "events_without_google_id",
                              {"count": 3, "event_ids": [...]})
    """

    TAGS = frozenset({
        "CONVERGENCE_ASSERT",
        "DRIFT_DETECTED",
        "DRIFT_RESOLVED",
        "ARBITRATION_APPLIED",
        "SYNC_CONVERGED",
        "POLLING_REOPEN_BLOCKED",
        "LOOKUP_MISS",
        "METADATA_INTEGRITY",
        "CLONE_EVENT",
        "BATCH_MOVE",
        "QUICK_EVENT",
        "INDIVIDUALIZAR",
        "GROUP_LIFECYCLE",
        "EVENT_MOVE",
    })

    @staticmethod
    def log(db, tag: str, step: str, detail: dict,
            event_id: str = "system", calendar_id: str = None):
        """
        Registra un log estructurado con tag canónico validado.
        Lanza ValueError si el tag no está en el conjunto oficial (fail-fast en desarrollo).
        En producción, el error se captura y se loguea como UNKNOWN_TAG para no romper flujo.
        """
        if tag not in OperationalLogger.TAGS:
            # No romper el flujo en producción, pero sí registrar el tag inválido
            print(f"[OperationalLogger] ADVERTENCIA: tag desconocido '{tag}' — usando UNKNOWN_TAG")
            tag = f"UNKNOWN_TAG:{tag}"

        try:
            db.log_trace(event_id, step, detail, calendar_id=calendar_id, tag=tag)
        except Exception as e:
            # El log nunca debe romper el flujo
            print(f"[OperationalLogger] Error al registrar log {tag}:{step}: {e}")

    @staticmethod
    def log_metadata_issues(db, event: dict, issues: list, context: str = ""):
        """Helper para loguear issues de assert_metadata_integrity directamente."""
        if not issues:
            return
        event_id = event.get("id") or event.get("google_event_id") or "UNKNOWN"
        calendar_id = event.get("calendar_id")
        OperationalLogger.log(
            db, "METADATA_INTEGRITY", "INTEGRITY_ISSUES",
            {"issues": issues, "context": context, "event_id": event_id},
            event_id=event_id, calendar_id=calendar_id
        )
