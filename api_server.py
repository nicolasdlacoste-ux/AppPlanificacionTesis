from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from typing import Optional, List
import uvicorn
import os
import json
import datetime
import pandas as pd
import threading
import time

import uuid
import re
import googleapiclient.errors
import sys
if sys.stdout is not None and getattr(sys.stdout, 'encoding', None) != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

import utils
import engine
from data_manager import DataManager
import extractor
from sync_manager import SyncWorker
from utils import EventAdapter

def get_resource_path(relative_path):
    """Obtiene la ruta absoluta para recursos (válido para desarrollo y .exe)"""
    if getattr(sys, 'frozen', False):
        # PyInstaller crea una carpeta temporal en sys._MEIPASS
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

app = FastAPI(title="Akrimet Planner API v2")
db = DataManager()

# ── BUSINESS DAY UTILS ────────────────────────────────────────

def get_next_business_day(start_date: datetime.date) -> str:
    """Return the next business day as ISO string, considering holidays from app_config.

    Args:
        start_date: The date from which to calculate the next business day.
    Returns:
        ISO formatted date string (YYYY-MM-DD) of the next business day.
    """
    # Gather holidays from app_config (keys are date strings)
    holidays = []
    try:
        cfg = db.get_app_config()
        hol_dict = cfg.get("holidays", {}) or {}
        for d in hol_dict.keys():
            try:
                holidays.append(datetime.datetime.strptime(d, "%Y-%m-%d").date())
            except Exception:
                continue
    except Exception:
        holidays = []
    # Use pandas CustomBusinessDay to compute next business day
    cbd = pd.tseries.offsets.CustomBusinessDay(holidays=holidays)
    next_bd = (pd.Timestamp(start_date) + cbd).date()
    return next_bd.isoformat()

# ── PUBLIC ENDPOINT FOR TARJETA DE SALIDA ──────────────────────────────
@app.get("/api/tarjeta-salida")
async def tarjeta_salida(date: Optional[str] = Query(None)):
    """Public endpoint that returns tarjeta de salida data.

    If *date* is not provided, the next business day (considering holidays) is used.
    """
    if date is None:
        today = datetime.date.today()
        date = get_next_business_day(today)
    return await obtener_tarjetas_salida(fecha=date)


# ── SYNC WORKER ───────────────────────────────────────────────
# Instancia única del worker (hilo daemon que procesa la sync_queue)
sync_worker = SyncWorker(db=db, extractor_module=extractor)

# ── POLLING MANAGER ───────────────────────────────────────────
from poll_manager import PollingManager
from hydration_service import HydrationService, RealOtRepository

def _make_google_service():
    """Factory: retorna un servicio autenticado de Google Calendar API."""
    svc_cal, svc_sheets = extractor._safe_get_google_services()
    return svc_cal

ot_repo = RealOtRepository(db)
hydrator = HydrationService(ot_repo)
poll_manager = PollingManager(
    db=db, 
    google_service_factory=_make_google_service,
    hydration_service=hydrator
)
from poll_diagnostics import PollingDiagnosticReporter
poll_reporter = PollingDiagnosticReporter(
    db=db,
    google_service_factory=_make_google_service
)

from drift_manager import DriftManagerService
from group_integrity import validate_group_integrity
from group_operations import GroupOperationContext, acquire_group_lock, release_group_lock, is_group_locked

observatory = DriftManagerService(db)
observatory.set_google_factory(_make_google_service)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── LOGICA DE APAGADO AUTOMÁTICO (Heartbeat) ──
_last_heartbeat = time.time() + 60.0  # Margen de 1 min al arrancar

def _watchdog_shutdown():
    global _last_heartbeat
    while True:
        time.sleep(10)
        # Si han pasado más de 300s (5 min) sin pulso, cerramos el proceso completo
        # Aumentado de 30s a 300s para evitar cierres por throttling del navegador en segundo plano
        if time.time() - _last_heartbeat > 300:
            print("\n[!] Heartbeat perdido (ventana cerrada). Finalizando aplicación...")
            os._exit(0)

# Iniciar hilos de monitoreo
threading.Thread(target=_watchdog_shutdown, daemon=True).start()

# Arrancar el SyncWorker en background (procesa la queue cada 30s)
sync_worker.start()
# NOTA: poll_manager.start() se llama explícitamente vía /api/poll/start


# ── AUTO-INICIO DEL POLLING ───────────────────────────────────
@app.on_event("startup")
async def on_startup():
    """Inicia el ciclo de polling automáticamente al arrancar la app."""
    import asyncio
    await asyncio.sleep(2)   # pequeña espera para que la DB quede lista
    ok = poll_manager.start(sync_worker)
    if ok:
        print("[POLL] Polling iniciado automáticamente al arrancar.")
    else:
        print("[POLL] Checklist falló — polling no iniciado automáticamente. Usar /api/poll/start manualmente.")

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

# generar_descripcion_enriquecida vive en utils.py (disponible también para group_operations)
from utils import generar_descripcion_enriquecida  # noqa: F401 re-export

def _is_complex_event(ev: dict) -> bool:
    """Determina si un evento es complejo (multidia o tiene invitados)."""
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
            
    return False

def _limpiar_cache_eventos():
    """Construye el diccionario tech_events que espera engine.py desde la DB."""
    eventos = db.obtener_eventos_dict()
    tech_events = {}

    for ev in eventos:
        tech = str(ev.get("tecnico_nombre") or ev.get("tecnico") or "").strip()
        if not tech:
            continue
        if tech not in tech_events:
            tech_events[tech] = {}

        start_str = ev.get("inicio", "")
        end_str = ev.get("fin", "")
        summary = str(ev.get("summary") or ev.get("evento") or "").strip()

        if not start_str or not end_str:
            continue

        # [OT_NORMALIZATION] Usar el normalizador canónico centralizado
        canon_ots = utils.OTNormalizationService.normalize(ev)
        ot_label = canon_ots[0] if canon_ots else (summary.split('-')[0].strip() if '-' in summary else summary)
        es_ot = len(canon_ots) > 0 or "RESERVA" in summary.upper()
        es_todo_el_dia = "T" not in start_str

        # Parsear extended_props
        ext_props = ev.get("extended_props") or ev.get("extendedProperties") or {}
        if isinstance(ext_props, str):
            try:
                ext_props = json.loads(ext_props)
            except Exception:
                ext_props = {}

        try:
            if es_todo_el_dia:
                start_date = datetime.datetime.strptime(start_str, "%Y-%m-%d").date()
                end_date = datetime.datetime.strptime(end_str, "%Y-%m-%d").date()
                dias = max(1, (end_date - start_date).days)
                for i in range(dias):
                    d = start_date + datetime.timedelta(days=i)
                    dk = d.strftime("%Y-%m-%d")
                    tech_events[tech].setdefault(dk, []).append({
                        "sort": 700, "sort_end": 1600, "text": f"07:00-16:00 | {ot_label}",
                        "horas": 0.0 if d.weekday() >= 5 else 9.0, "es_ot": es_ot,
                        "original_text": summary,
                        "extendedProperties": ext_props,
                        "id": ev.get("id"), "calendar_id": ev.get("calendar_id"),
                        "inicio": start_str, "fin": end_str,
                        "description": ev.get("descripcion", "")
                    })
            else:
                start_dt = datetime.datetime.fromisoformat(start_str)
                end_dt = datetime.datetime.fromisoformat(end_str)
                start_date = start_dt.date()
                end_date = end_dt.date()
                dias = (end_date - start_date).days
                for i in range(dias + 1):
                    d = start_date + datetime.timedelta(days=i)
                    dk = d.strftime("%Y-%m-%d")
                    is_weekend = d.weekday() >= 5
                    if i == 0 and dias == 0:
                        t1 = start_dt.strftime("%H:%M")
                        t2 = end_dt.strftime("%H:%M")
                        desc = f"{t1}-{t2} | {ot_label}"
                        sort_val = int(start_dt.strftime("%H%M"))
                        sort_end_val = int(end_dt.strftime("%H%M"))
                        h = 0.0 if is_weekend else max(0.0, min(16.0, end_dt.hour + end_dt.minute / 60) - max(7.0, start_dt.hour + start_dt.minute / 60))
                    else:
                        desc = f"{start_dt.strftime('%H:%M')}-... | {ot_label}" if i == 0 else (f"...-{end_dt.strftime('%H:%M')} | {ot_label}" if i == dias else f"Día entero | {ot_label}")
                        sort_val = int(start_dt.strftime("%H%M")) if i == 0 else 0
                        sort_end_val = int(end_dt.strftime("%H%M")) if i == dias else 2359
                        h = 0.0 if is_weekend else 9.0

                    tech_events[tech].setdefault(dk, []).append({
                        "sort": sort_val, "sort_end": sort_end_val, "text": desc,
                        "horas": h, "es_ot": es_ot, "original_text": summary,
                        "extendedProperties": ext_props,
                        "id": ev.get("id"), "calendar_id": ev.get("calendar_id"),
                        "inicio": start_str, "fin": end_str,
                        "description": ev.get("descripcion", "")
                    })
        except Exception as e:
            print(f"Error procesando evento {summary}: {e}")

    for t in tech_events:
        for d in tech_events[t]:
            tech_events[t][d].sort(key=lambda x: (x["sort"], x.get("sort_end", 9999)))

    return tech_events

async def sync_group_events(grupo_id: str, svc_cal=None):
    """
    [LEGACY_REMOVED] Sincronización directa de grupos eliminada.
    Ahora se utiliza actualizar_titulos_grupo_local() + SyncWorker.
    """
    print(f"[OUTBOUND_MUTATION] sync_group_events({grupo_id}): No-op. Redirigido a SyncWorker.")
    return
    """
    Sincroniza todos los eventos de un grupo para que tengan el mismo título,
    descripción y metadatos (vehículo, patrones, etc).
    Usa el objeto 'grupo' en DB como fuente de verdad para metadatos compartidos.
    """
    if not svc_cal:
        svc_cal, _ = await run_in_threadpool(extractor._safe_get_google_services)
    
    grupo = db.obtener_grupo(grupo_id)
    if not grupo: return
    
    # 1. Obtener iniciales para el tag del título
    tecs_db = db.obtener_tecnicos()
    map_nombre_correo = {t['nombre']: t['correo'] for t in tecs_db}
    map_nombre_init = {t['nombre']: t['iniciales'] for t in tecs_db}
    
    inits = []
    for n in grupo['tecnico_nombres']:
        if n in map_nombre_init:
            inits.append(map_nombre_init[n])
    tag = "/".join(sorted(list(set(inits)))) if len(inits) > 1 else ""
    
    # 2. Obtener un evento base para el título base y descripción base
    base_ev = None
    for i, eid in enumerate(grupo['event_ids']):
        try:
            tec_name = grupo['tecnico_nombres'][i]
            cal_t = map_nombre_correo.get(tec_name)
            if cal_t:
                base_ev = svc_cal.events().get(calendarId=cal_t, eventId=eid).execute()
                break
        except: continue
    if not base_ev: return

    # 3. Preparar metadatos (Fuente de verdad: DB 'grupo')
    pats = grupo.get('patrones', [])
    veh = grupo.get('vehiculo', '')
    
    original_summary = base_ev.get('summary', '')
    cleaned_title = re.sub(r'\s*-\s*[A-Z0-9/]+\s*$', '', original_summary).strip()
    new_title = f"{cleaned_title} - {tag}" if tag else cleaned_title
    
    # Combinar metadata existente con la del grupo
    metadata = base_ev.get('extendedProperties', {}).get('private', {}).copy()
    metadata['grupo_id'] = grupo_id
    metadata['tecnico_nombres'] = json.dumps(grupo['tecnico_nombres'])
    metadata['event_ids'] = json.dumps(grupo['event_ids'])
    metadata['app_patrones'] = json.dumps(pats)
    metadata['app_vehiculo'] = veh
    
    base_desc = base_ev.get('description', '')
    all_pats = db.obtener_patrones()
    new_desc = generar_descripcion_enriquecida(base_desc, pats, veh, all_pats)
    
    # 4. Actualizar todos los eventos (Usar threadpool para no bloquear el event loop)
    async def _patch_one(cal_id, eid, body):
        try:
            await run_in_threadpool(svc_cal.events().patch(calendarId=cal_id, eventId=eid, body=body).execute)
            db.actualizar_titulo_evento(eid, body['summary'])
        except Exception as e:
            print(f"[sync_group_events] Error patch {eid}: {e}")

    for i, eid in enumerate(grupo['event_ids']):
        tec_name = grupo['tecnico_nombres'][i]
        cal_t = map_nombre_correo.get(tec_name)
        if not cal_t: continue
        
        body = {
            'summary': new_title,
            'description': new_desc,
            'extendedProperties': {'private': metadata}
        }
        await _patch_one(cal_t, eid, body)
    
    # Asegurar que el grupo en DB esté actualizado
    db.crear_o_actualizar_grupo(grupo)



async def update_group_title(grupo_id: str):
    grupo = db.obtener_grupo(grupo_id)
    if not grupo: return
    
    tecnicos = db.obtener_tecnicos()
    map_correo_init = {t['correo']: t.get('iniciales', '') for t in tecnicos}

    # Usar format_group_summary para garantizar separador canónico " + " (no "/")
    from utils import format_group_summary, get_ot_base_from_event
    ini_list = [map_correo_init.get(c, '') for c in grupo.get('calendar_ids', []) if c]
    
    # Fallback si no hay calendar_ids (datos legacy)
    if not ini_list:
        map_nombre_init = {t['nombre']: t.get('iniciales', '') for t in tecnicos}
        ini_list = [map_nombre_init.get(n, '') for n in grupo.get('tecnico_nombres', []) if n]

    
    eventos_dict = db.obtener_eventos_dict()
    map_id_ev = {e['id']: e for e in eventos_dict}
    
    def _safe_ext(ev):
        """Parsea extendedProperties defensivamente (puede venir como str desde SQLite)."""
        ext = ev.get('extendedProperties') or ev.get('extended_props') or {}
        if isinstance(ext, str):
            try: ext = json.loads(ext)
            except: ext = {}
        if not isinstance(ext, dict): ext = {}
        priv = ext.get('private') or {}
        if isinstance(priv, str):
            try: priv = json.loads(priv)
            except: priv = {}
        if not isinstance(priv, dict): priv = {}
        return ext, priv

    # 1. Unificar metadata
    all_ots = set()
    all_pats = set()
    vehiculo_lider = None
    
    for eid in grupo['event_ids']:
        ev = map_id_ev.get(eid)
        if not ev: continue
        _, priv = _safe_ext(ev)
        
        # OTs
        ev_ots = priv.get('app_ots', "[]")
        if isinstance(ev_ots, str):
            try: ev_ots = json.loads(ev_ots)
            except: ev_ots = []
        if isinstance(ev_ots, list):
            for o in ev_ots: all_ots.add(o)
            
        # Patrones
        ev_pats = priv.get('app_patrones', "[]")
        if isinstance(ev_pats, str):
            try: ev_pats = json.loads(ev_pats)
            except: ev_pats = []
        if isinstance(ev_pats, list):
            for p in ev_pats: all_pats.add(p)
            
        if priv.get('app_vehiculo') and not vehiculo_lider:
            vehiculo_lider = priv.get('app_vehiculo')
            
    # 2. Calcular título canónico usando format_group_summary (separador " + ")
    ref_ev = next((map_id_ev.get(eid) for eid in grupo['event_ids'] if map_id_ev.get(eid)), None)
    ot_base = get_ot_base_from_event(ref_ev) if ref_ev else ""
    new_title = format_group_summary(ot_base, ini_list) if ot_base else ""

    # 3. Actualizar cada miembro si el título cambió
    for eid in grupo['event_ids']:
        ev = map_id_ev.get(eid)
        if not ev: continue
        
        titulo_orig = ev.get('evento') or ev.get('summary') or ''
        if new_title and new_title != titulo_orig:
            db.actualizar_titulo_evento(eid, new_title)
            
            cal_id = ev.get('calendar_id', '')
            tec = ev.get('tecnico_nombre') or ev.get('tecnico') or ''
            
            db.log_trace(eid, "mutation_created", {
                "type": "UPDATE",
                "origin": "update_group_title",
                "new_title": new_title
            }, calendar_id=cal_id, tag="OUTBOUND_MUTATION")
            db.enqueue_sync(eid, cal_id, tec, "UPDATE", origin="group_update")

async def _auto_agrupar_evento(event_id, cal_id, tec_nombre, fecha, ots, svc_cal=None):
    """
    Busca otros eventos en el mismo día con la misma OT para formar un grupo automáticamente.
    Prioriza la consistencia en SQLite y evita llamadas innecesarias a Google.
    """
    if not ots: return
    
    # 1. Buscar eventos en SQLite para ese día con alguna de esas OTs
    candidatos = []
    eventos_dia = db.obtener_eventos_por_fecha(fecha)
    
    for ev in eventos_dia:
        if (ev.get("google_event_id") or ev.get("id")) == event_id: continue
        
        # [EVENT_ADAPTER] Normalizar evento candidato para acceso canónico a extended_props.private
        ev_norm = utils.EventAdapter.normalize_event(ev)
        ev_ots = list(utils.extraer_ots(ev_norm.get('summary') or ''))
        if any(ot in ev_ots for ot in ots):
            candidatos.append(ev_norm)
            
    if not candidatos: return
    
    # 2. Decidir si unirse a un grupo existente o crear uno nuevo
    target_grupo_id = None
    for c in candidatos:
        props = c.get('extended_props', {})
        gid = props.get('private', {}).get('grupo_id')
        if gid:
            target_grupo_id = gid
            break
            
    if target_grupo_id:
        # Unirse a grupo existente
        grupo = db.obtener_grupo(target_grupo_id)
        if grupo:
            # [LEGACY_EVENT_ID] Usando google_event_id para membresía de grupo
            if event_id not in grupo['event_ids']:
                grupo['event_ids'].append(event_id)
                grupo['tecnico_nombres'].append(tec_nombre)
                db.crear_o_actualizar_grupo(grupo)
                
                # Actualizar metadatos del evento recién unido para que tenga el grupo_id
                db.vincular_evento_a_grupo(event_id, target_grupo_id)
                
                await actualizar_titulos_grupo_local(target_grupo_id)
                # Opcional: sync_group_events en background si svc_cal está
    else:
        # Crear grupo nuevo con el primero que encontramos
        c = candidatos[0]
        c_id = c['id']
        c_tec = c.get('tecnico_nombre') or c.get("tecnico")
        c_props = c.get('extended_props', {})
        c_vehiculo = c_props.get('private', {}).get('app_vehiculo') or ""
        
        new_gid = str(uuid.uuid4())
        db.crear_o_actualizar_grupo({
            "grupo_id": new_gid,
            "ot_nro": ots[0],
            "fecha": fecha,
            "event_ids": [c_id, event_id],
            "tecnico_nombres": [c_tec, tec_nombre],
            "vehiculo": c_vehiculo,
            "patrones": []
        })
        
        # Vincular ambos eventos en SQLite (guarda el grupo_id en sus extendedProperties)
        db.vincular_evento_a_grupo(c_id, new_gid)
        db.vincular_evento_a_grupo(event_id, new_gid)
        
        await actualizar_titulos_grupo_local(new_gid)




@app.post("/api/heartbeat")
async def receive_heartbeat():
    global _last_heartbeat
    _last_heartbeat = time.time()
    return {"status": "alive", "last_mutation_time": db.last_mutation_time}


# ─────────────────────────────────────────────
# AUTENTICACIÓN / IDENTIDAD
# ─────────────────────────────────────────────

@app.get("/api/auth/me")
async def get_auth_me():
    """
    Retorna el perfil del usuario autenticado.
    Primero busca en caché (SQLite), si no existe lo consulta a Google y lo guarda.
    """
    try:
        # 1. Buscar en caché local
        cached = db.get_metadato("user_profile")
        if cached:
            return json.loads(cached)

        # 2. Consultar a Google y cachear
        svc_cal, _ = await run_in_threadpool(extractor._safe_get_google_services)
        profile = extractor.get_current_user_profile(svc_cal)

        db.set_metadato("user_profile", json.dumps(profile))
        return profile
    except Exception as e:
        # Si no hay token aún, retornar estado no autenticado (no error 500)

        return {"email": "", "nombre": "", "autenticado": False, "error": str(e)}


@app.post("/api/auth/logout")
async def auth_logout():
    """
    Desconecta la cuenta de Google: elimina token.json y borra el caché del perfil.
    La próxima sincronización pedirá autorización nuevamente.
    """
    try:
        token_path = extractor.TOKEN_PATH_DEFAULT
        if os.path.exists(token_path):
            os.remove(token_path)
        db.set_metadato("user_profile", "")

        return {"status": "ok", "message": "Sesión cerrada. Sincroniza para volver a conectar."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def check_authorization():
    """
    Verifica si el usuario actual está en la lista de authorized_users del app_config.
    Si la lista está vacía, no se permite la edición (seguridad por defecto).

    [OFFLINE_FIX] Si Google no está disponible (sin red), usa el perfil en caché (SQLite)
    para no bloquear operaciones locales como Accept Review.
    """
    app_config = db.get_app_config()
    authorized = app_config.get("authorized_users", [])

    # 1. Normalizar lista de autorizados para comparación robusta
    authorized_norm = [utils.normalizar_texto(u) for u in authorized if u]

    if not authorized_norm:
        raise HTTPException(status_code=403, detail="No hay usuarios autorizados configurados. Contacte al administrador.")

    try:
        svc_cal, _ = await run_in_threadpool(extractor._safe_get_google_services)
        current_email = await run_in_threadpool(extractor.obtener_email_usuario, svc_cal)
        
        # 2. Manejar email vacío (error de Google o falta de identidad) como 403 explícito
        if not current_email:
            raise HTTPException(status_code=403, detail="No se pudo obtener la identidad del usuario (Google). Verifique su conexión y sesión.")
        
        # 3. Normalizar email actual para la comparación
        email_norm = utils.normalizar_texto(current_email)
        
        if email_norm in authorized_norm:
            return True
            
        # 4. Error descriptivo para facilitar el diagnóstico
        raise HTTPException(status_code=403, detail=f"Usuario {current_email} no tiene permisos de edición. Verifique la pestaña de seguridad en Configuración.")
        
    except Exception as e:
        if isinstance(e, HTTPException): raise e

        # [OFFLINE_FIX] Detectar errores de red/conectividad con Google
        err_str = str(e).lower()
        _network_keywords = ("unable to find the server", "network", "connection",
                             "timeout", "name or service not known", "getaddrinfo",
                             "socket", "ssl", "eof", "timed out")
        is_network_error = any(kw in err_str for kw in _network_keywords)

        if is_network_error:
            # Intentar con el perfil en caché (guardado en el último login exitoso)
            try:
                cached = db.get_metadato("user_profile")
                if cached:
                    profile = json.loads(cached)
                    email_cached = profile.get("email", "")
                    if email_cached:
                        email_norm_cached = utils.normalizar_texto(email_cached)
                        if email_norm_cached in authorized_norm:
                            print(f"[AUTH] Google no disponible — autorizado por caché: {email_cached}")
                            return True
                        raise HTTPException(
                            status_code=403,
                            detail=f"[OFFLINE] Usuario {email_cached} (caché) no está en la lista de autorizados."
                        )
            except HTTPException:
                raise
            except Exception:
                pass  # Si el caché también falla, caer al error de red

            raise HTTPException(
                status_code=503,
                detail="Google Calendar no disponible y no hay perfil en caché. "
                       "Reconecta a Google una vez que haya conexión."
            )

        # Error no relacionado a red → 500 genérico
        raise HTTPException(status_code=500, detail=f"Error de validación de seguridad: {str(e)}")


@app.get("/api/config")
async def get_config():
    """Retorna la configuración actual (ocultando el PIN por seguridad)."""
    config = db.get_app_config()
    # No enviamos el PIN al frontend en la carga inicial
    config.pop("pin", None)
    return config

class PinRequest(BaseModel):
    pin: str

@app.post("/api/config/verify-pin")
async def verify_pin(req: PinRequest):
    """Verifica si el PIN ingresado es correcto."""
    config = db.get_app_config()
    is_valid = (req.pin == config.get("pin", "2302"))
    return {"valid": is_valid}

class PollRoutingConfig(BaseModel):
    REMOTE_CREATE: str
    FIELD_CHANGE: str
    FIELD_CHANGE_SAFE: str = "AUTO_APPLY"
    REMOTE_DELETE: str

@app.get("/api/config/poll-routing")
async def get_poll_routing():
    """Obtiene la configuración de ruteo de polling."""
    import json
    val = db.get_metadato("poll_routing_config")
    if not val:
        return {
            "REMOTE_CREATE": "INBOX",
            "FIELD_CHANGE": "INBOX",
            "FIELD_CHANGE_SAFE": "AUTO_APPLY",
            "REMOTE_DELETE": "INBOX"
        }
    return json.loads(val)

@app.post("/api/config/poll-routing")
async def save_poll_routing(req: PollRoutingConfig):
    """Guarda la configuración de ruteo de polling."""
    import json
    db.set_metadato("poll_routing_config", json.dumps(req.dict()))
    return {"status": "ok"}

@app.post("/api/config/poll-routing/apply-retroactive")
async def apply_retroactive_poll_routing():
    """Applies current routing rules to all PENDING items in the review queue."""
    import json
    val = db.get_metadato("poll_routing_config")
    rules = json.loads(val) if val else {}
    
    pending = db.get_poll_review_queue(limit=5000)
    applied_count = 0
    ignored_count = 0
    
    critical_keys = {"tecnico_nombre", "inicio", "fin", "summary", "status", "_action"}
    
    for item in pending:
        c_type = item.get("conflict_type")
        
        rule_type = c_type
        if c_type == "FIELD_CHANGE":
            diff = item.get("diff", {})
            has_critical = any(k in critical_keys for k in diff.keys())
            if not has_critical:
                rule_type = "FIELD_CHANGE_SAFE"
        
        rule = rules.get(rule_type, "INBOX")
        
        try:
            if rule == "AUTO_APPLY":
                db.accept_review(item["review_id"])
                applied_count += 1
            elif rule == "IGNORE":
                with db._get_connection() as conn:
                    conn.execute("UPDATE poll_review_queue SET status = 'IGNORED' WHERE review_id = ?", (item["review_id"],))
                ignored_count += 1
        except Exception as e:
            print(f"[RETROACTIVE_APPLY_ERROR] review_id={item['review_id']} - {type(e).__name__}: {str(e)}")
            pass

    return {"applied": applied_count, "ignored": ignored_count}

class ConfigRequest(BaseModel):
    config: dict
    pin: Optional[str] = None

@app.post("/api/config")
async def save_config(req: ConfigRequest):
    """Guarda la configuración. Si se modifican campos protegidos, requiere el PIN correcto."""
    current_config = db.get_app_config()
    
    # Validar PIN si se provee (se requiere para guardar servicios o seguridad)
    if req.pin and req.pin != current_config.get("pin", "2302"):
        raise HTTPException(status_code=403, detail="PIN incorrecto")
        
    new_config = req.config
    # Mantener el PIN actual si no se envió uno nuevo en la configuración
    if "pin" not in new_config or not new_config["pin"]:
        new_config["pin"] = current_config.get("pin", "2302")
        
    db.set_app_config(new_config)
    
    # Sincronizar inmediatamente la tabla de técnicos para que el planner los vea
    tecnicos_config = new_config.get("technicians", {})
    tecnicos_db = []
    for email, data in tecnicos_config.items():
        if data.get("enabled", False):
            tecnicos_db.append({
                "nombre": data.get("alias", email.split('@')[0]),
                "correo": email,
                "iniciales": data.get("iniciales", ""),
                "color": "",
                "servicio": data.get("service", "")
            })
    if tecnicos_db:
        db.guardar_tecnicos(tecnicos_db)

    return {"status": "ok", "message": "Configuración guardada"}

@app.get("/api/calendars")
async def get_calendars():
    """Retorna los calendarios accesibles por el usuario."""
    try:
        svc_cal, _ = await run_in_threadpool(extractor._safe_get_google_services)
        calendars = extractor.obtener_calendarios_usuario(svc_cal)
        return calendars
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/holidays/import_google")
async def import_google_holidays():
    """Importa feriados de Argentina desde el calendario oficial de Google."""
    try:
        svc_cal, _ = await run_in_threadpool(extractor._safe_get_google_services)
        
        # Calendario oficial de feriados de Argentina en Google
        calendar_id = 'es.ar#holiday@group.v.calendar.google.com'
        
        # Obtener feriados desde el 1 de Enero del año actual hasta fin del año próximo
        now = datetime.datetime.now()
        time_min = f"{now.year}-01-01T00:00:00Z"
        time_max = f"{now.year + 1}-12-31T23:59:59Z"
        
        events_result = svc_cal.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        holidays_found = {}
        for item in events_result.get('items', []):
            date_str = item.get('start', {}).get('date')
            summary = item.get('summary')
            if date_str and summary:
                holidays_found[date_str] = summary
                
        # Merge con los existentes
        app_config = db.get_app_config()
        current_holidays = app_config.get("holidays", {})
        current_holidays.update(holidays_found)
        app_config["holidays"] = current_holidays
        db.set_app_config(app_config)

        return {"status": "ok", "imported": len(holidays_found), "holidays": current_holidays}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
@app.get("/api/tecnicos")
async def get_tecnicos():
    return db.obtener_tecnicos()


@app.get("/api/patrones")
async def get_patrones():
    try:
        rows = db.obtener_patrones()
        result = []
        # Fila 1 son encabezados -> Saltar si el primer elemento parece un encabezado
        # O simplemente saltar la primera si rows > 0
        start_idx = 0
        if rows and len(rows) > 0:
            first = str(rows[0][0]).lower()
            # Detectar fila de encabezado por substrings robustos (no requiere acento)
            header_keywords = ("nombre", "patron", "identif", "id", "activo", "equipo", "serie", "marca")
            if any(kw in first for kw in header_keywords):
                start_idx = 1
        
        for row in rows[start_idx:]:
            if row and len(row) > utils.IDX_PATRON_NOMBRE:
                result.append({
                    "nombre": str(row[utils.IDX_PATRON_NOMBRE]).strip(),
                    "trabajos": str(row[utils.IDX_PATRON_TRABAJOS]).strip() if len(row) > utils.IDX_PATRON_TRABAJOS else "",
                    "clase": str(row[utils.IDX_PATRON_CLASE]).strip() if len(row) > utils.IDX_PATRON_CLASE else "",
                    "rango": str(row[utils.IDX_PATRON_RANGO]).strip() if len(row) > utils.IDX_PATRON_RANGO else "",
                })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ots/pendientes")
async def get_ots_pendientes():
    try:
        todas = db.obtener_bd_ots()
        ots_agrupadas = {}

        header_names = ["estatus", "ot", "cliente", "trabajo"]
        start_idx = 0
        if todas and any(h in str(todas[0]).lower() for h in header_names):
            start_idx = 1

        for row in todas[start_idx:]:
            if len(row) > utils.IDX_OT:
                nro_ot = str(row[utils.IDX_OT]).strip()
                if not nro_ot:
                    continue
                
                trabajo_item = row[utils.IDX_TRAB].strip() if len(row) > utils.IDX_TRAB else ""
                estado_val = row[utils.IDX_ESTADO].strip() if len(row) > utils.IDX_ESTADO else "Desconocido"

                if nro_ot not in ots_agrupadas:
                    ots_agrupadas[nro_ot] = {
                        "nro": nro_ot,
                        "cliente": row[utils.IDX_CLIE].strip() if len(row) > utils.IDX_CLIE else "S/N",
                        "estado": estado_val,
                        "trabajos": [trabajo_item] if trabajo_item else [],
                        "asunto": row[utils.IDX_ASUNTO].strip() if len(row) > utils.IDX_ASUNTO else "",
                        "direccion": row[utils.IDX_DIRECCION].strip() if len(row) > utils.IDX_DIRECCION else "",
                        "fecha": row[utils.IDX_FECHA] if len(row) > utils.IDX_FECHA else "",
                        "sfid": row[utils.IDX_SFID].strip() if len(row) > utils.IDX_SFID else ""
                    }
                else:
                    if trabajo_item and trabajo_item not in ots_agrupadas[nro_ot]["trabajos"]:
                        ots_agrupadas[nro_ot]["trabajos"].append(trabajo_item)
                    # Si no teníamos sfid pero ahora sí, lo guardamos
                    if not ots_agrupadas[nro_ot].get("sfid") and len(row) > utils.IDX_SFID:
                        ots_agrupadas[nro_ot]["sfid"] = row[utils.IDX_SFID].strip()
        
        resultado = []
        for nro, data in ots_agrupadas.items():
            data["trabajo"] = " | ".join(data["trabajos"])
            resultado.append(data)
        return resultado
    except Exception as e:
        print(f"Error en get_ots_pendientes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ots/{nro}/partidas")
async def get_ot_partidas(nro: str):
    try:
        todas = db.obtener_bd_ots()
        filas = [r for r in todas if len(r) > utils.IDX_OT and str(r[utils.IDX_OT]).strip() == nro]

        conteo = {}
        equipos = []
        for f in filas:
            t = f[utils.IDX_TRAB].strip() if len(f) > utils.IDX_TRAB else ''
            p = f[utils.IDX_PTS].strip() if len(f) > utils.IDX_PTS else ''
            if t or p:
                k = (t, p)
                conteo[k] = conteo.get(k, 0) + 1
            equipos.append({
                "id": f[utils.IDX_ID] if len(f) > utils.IDX_ID else "",
                "serie": f[utils.IDX_SERIE] if len(f) > utils.IDX_SERIE else "",
                "marca": f[utils.IDX_MARCA] if len(f) > utils.IDX_MARCA else "",
                "modelo": f[utils.IDX_MODELO] if len(f) > utils.IDX_MODELO else "",
                "trabajo": t,
                "puntos": p,
            })

        partidas = [{"trabajo": k[0] or "—", "puntos": k[1] or "—", "cant": v}
                    for k, v in sorted(conteo.items())]

        return {
            "nro": nro,
            "partidas": partidas,
            "total_partidas": sum(conteo.values()),
            "equipos": equipos
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class BatchOTParams(BaseModel):
    nros: List[str]


@app.post("/api/ots/batch/partidas")
async def get_batch_ot_partidas(params: BatchOTParams):
    try:
        todas = db.obtener_bd_ots()
        nros_set = set(str(n).strip() for n in params.nros)

        # Filtrar todas las filas que pertenezcan a las OTs solicitadas
        filas = [r for r in todas if len(r) > utils.IDX_OT and str(r[utils.IDX_OT]).strip() in nros_set]

        conteo = {}
        equipos = []
        for f in filas:
            t = f[utils.IDX_TRAB].strip() if len(f) > utils.IDX_TRAB else ''
            p = f[utils.IDX_PTS].strip() if len(f) > utils.IDX_PTS else ''
            if t or p:
                k = (t, p)
                conteo[k] = conteo.get(k, 0) + 1
            equipos.append({
                "ot": f[utils.IDX_OT] if len(f) > utils.IDX_OT else "",
                "id": f[utils.IDX_ID] if len(f) > utils.IDX_ID else "",
                "serie": f[utils.IDX_SERIE] if len(f) > utils.IDX_SERIE else "",
                "marca": f[utils.IDX_MARCA] if len(f) > utils.IDX_MARCA else "",
                "modelo": f[utils.IDX_MODELO] if len(f) > utils.IDX_MODELO else "",
                "trabajo": t,
                "puntos": p,
            })

        partidas = [{"trabajo": k[0] or "—", "puntos": k[1] or "—", "cant": v}
                    for k, v in sorted(conteo.items())]

        return {
            "nros": list(nros_set),
            "partidas": partidas,
            "total_partidas": sum(conteo.values()),
            "equipos": equipos
        }
    except Exception as e:
        import traceback; print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/eventos")
async def get_eventos():
    try:
        eventos_raw = db.obtener_eventos_dict()
        return [EventAdapter.normalize_event(ev) for ev in eventos_raw]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/eventos/cancelled")
async def get_cancelled_eventos():
    try:
        eventos_raw = db.obtener_eventos_dict()
        canon_events = [EventAdapter.normalize_event(ev) for ev in eventos_raw]
        return [ev for ev in canon_events if ev.get("sync_state") == "CANCELLED_IN_GOOGLE"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/eventos-externos")
async def get_eventos_externos(
    start: Optional[str] = Query(None),
    end:   Optional[str] = Query(None)
):
    """
    [SURROGATE_KEY] Retorna el caché vivo de eventos externos de Google Calendar.
    Estos eventos no tienen tarea_id_local y no están en la tabla 'eventos'.
    Son actualizados automáticamente por el PollingManager sin arbitraje.
    """
    try:
        return db.obtener_eventos_externos(start=start, end=end)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@app.get("/api/vehiculos")
async def get_vehiculos():

    try:
        return db.obtener_vehiculos()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────

# MOTOR DE BÚSQUEDA
# ─────────────────────────────────────────────

class BuscarParams(BaseModel):
    ots_seleccionadas: List[str]
    n_tec: int = 1
    jornadas: float = 1.0
    consecutivo: bool = False
    viaje: bool = False
    patrones_requeridos: List[str] = []
    excluir_conflictos_pats: bool = False
    pivot_date: Optional[str] = None
    servicio_requerido: Optional[str] = None
    tecnico_op: Optional[str] = None
    tecnico_filtro: Optional[str] = None

def _build_tech_events():
    """Construye el diccionario tech_events que espera engine.py desde la DB."""
    eventos = db.obtener_eventos_dict()
    tech_events = {}

    for ev in eventos:
        tech = str(ev.get("tecnico_nombre", "")).strip()
        if not tech: continue
        if tech not in tech_events:
            tech_events[tech] = {}

        start_str = ev.get("inicio", "")
        end_str = ev.get("fin", "")
        summary = ev.get("summary", "")

        if not start_str or not end_str: continue

        idx_p = summary.find(')')
        ot = summary[:idx_p + 1].strip() if idx_p != -1 else summary.split('-')[0].strip()
        es_todo_el_dia = "T" not in start_str or start_str.endswith("T00:00:00Z") or start_str.endswith("T03:00:00Z")
        es_ot = bool(ot and ot[0].isdigit()) or "RESERVA" in summary.upper()

        try:
            if "Z" in start_str: start_str = start_str.replace("Z", "+00:00")
            if "Z" in end_str: end_str = end_str.replace("Z", "+00:00")
            
            try: start_dt = datetime.datetime.fromisoformat(start_str)
            except ValueError: start_dt = datetime.datetime.strptime(start_str[:10], "%Y-%m-%d")
            
            try: end_dt = datetime.datetime.fromisoformat(end_str)
            except ValueError: end_dt = datetime.datetime.strptime(end_str[:10], "%Y-%m-%d")
            
            import pytz
            arg_tz = pytz.timezone("America/Argentina/Buenos_Aires")
            if start_dt.tzinfo: start_dt = start_dt.astimezone(arg_tz)
            if end_dt.tzinfo: end_dt = end_dt.astimezone(arg_tz)

            start_date = start_dt.date()
            end_date = end_dt.date()
            
            is_functionally_allday = start_dt.hour == 0 and start_dt.minute == 0 and end_dt.hour == 0 and end_dt.minute == 0 and end_dt > start_dt
            
            raw_props = ev.get("extended_props", {})
            if isinstance(raw_props, str):
                try: props = json.loads(raw_props) if raw_props else {}
                except: props = {}
            else:
                props = raw_props or {}
            
            if is_functionally_allday or es_todo_el_dia:
                dias = max(1, (end_date - start_date).days)
                for i in range(dias):
                    d = start_date + datetime.timedelta(days=i)
                    dk = d.strftime("%Y-%m-%d")
                    tech_events[tech].setdefault(dk, []).append({
                        "sort": 700, "sort_end": 1600, "text": f"07:00-16:00 | {ot}",
                        "horas": 0.0 if d.weekday() >= 5 else 9.0, "es_ot": es_ot,
                        "original_text": summary,
                        "extendedProperties": props,
                        "id": ev.get("id"), "calendar_id": ev.get("calendar_id"),
                        "Inicio": ev.get("inicio"), "Fin": ev.get("fin"),
                        "description": ev.get("descripcion", "")
                    })
            else:
                dias = (end_date - start_date).days
                for i in range(dias + 1):
                    d = start_date + datetime.timedelta(days=i)
                    dk = d.strftime("%Y-%m-%d")
                    is_weekend = d.weekday() >= 5
                    if i == 0 and dias == 0:
                        t1 = start_dt.strftime("%H:%M")
                        t2 = end_dt.strftime("%H:%M")
                        desc = f"{t1}-{t2} | {ot}"
                        sort_val = int(start_dt.strftime("%H%M"))
                        sort_end_val = int(end_dt.strftime("%H%M"))
                        h = 0.0 if is_weekend else max(0.0, min(16.0, end_dt.hour + end_dt.minute / 60) - max(7.0, start_dt.hour + start_dt.minute / 60))
                    else:
                        desc = f"{start_dt.strftime('%H:%M')}-... | {ot}" if i == 0 else (f"...-{end_dt.strftime('%H:%M')} | {ot}" if i == dias else f"Día entero | {ot}")
                        sort_val = int(start_dt.strftime("%H%M")) if i == 0 else 0
                        sort_end_val = int(end_dt.strftime("%H%M")) if i == dias else 2359
                        h = 0.0 if is_weekend else 9.0

                    tech_events[tech].setdefault(dk, []).append({
                        "sort": sort_val, "sort_end": sort_end_val, "text": desc,
                        "horas": h, "es_ot": es_ot, "original_text": summary,
                        "extendedProperties": props,
                        "id": ev.get("id"), "calendar_id": ev.get("calendar_id"),
                        "Inicio": ev.get("inicio"), "Fin": ev.get("fin"),
                        "description": ev.get("descripcion", "")
                    })
        except Exception as e:
            print(f"Error parseando {ev.get('id')}: {e}")
            continue

    return tech_events

@app.post("/api/engine/buscar")
async def buscar_disponibilidad(params: BuscarParams):
    try:
        tech_events = _build_tech_events()
        tecnicos_info = db.obtener_tecnicos()
        app_config = db.get_app_config()
        holidays = set(app_config.get("holidays", {}).keys())
        
        if params.pivot_date:
            f_inicio = datetime.date.fromisoformat(params.pivot_date)
        else:
            f_inicio = datetime.date.today() + datetime.timedelta(days=1)

        def serializar(res):
            out = []
            for op in res:
                fechas = []
                for fdata in op["fechas"]:
                    fechas.append({
                        "date": fdata["date"].isoformat(),
                        "h_start": fdata["h_start"],
                        "h_dur": fdata["h_dur"],
                        "conf": fdata.get("conf", []),
                        "conf_patrones": [
                            {"patron": c["patron"], "tecnico": c["tecnico"], "donde": c["donde"]}
                            for c in fdata.get("conf_patrones", [])
                        ]
                    })
                out.append({
                    "tecnicos": [{"nombre": t["nombre"], "iniciales": t.get("iniciales", "")} for t in op["tecnicos"]],
                    "fechas": fechas,
                    "tiene_conflictos": any(len(f.get("conf", [])) > 0 for f in fechas),
                    "tiene_conf_patrones": any(len(f.get("conf_patrones", [])) > 0 for f in fechas),
                })
            return out

        res_est = engine.buscar_disponibilidad(
            tech_events, tecnicos_info, params.n_tec, params.jornadas,
            params.consecutivo, params.viaje, f_inicio, 120, ignorar_no_ots=False,
            patrones_requeridos=params.patrones_requeridos,
            excluir_conflictos_pats=params.excluir_conflictos_pats,
            ots_objetivo=params.ots_seleccionadas,
            holidays=holidays,
            servicio_requerido=params.servicio_requerido,
            tecnico_op=params.tecnico_op,
            tecnico_filtro=params.tecnico_filtro
        )
        res_flex = engine.buscar_disponibilidad(
            tech_events, tecnicos_info, params.n_tec, params.jornadas,
            params.consecutivo, params.viaje, f_inicio, 120, ignorar_no_ots=True,
            patrones_requeridos=params.patrones_requeridos,
            excluir_conflictos_pats=params.excluir_conflictos_pats,
            ots_objetivo=params.ots_seleccionadas,
            holidays=holidays,
            servicio_requerido=params.servicio_requerido,
            tecnico_op=params.tecnico_op,
            tecnico_filtro=params.tecnico_filtro
        )

        return {"estrictas": serializar(res_est), "flexibles": serializar(res_flex)}
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


class BuscarSiguientesParams(BuscarParams):
    pivot_date: str  # ISO date del pivot para continuar desde ahí

@app.post("/api/engine/buscar_siguientes")
async def buscar_siguientes(params: BuscarSiguientesParams):
    try:
        tech_events = _build_tech_events()
        tecnicos_info = db.obtener_tecnicos()
        app_config = db.get_app_config()
        holidays = set(app_config.get("holidays", {}).keys())
        f_pivot = datetime.date.fromisoformat(params.pivot_date) + datetime.timedelta(days=1)

        def ser(res):
            out = []
            for op in res:
                fechas = []
                for fdata in op["fechas"]:
                    fechas.append({
                        "date": fdata["date"].isoformat(),
                        "h_start": fdata["h_start"], "h_dur": fdata["h_dur"],
                        "conf": fdata.get("conf", []),
                        "conf_patrones": [{"patron": c["patron"], "tecnico": c["tecnico"], "donde": c["donde"]}
                                          for c in fdata.get("conf_patrones", [])]
                    })
                out.append({
                    "tecnicos": [{"nombre": t["nombre"], "iniciales": t.get("iniciales", "")} for t in op["tecnicos"]],
                    "fechas": fechas,
                    "tiene_conflictos": any(len(f.get("conf", [])) > 0 for f in fechas),
                    "tiene_conf_patrones": any(len(f.get("conf_patrones", [])) > 0 for f in fechas),
                })
            return out

        res_est = engine.buscar_disponibilidad(tech_events, tecnicos_info, params.n_tec, params.jornadas,
                                               params.consecutivo, params.viaje, f_pivot, 120,
                                               ignorar_no_ots=False, patrones_requeridos=params.patrones_requeridos,
                                               excluir_conflictos_pats=params.excluir_conflictos_pats,
                                               ots_objetivo=params.ots_seleccionadas,
                                               holidays=holidays,
                                               servicio_requerido=params.servicio_requerido,
                                               tecnico_op=params.tecnico_op,
                                               tecnico_filtro=params.tecnico_filtro)
        res_flex = engine.buscar_disponibilidad(tech_events, tecnicos_info, params.n_tec, params.jornadas,
                                                params.consecutivo, params.viaje, f_pivot, 120,
                                                ignorar_no_ots=True, patrones_requeridos=params.patrones_requeridos,
                                                excluir_conflictos_pats=params.excluir_conflictos_pats,
                                                ots_objetivo=params.ots_seleccionadas,
                                                holidays=holidays,
                                                servicio_requerido=params.servicio_requerido,
                                                tecnico_op=params.tecnico_op,
                                                tecnico_filtro=params.tecnico_filtro)

        return {"estrictas": ser(res_est), "flexibles": ser(res_flex)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CrearEventoParams(BaseModel):
    correo_tecnico: str
    titulo: str
    descripcion: str
    direccion: str
    fecha: str
    fecha_fin: Optional[str] = None
    h_start: float
    h_dur: float
    patrones: List[str]
    ots: List[str]
    vehiculo: Optional[str] = None
    requiere_vehiculo: bool = False

# ─────────────────────────────────────────────
# IMPORTAR EVENTO EXTERNO DE GOOGLE CALENDAR
# ─────────────────────────────────────────────

class ImportarEventoExternoParams(BaseModel):
    google_event_id: str          # ID del evento en Google Calendar
    calendar_id: str              # Calendario donde vive el evento (del técnico destino)
    tecnico_nombre: str           # Nombre del técnico en el sistema

@app.post("/api/eventos/importar-externo")
async def importar_evento_externo(params: ImportarEventoExternoParams):
    """
    [SURROGATE_KEY] Importa un evento externo de Google Calendar al Planner.

    Lógica de Grupo Automática:
      Importa al organizador y a TODOS los técnicos invitados registrados en Configuración,
      vinculándolos bajo un mismo 'grupo_id', sin importar desde qué calendario se
      hizo clic en "Importar Trabajo".
    """
    await check_authorization()
    try:
        svc_cal, _ = extractor._safe_get_google_services()

        # 1. Obtener el evento desde el calendario solicitado
        try:
            g_ev = svc_cal.events().get(
                calendarId=params.calendar_id,
                eventId=params.google_event_id
            ).execute()
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Evento no encontrado en Google Calendar: {e}")

        # 2. Obtener el evento máster desde el organizador (si el click fue en un invitado)
        organizer_email = g_ev.get("organizer", {}).get("email", "")
        master_g_ev = g_ev
        master_calendar_id = params.calendar_id

        if organizer_email and organizer_email != params.calendar_id:
            try:
                master_g_ev = svc_cal.events().get(
                    calendarId=organizer_email,
                    eventId=params.google_event_id
                ).execute()
                master_calendar_id = organizer_email
            except Exception:
                # Fallback: usar el evento traído originalmente
                master_g_ev = g_ev

        # 3. Validar si ESTE técnico específico ya importó este evento
        existing_priv = master_g_ev.get("extendedProperties", {}).get("private", {})
        existing_tarea_id = existing_priv.get("tarea_id_local")
        existing_grupo_id = existing_priv.get("grupo_id")

        with db._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            tec_already_has = conn.execute(
                """SELECT * FROM eventos 
                   WHERE calendar_id = ? 
                     AND (google_event_id = ? OR id = ? OR extended_props LIKE ?)""",
                (
                    params.calendar_id,
                    master_g_ev.get("id"),
                    existing_tarea_id or "___NONE___",
                    f"%{existing_tarea_id}%" if existing_tarea_id else "%___NONE___%"
                )
            ).fetchone()

        if tec_already_has:
            raise HTTPException(
                status_code=409,
                detail=f"Este técnico ('{params.tecnico_nombre}') ya tiene importado este trabajo en el Planner ({tec_already_has['id']})"
            )

        # 4. Clasificar técnicos registrados
        tecnicos = db.obtener_tecnicos()
        email_to_tec = {t["correo"]: t for t in tecnicos if t.get("correo")}
        warnings = []

        attendees = master_g_ev.get("attendees", [])
        organizer_tec = email_to_tec.get(organizer_email)

        registered_guest_tecs = []
        unknown_guests = []

        for att in attendees:
            att_email = att.get("email", "")
            if not att_email or att_email == organizer_email:
                continue
            if att_email in email_to_tec:
                registered_guest_tecs.append(email_to_tec[att_email])
            else:
                unknown_guests.append(att_email)
                warnings.append(f"Aviso: El invitado '{att_email}' no está registrado como técnico en el sistema.")

        # Determinar si el organizador ya fue importado previamente
        org_already_imported = False
        org_event_row = None
        if organizer_tec and existing_tarea_id:
            with db._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                org_event_row = conn.execute(
                    "SELECT * FROM eventos WHERE google_event_id = ? OR id = ?",
                    (master_g_ev.get("id"), existing_tarea_id)
                ).fetchone()
                if org_event_row:
                    org_already_imported = True
                    if not existing_grupo_id:
                        try:
                            import json as _json
                            ep_data = _json.loads(org_event_row.get("extended_props") or "{}")
                            existing_grupo_id = ep_data.get("private", {}).get("grupo_id")
                        except Exception:
                            pass

        # Determinar si requiere grupo (múltiples técnicos o unir nuevo invitado a organizador importado)
        all_participating_tecs = ([] if not organizer_tec else [organizer_tec]) + registered_guest_tecs
        has_group = len(all_participating_tecs) > 1 or org_already_imported
        grupo_id = existing_grupo_id or (f"g_{uuid.uuid4().hex[:10]}" if has_group else None)

        # Preparar fechas normalizadas
        from utils import TimeNormalizationService
        start_raw = master_g_ev.get("start", {})
        end_raw   = master_g_ev.get("end",   {})
        inicio_str = TimeNormalizationService.normalize_to_utc_z(start_raw)
        fin_str    = TimeNormalizationService.normalize_to_utc_z(end_raw)

        imported_tarea_ids = []

        # 5. Procesar ORGANIZADOR
        if organizer_tec and not org_already_imported:
            org_tarea_id = f"local_{uuid.uuid4().hex[:12]}"

            # Desvincular a los invitados registrados del evento original en GCal
            remaining_attendees = [
                a for a in attendees
                if a.get("email") not in email_to_tec or a.get("email") == organizer_email
            ]

            org_patch_priv = {
                **existing_priv,
                "source":         "internal",
                "tarea_id_local": org_tarea_id,
                "import_type":    "group_owner_claim"
            }
            if grupo_id:
                org_patch_priv["grupo_id"] = grupo_id

            try:
                svc_cal.events().patch(
                    calendarId=organizer_email,
                    eventId=master_g_ev.get("id"),
                    body={
                        "attendees": remaining_attendees,
                        "extendedProperties": {"private": org_patch_priv}
                    }
                ).execute()
            except Exception as e:
                warnings.append(f"Aviso al actualizar evento del organizador: {e}")

            org_event_obj = {
                "id":              org_tarea_id,
                "google_event_id": master_g_ev.get("id"),
                "calendar_id":     organizer_email,
                "tecnico":         organizer_tec["nombre"],
                "tecnico_nombre":  organizer_tec["nombre"],
                "summary":         master_g_ev.get("summary", "Trabajo importado"),
                "evento":          master_g_ev.get("summary", "Trabajo importado"),
                "inicio":          inicio_str,
                "fin":             fin_str,
                "descripcion":     master_g_ev.get("description", ""),
                "ubicacion":       master_g_ev.get("location", ""),
                "extendedProperties": {
                    "private": org_patch_priv
                },
                "sync_status":  "SUCCESS",
                "pending_sync": 0,
                "source":       "internal"
            }
            db.guardar_evento_individual(org_event_obj)
            db.delete_evento_externo(master_g_ev.get("id"), organizer_email)
            imported_tarea_ids.append(org_tarea_id)

        elif organizer_tec and org_already_imported and grupo_id and not existing_grupo_id:
            # El organizador ya fue importado previamente pero no tenía grupo_id; se lo asignamos ahora
            try:
                org_tarea_id = org_event_row["id"]
                org_patch_priv = {
                    **existing_priv,
                    "grupo_id": grupo_id
                }
                svc_cal.events().patch(
                    calendarId=organizer_email,
                    eventId=master_g_ev.get("id"),
                    body={"extendedProperties": {"private": org_patch_priv}}
                ).execute()

                db.actualizar_extended_props_incremental(org_tarea_id, {"private": {"grupo_id": grupo_id}})
            except Exception as e:
                warnings.append(f"Aviso al asignar grupo_id al organizador: {e}")


        # 6. Procesar cada INVITADO REGISTRADO
        for g_tec in registered_guest_tecs:
            guest_tarea_id = f"local_{uuid.uuid4().hex[:12]}"
            guest_priv = {
                "source":         "internal",
                "tarea_id_local": guest_tarea_id,
                "imported_from":  master_g_ev.get("id"),
                "import_type":    "group_guest_detach"
            }
            if grupo_id:
                guest_priv["grupo_id"] = grupo_id

            guest_body = {
                "summary":     master_g_ev.get("summary", "Trabajo importado"),
                "description": master_g_ev.get("description", ""),
                "location":    master_g_ev.get("location", ""),
                "start":       start_raw,
                "end":         end_raw,
                "extendedProperties": {"private": guest_priv}
            }

            try:
                created_guest = svc_cal.events().insert(
                    calendarId=g_tec["correo"],
                    body=guest_body
                ).execute()

                guest_google_id = created_guest["id"]

                guest_event_obj = {
                    "id":              guest_tarea_id,
                    "google_event_id": guest_google_id,
                    "calendar_id":     g_tec["correo"],
                    "tecnico":         g_tec["nombre"],
                    "tecnico_nombre":  g_tec["nombre"],
                    "summary":         master_g_ev.get("summary", "Trabajo importado"),
                    "evento":          master_g_ev.get("summary", "Trabajo importado"),
                    "inicio":          inicio_str,
                    "fin":             fin_str,
                    "descripcion":     master_g_ev.get("description", ""),
                    "ubicacion":       master_g_ev.get("location", ""),
                    "extendedProperties": {
                        "private": guest_priv
                    },
                    "sync_status":  "SUCCESS",
                    "pending_sync": 0,
                    "source":       "internal"
                }
                db.guardar_evento_individual(guest_event_obj)
                db.delete_evento_externo(master_g_ev.get("id"), g_tec["correo"])
                imported_tarea_ids.append(guest_tarea_id)
            except Exception as ge:
                warnings.append(f"No se pudo crear evento individual para invitado '{g_tec['nombre']}': {ge}")

        # Limpiar también la entrada de eventos_externos para params.calendar_id por si acaso
        db.delete_evento_externo(params.google_event_id, params.calendar_id)
        db.bump_mutation_time()

        db.log_trace(params.google_event_id, "importar_grupo_externo", {
            "grupo_id":       grupo_id,
            "organizer":      organizer_email,
            "guests_count":   len(registered_guest_tecs),
            "imported_ids":   imported_tarea_ids,
            "warnings":       warnings
        }, calendar_id=params.calendar_id, tag="IMPORT_GROUP_EXTERNAL")

        return {
            "status":          "ok",
            "grupo_id":        grupo_id,
            "imported_count":  len(imported_tarea_ids),
            "organizer":       organizer_tec["nombre"] if organizer_tec else None,
            "guests_imported": [t["nombre"] for t in registered_guest_tecs],
            "warnings":        warnings
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))



# ─────────────────────────────────────────────
# CREACIÓN / MOVIMIENTO / ELIMINACIÓN
# ─────────────────────────────────────────────


@app.post("/api/eventos/crear")
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

        all_pats = db.obtener_patrones()
        desc_enriquecida = generar_descripcion_enriquecida(params.descripcion, params.patrones, params.vehiculo, all_pats)

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

            db.guardar_evento_individual(event_obj)
            
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

@app.post("/api/eventos/{event_id}/duplicar")
async def duplicar_evento(event_id: str):
    await check_authorization()
    try:
        original = db.get_evento_dict(event_id)
        if not original:
            raise HTTPException(status_code=404, detail="Evento original no encontrado.")
            
        new_event_id = f"local_{uuid.uuid4().hex[:12]}"
        
        # Clonar extendedProperties de manera segura
        import copy
        new_ext_props = copy.deepcopy(original.get('extendedProperties') or {})
        if 'private' not in new_ext_props:
            new_ext_props['private'] = {}
            
        new_ext_props['private']['source'] = 'internal'
        new_ext_props['private']['version'] = '1'
        
        # El clon nace individualizado
        if 'grupo_id' in new_ext_props['private']:
            del new_ext_props['private']['grupo_id']
            
        event_obj = {
            "id": new_event_id,
            "google_event_id": new_event_id, # [LEGACY_EVENT_ID] Nuevo ID local
            "calendar_id": original.get("calendar_id"),
            "tecnico_nombre": original.get("tecnico_nombre"),
            "summary": original.get("summary", ""),
            "inicio": original.get("inicio"),
            "fin": original.get("fin"),
            "ubicacion": original.get("ubicacion", ""),
            "descripcion": original.get("descripcion", ""),
            "extendedProperties": new_ext_props,
            "version": 1,
            "sync_status": "PENDING",
            "pending_sync": 1,
            "source": "internal",
            "updated_at": datetime.datetime.now().isoformat(),
        }

        db.guardar_evento_individual(event_obj)
        
        db.log_trace(new_event_id, "mutation_clone", {
            "type": "CLONE_EVENT",
            "original_id": event_id,
            "calendar_id": event_obj["calendar_id"],
            "tecnico": event_obj["tecnico_nombre"]
        }, calendar_id=event_obj["calendar_id"], tag="OUTBOUND_MUTATION")

        db.enqueue_sync(new_event_id, event_obj["calendar_id"], event_obj["tecnico_nombre"], "CREATE")
        db.update_last_sync()

        return EventAdapter.normalize_event(event_obj)

    except Exception as e:
        import traceback
        print("Error en duplicar_evento:", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


class MoverEventoParams(BaseModel):
    event_id: str
    calendar_id_origen: str
    correo_destino: str
    nueva_fecha: str  # YYYY-MM-DD
    h_start: Optional[float] = None
    h_dur: Optional[float] = None
    # Nuevos campos para edición completa
    titulo: Optional[str] = None
    descripcion: Optional[str] = None
    patrones: Optional[List[str]] = None
    ots: Optional[List[str]] = None
    direccion: Optional[str] = None
    vehiculo: Optional[str] = None
    requiere_vehiculo: Optional[bool] = None
    base_version: Optional[int] = None

@app.patch("/api/eventos/{event_id}/mover")
async def mover_evento(event_id: str, params: MoverEventoParams):
    await check_authorization()
    
    grupo = db.obtener_grupo_de_evento(event_id)
    if grupo:
        return await mover_grupo(event_id, params)
        
    ev_interno = db.resolve_event(event_id)
    if not ev_interno:
        raise HTTPException(404, f"Evento {event_id} no encontrado")
    if _is_complex_event(ev_interno):
        raise HTTPException(400, "Eventos complejos (multidia o con invitados) estan bloqueados para edicion directa. Deben ser individualizados primero.")
        
    # Normalizar IDs a valores internos
    event_id = ev_interno['id']
    calendar_id_orig = ev_interno['calendar_id']

    if params.base_version is not None:
        if ev_interno['version'] > params.base_version:
            raise HTTPException(status_code=409, detail=f"Conflicto de concurrencia. Version local: {params.base_version}, Version DB: {ev_interno['version']}")

    from utils import TimeNormalizationService

    # [VEHICLE_UPDATE_TRACE] Capture initial state
    print(f"[VEHICLE_UPDATE_TRACE] mover_evento {event_id}:")
    print(f"  1. Original Full (Internal): {ev_interno}")
    print(f"  2. Original Props: {ev_interno.get('extendedProperties')}")
    print(f"  3. Frontend Payload: {params.dict()}")
                
    try:
        # Usar el evento resuelto directamente
        ev_actual_db = ev_interno
            
        start_orig = ev_actual_db["inicio"]
        end_orig = ev_actual_db["fin"]
        
        ev_actual = {
            "extendedProperties": ev_actual_db.get("extendedProperties", {}),
            "description": ev_actual_db.get("descripcion", ""),
            "summary": ev_actual_db.get("evento", ""),
            "location": ev_actual_db.get("ubicacion", "")
        }

        nueva_f = datetime.date.fromisoformat(params.nueva_fecha)
        tz_suffix = "-03:00"

        if params.h_start is not None:
            dur = params.h_dur
            if dur is None:
                try:
                    dt_s_orig = datetime.datetime.fromisoformat(start_orig.replace('Z', '+00:00'))
                    dt_e_orig = datetime.datetime.fromisoformat(end_orig.replace('Z', '+00:00'))
                    dur = (dt_e_orig - dt_s_orig).total_seconds() / 3600.0
                except:
                    dur = 1.0 
            
            dt_base = datetime.datetime.combine(nueva_f, datetime.time(0, 0))
            dt_s_new = dt_base + datetime.timedelta(hours=params.h_start)
            dt_e_new = dt_base + datetime.timedelta(hours=params.h_start + dur)
            
            nuevo_s = TimeNormalizationService.normalize_to_utc_z(dt_s_new)
            nuevo_e = TimeNormalizationService.normalize_to_utc_z(dt_e_new)
        elif "T" in start_orig:
            dt_s = datetime.datetime.fromisoformat(start_orig.replace('Z', '+00:00'))
            dt_e = datetime.datetime.fromisoformat(end_orig.replace('Z', '+00:00'))
            delta = (nueva_f - dt_s.date()).days
            new_s_dt = dt_s + datetime.timedelta(days=delta)
            new_e_dt = dt_e + datetime.timedelta(days=delta)
            nuevo_s = TimeNormalizationService.normalize_to_utc_z(new_s_dt)
            nuevo_e = TimeNormalizationService.normalize_to_utc_z(new_e_dt)
        else:
            nuevo_s = TimeNormalizationService.normalize_to_utc_z(nueva_f)
            nuevo_e = TimeNormalizationService.normalize_to_utc_z(nueva_f + datetime.timedelta(days=1))

        metadata = ev_actual.get('extendedProperties', {}).get('private', {})
        if params.ots is not None:
            metadata["app_ots"] = json.dumps(params.ots)
        if params.patrones is not None:
            metadata["app_patrones"] = json.dumps(params.patrones)
        if params.vehiculo is not None:
            metadata["app_vehiculo"] = params.vehiculo
        if params.requiere_vehiculo is not None:
            metadata["app_requiere_vehiculo"] = str(params.requiere_vehiculo).lower()
            
        nuevo_titulo = params.titulo if params.titulo is not None else ev_actual.get('summary', '')

        # --- HIDRATACIÓN PARA OTs (Backend) ---
        if params.ots is not None and len(params.ots) > 0:
            primera_ot = str(params.ots[0])
            ot_data = hydrator.ot_repo.get_ot(primera_ot)
            if ot_data:
                if not params.patrones and ot_data.get("patterns"):
                    metadata["app_patrones"] = json.dumps(ot_data["patterns"])
                if not params.vehiculo and ot_data.get("vehicle"):
                    metadata["app_vehiculo"] = ot_data["vehicle"]
            
            # Reescribir título si la OT no está presente en el mismo
            if primera_ot not in nuevo_titulo:
                import utils
                todas = db.obtener_bd_ots()
                ot_cache = next((r for r in todas if len(r) > utils.IDX_OT and str(r[utils.IDX_OT]).strip() == primera_ot), None)
                cliente = ot_cache[utils.IDX_CLIENTE] if ot_cache and len(ot_cache) > utils.IDX_CLIENTE else "S/C"
                base_titulo = f"{primera_ot} ({cliente})"
                # Buscar iniciales del técnico de destino
                target_cal = params.correo_destino or ev_actual_db["calendar_id"]
                tecs = db.obtener_tecnicos()
                t_match = next((t for t in tecs if t['correo'] == target_cal or t['nombre'] == target_cal), None)
                ini_dest = t_match.get('iniciales', '') if t_match else ''
                nuevo_titulo = utils.format_group_summary(base_titulo, [ini_dest])

        full_props = ev_actual.get('extendedProperties', {}).copy()
        full_props["private"] = metadata

        try:
            pats_actuales = json.loads(metadata.get('app_patrones', '[]') or '[]')
        except:
            pats_actuales = []

        base_desc = params.descripcion if params.descripcion is not None else ev_actual.get('description', '')
        if any(x is not None for x in [params.descripcion, params.patrones, params.vehiculo]):
            all_pats = db.obtener_patrones()
            desc_final = generar_descripcion_enriquecida(
                base_desc,
                json.loads(metadata.get("app_patrones", "[]")),
                metadata.get("app_vehiculo", ""),
                all_pats
            )
        else:
            desc_final = base_desc

        target_cal = params.correo_destino or ev_actual_db["calendar_id"]
        tecs = db.obtener_tecnicos()
        t_match = next((t for t in tecs if t['correo'] == target_cal or t['nombre'] == target_cal), None)
        tec_nombre = t_match['nombre'] if t_match else target_cal
        
        # VALIDACIÓN ETAPA 5
        h_start_val = params.h_start
        h_end_val = params.h_start + dur if params.h_start is not None else None
        if h_start_val is None:
            try:
                dt_s_val = datetime.datetime.fromisoformat(nuevo_s.replace('Z', '+00:00'))
                dt_e_val = datetime.datetime.fromisoformat(nuevo_e.replace('Z', '+00:00'))
                h_start_val = dt_s_val.hour + dt_s_val.minute / 60.0
                h_end_val = dt_e_val.hour + dt_e_val.minute / 60.0
            except:
                h_start_val, h_end_val = 7.0, 16.0
                
        vehiculo_val = params.vehiculo if params.vehiculo is not None else metadata.get('app_vehiculo', '')
        patrones_val = params.patrones if params.patrones is not None else pats_actuales


        # [VEHICLE_UPDATE_TRACE] Pre-persist state
        print(f"  4. Received in Backend: patrones={params.patrones}, vehiculo={params.vehiculo}")
        print(f"  5. Merge Input (full_props): {full_props}")

        print(f"[REASSIGN_TRACE:API] payload exacto enviado desde frontend: {params.dict()}")
        print(f"[REASSIGN_TRACE:API] target_cal: {target_cal}, original calendar_id: {ev_actual_db['calendar_id']}")
        print(f"[REASSIGN_TRACE:SQLITE_BEFORE] Evento en DB antes: {ev_actual_db}")

        # [REMOTE_REASSIGNMENT] Detección de movimiento entre calendarios
        is_reassignment = target_cal != ev_actual_db["calendar_id"]
        reassignment_id = None
        
        if is_reassignment:
            import uuid
            reassignment_id = str(uuid.uuid4())
            full_props["private"]["reassignment_in_progress"] = "true"
            full_props["private"]["reassignment_id"] = reassignment_id
            full_props["private"]["reassignment_started_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            full_props["private"]["previous_google_event_id"] = ev_actual_db["google_event_id"]
            full_props["private"]["previous_calendar_id"] = ev_actual_db["calendar_id"]
            full_props["private"]["reassignment_origin"] = "ui_move"
            sync_status_val = "REASSIGN_PENDING"
            operation_val = "REMOTE_REASSIGNMENT"
        else:
            sync_status_val = "PENDING"
            operation_val = "UPDATE"

        # PERSISTENCIA LOCAL Y ENCOLADO
        try:
            new_version = db.actualizar_evento_individual(event_id, ev_actual_db["calendar_id"], {
                "tecnico":    tec_nombre,
                "evento":     nuevo_titulo,
                "inicio":     nuevo_s,
                "fin":        nuevo_e,
                "ubicacion":  params.direccion if params.direccion is not None else ev_actual.get('location', ''),
                "descripcion": desc_final,
                "extendedProperties": full_props,
                "calendar_id": target_cal,
                "sync_status": sync_status_val,
                "pending_sync": 1
            }, base_version=params.base_version)
            
            # [VEHICLE_UPDATE_TRACE] Final persisted state
            persisted = db.resolve_event(event_id)
            print(f"  7. SQLite Persisted Props: {persisted.get('extendedProperties')}")
            
            # [OUTBOUND_MUTATION] mutation_created
            db.log_trace(event_id, "mutation_created", {
                "type": operation_val,
                "new_tecnico": tec_nombre,
                "new_calendar": target_cal,
                "reassignment_id": reassignment_id,
                "version_post": new_version
            }, calendar_id=target_cal, tag="OUTBOUND_MUTATION")
            
            print(f"[REASSIGN_TRACE:SQLITE_AFTER] Snapshot posterior: {persisted}")
            print(f"[REASSIGN_TRACE:API] operation_type generado: {operation_val}, sync_status asignado: {sync_status_val}")

            # Encolar actualización o reasignación
            # Para reasignación, usamos mutation_context para pasar el reassignment_id
            db.enqueue_sync(event_id, target_cal, tec_nombre, operation_val, 
                           origin=reassignment_id if is_reassignment else 'api',
                           original_calendar_id=ev_actual_db["calendar_id"])
            print(f"[REASSIGN_TRACE:QUEUE] Queue item generado con origin: {reassignment_id if is_reassignment else 'api'}")

        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))

        # ── Propagación silenciosa de vehículo/patrones al grupo ─────────
        if params.vehiculo is not None or params.patrones is not None:
            grupo_actual = db.obtener_grupo_de_evento(event_id)
            if grupo_actual:
                for eid_m in grupo_actual['event_ids']:
                    if eid_m == event_id:
                        continue  # Ya actualizado arriba
                    ev_m = db.resolve_event(eid_m)
                    if not ev_m:
                        continue
                    ev_norm = utils.EventAdapter.normalize_event(ev_m)
                    meta_m = ev_norm.get('extended_props', {}).get('private', {}).copy()
                    if params.vehiculo is not None:
                        meta_m['app_vehiculo'] = params.vehiculo
                    if params.patrones is not None:
                        meta_m['app_patrones'] = json.dumps(params.patrones)
                    pats_m = params.patrones if params.patrones is not None else json.loads(meta_m.get('app_patrones', '[]') or '[]')
                    veh_m = params.vehiculo if params.vehiculo is not None else meta_m.get('app_vehiculo', '')
                    all_pats = db.obtener_patrones()
                    desc_m = generar_descripcion_enriquecida(ev_norm.get('descripcion', ''), pats_m, veh_m, all_pats)
                    props_m = ev_norm.get('extended_props', {}).copy()
                    if 'private' not in props_m:
                        props_m['private'] = {}
                    props_m['private'].update(meta_m)
                    db.actualizar_evento_individual(
                        eid_m, ev_m['calendar_id'],
                        {"extendedProperties": props_m, "descripcion": desc_m},
                        sync_status='PENDING', pending_sync=1, origin='group_propagate'
                    )
                    gid_m = ev_m.get('google_event_id') or eid_m
                    db.enqueue_sync(gid_m, ev_m['calendar_id'], ev_m['tecnico_nombre'], "UPDATE")
                    db.log_trace(eid_m, "mutation_created", {
                        "type": "UPDATE", "origin": "group_propagate_vehiculo",
                        "vehiculo": params.vehiculo, "patrones": params.patrones
                    }, calendar_id=ev_m['calendar_id'], tag="OUTBOUND_MUTATION")

        # ── Gestión de grupo post-movimiento ──────────────────────────────
        grupo = db.obtener_grupo_de_evento(event_id)
        if grupo:
            nueva_f_str = nuevo_s[:10]
            cambio_fecha = (nueva_f_str != grupo['fecha'])
            cambio_tecnico = is_reassignment  # solo si cambió de calendario

            if cambio_tecnico:
                # [FASE 6 - BUG 1 FIX] Tecnico movido a otro calendario: MANTENER en el grupo.
                # Se actualiza tecnico_nombres del miembro y se recalculan los titulos de todos.
                all_tecnicos = db.obtener_tecnicos()
                ini_map = {t['nombre']: t.get('iniciales', '') for t in all_tecnicos}

                new_tec_nombres = []
                for rid in grupo['event_ids']:
                    rid_resolved = db.resolve_event(rid)
                    if rid == event_id or (rid_resolved and rid_resolved.get('google_event_id') == event_id):
                        new_tec_nombres.append(tec_nombre)
                    else:
                        if rid_resolved:
                            new_tec_nombres.append(
                                rid_resolved.get("tecnico_nombre") or rid_resolved.get("tecnico") or ""
                            )
                        else:
                            new_tec_nombres.append("")

                ot_base = utils.get_ot_base_from_event(ev_actual_db)
                nuevo_titulo_grupo = utils.format_group_summary(
                    ot_base,
                    [ini_map.get(n, '') for n in new_tec_nombres],
                )

                for rid in grupo['event_ids']:
                    rev = db.resolve_event(rid)
                    if not rev:
                        continue
                    is_reasigned_member = (rid == event_id or rev.get('google_event_id') == event_id)
                    db.actualizar_evento_individual(
                        rid,
                        target_cal if is_reasigned_member else rev['calendar_id'],
                        {"evento": nuevo_titulo_grupo},
                        sync_status=sync_status_val if is_reasigned_member else 'PENDING',
                        pending_sync=1,
                        origin='group_reassign_rename'
                    )
                    if not is_reasigned_member:
                        gid_r = rev.get('google_event_id') or rid
                        db.enqueue_sync(gid_r, rev['calendar_id'], rev['tecnico_nombre'], "UPDATE")
                        db.log_trace(rid, "mutation_created", {
                            "type": "UPDATE", "origin": "group_reassign_title",
                            "nuevo_titulo": nuevo_titulo_grupo
                        }, calendar_id=rev['calendar_id'], tag="OUTBOUND_MUTATION")

                db.crear_o_actualizar_grupo({
                    **grupo,
                    "tecnico_nombres": new_tec_nombres
                })

            elif cambio_fecha:
                # Solo cambio de fecha: quitar del grupo (el evento se mueve a otra fecha)
                new_event_ids = [eid for eid in grupo['event_ids'] if eid != event_id]
                try:
                    idx_rem = grupo['event_ids'].index(event_id)
                    new_tecnico_nombres = [n for i, n in enumerate(grupo['tecnico_nombres']) if i != idx_rem]
                except ValueError:
                    new_tecnico_nombres = [n for n in grupo['tecnico_nombres'] if n != tec_nombre]

                if not new_event_ids or len(new_event_ids) <= 1:
                    db.eliminar_grupo(grupo['grupo_id'])
                else:
                    db.crear_o_actualizar_grupo({**grupo, "event_ids": new_event_ids, "tecnico_nombres": new_tecnico_nombres})

        return {
            "status": "ok",
            "event_id": event_id,
            "version": new_version
        }


    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print("Error global en mover:", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))



# ─────────────────────────────────────────────
# GESTIÓN DE GRUPOS — MOVER / ELIMINAR / REASIGNAR
# ─────────────────────────────────────────────


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
        all_pats = db.obtener_patrones()
        desc_final = generar_descripcion_enriquecida(
            base_desc,
            json.loads(metadata.get("app_patrones", "[]")),
            metadata.get("app_vehiculo", ""),
            all_pats
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

@app.patch("/api/eventos/{event_id}/mover_grupo")
async def mover_grupo(event_id: str, params: MoverEventoParams):
    await check_authorization()

    ev_interno = db.resolve_event(event_id)
    if not ev_interno:
        raise HTTPException(404, f"Evento {event_id} no encontrado")
    if _is_complex_event(ev_interno):
        raise HTTPException(400, "Eventos complejos (multidia o con invitados) estan bloqueados para edicion directa. Deben ser individualizados primero.")

    # Normalizar al ID canónico local
    event_id = ev_interno["id"]

    # Si no pertenece a ningún grupo, delegar a mover_evento individual
    grupo_meta = db.obtener_grupo_de_evento(event_id)
    if not grupo_meta:
        return await mover_evento(event_id, params)

    grupo_id = grupo_meta["grupo_id"]

    # [GROUP_LOCK] Evitar mutaciones concurrentes sobre el mismo grupo
    db.log_trace(grupo_id, "GROUP_TX_BEGIN", {
        "operation_type": "mover_grupo",
        "trigger_event_id": event_id,
        "initiated_by": "right_panel",
        "base_version": params.base_version,
    }, tag="GROUP_TX")

    if is_group_locked(grupo_id):
        raise HTTPException(409, f"El grupo {grupo_id} tiene una operación en curso. Intente nuevamente en unos segundos.")

    # Verificar group_version (optimistic lock a nivel de grupo, no de miembro individual)
    if params.base_version is not None:
        stored_group_version = grupo_meta.get("group_version", 0)
        if params.base_version < stored_group_version:
            raise HTTPException(
                status_code=409,
                detail=f"Conflicto de versión grupal. Versión enviada: {params.base_version}, Versión actual: {stored_group_version}. Recargue la página e intente nuevamente."
            )

    acquired = acquire_group_lock(grupo_id, f"mover_grupo_{event_id}")
    if not acquired:
        raise HTTPException(409, f"El grupo {grupo_id} está siendo modificado por otra operación.")

    try:
        tecs_db = db.obtener_tecnicos()

        ctx = GroupOperationContext(
            operation_type    = "mover_grupo",
            grupo_id          = grupo_id,
            initiated_by      = "right_panel",
            trigger_event_id  = event_id,
        )

        ctx.load_group(db)
        ctx.validate(params)

        if ctx.validation_errors:
            raise HTTPException(400, "; ".join(ctx.validation_errors))

        ctx.build_plan(db, params, tecs_db)

        # Ejecutar mutación atómica (BEGIN IMMEDIATE → COMMIT/ROLLBACK automático)
        with DataManager.group_transaction_static(db.db_path) as conn:
            ctx.execute_mutation_phase(conn)

        # Post-commit: enqueue_sync, traces, journal — fuera de la transacción
        await run_in_threadpool(ctx.execute_post_commit_phase, db)

        db.log_trace(grupo_id, "GROUP_LOCK_RELEASED", {
            "operation_id": ctx.operation_id,
        }, tag="GROUP_TX")

        return ctx.to_snapshot_response(db)

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[ERROR] mover_grupo:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        release_group_lock(grupo_id)




@app.delete("/api/grupos/{grupo_id}")
async def eliminar_grupo_completo(grupo_id: str):
    await check_authorization()
    """Elimina todos los eventos de un grupo localmente."""
    try:
        eventos = db.obtener_eventos_dict()
        # Buscar el grupo en la DB
        # Nota: obtener_eventos_dict no tiene el grupo_id directo en cada evento de forma fácil, 
        # pero podemos usar el helper de data_manager si existiera.
        # Por ahora, usemos una conexión directa o busquemos por metadatos.
        with db._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT event_ids FROM grupos WHERE grupo_id = ?", (grupo_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Grupo no encontrado")
            
            event_ids = json.loads(row[0])
            for eid in event_ids:
                # 1. Obtener datos antes de borrar para encolar el DELETE
                cur.execute("SELECT tecnico_nombre, calendar_id FROM eventos WHERE id=? OR google_event_id=?", (eid, eid))
                info = cur.fetchone()
                if info:
                    # [OUTBOUND_MUTATION] mutation_created
                    db.log_trace(eid, "mutation_created", {
                        "type": "DELETE",
                        "tecnico": info[0],
                        "origin": "group_delete"
                    }, calendar_id=info[1], tag="OUTBOUND_MUTATION")

                    db.enqueue_sync(eid, info[1], info[0], "DELETE")
                
                db.eliminar_evento_individual(eid)
            
            db.eliminar_grupo(grupo_id)
            
            import re
            for eid in event_ids:
                ev = db.resolve_event(eid)
                if ev:
                    titulo_orig = ev.get('evento', '')
                    clean_title = re.sub(r'\s*-\s*[A-Z0-9/]+\s*$', '', titulo_orig).strip()
                    if clean_title != titulo_orig:
                        db.actualizar_titulo_evento(eid, clean_title)
                        db.enqueue_sync(eid, ev.get('calendar_id'), ev.get('tecnico_nombre'), "UPDATE")
            
        db.update_last_sync()

        return {"status": "ok"}
    except Exception as e:
        print("Error en eliminar_grupo_completo:", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/eventos/{event_id}/split")
async def split_evento(event_id: str, calendar_id: str = Query(...)):
    await check_authorization()
    """Divide un evento multi-día en N eventos de un solo día por técnico, con grupos día a día."""
    try:
        from datetime import datetime, timedelta

        # 1. Obtener el evento original de la DB
        ev_orig = db.resolve_event(event_id)
        if not ev_orig:
            raise HTTPException(status_code=404, detail=f"Evento {event_id} no encontrado")

        event_id = ev_orig['id']
        calendar_id = ev_orig['calendar_id']

        # 2. Detectar si forma parte de un grupo (multi-técnico)
        grupo = db.obtener_grupo_de_evento(event_id)
        all_tecnicos_db = db.obtener_tecnicos()
        ini_map = {t['nombre']: t.get('iniciales', '') for t in all_tecnicos_db}
        cal_map = {t['nombre']: t['correo'] for t in all_tecnicos_db}

        if grupo:
            # Lista de (event_id_orig, tecnico_nombre, calendar_id) para cada miembro
            miembros = []
            for eid_m, tec_m in zip(grupo['event_ids'], grupo['tecnico_nombres']):
                ev_m = db.resolve_event(eid_m)
                if ev_m:
                    miembros.append((eid_m, tec_m, ev_m['calendar_id'], ev_m))
        else:
            eventos_db = db.get_eventos_by_id(ev_orig.get('google_event_id') or event_id)
            if len(eventos_db) > 1:
                miembros = []
                for ev_db in eventos_db:
                    tec_n = ev_db.get('tecnico_nombre') or ev_db.get('tecnico', '')
                    miembros.append((ev_db['id'], tec_n, ev_db['calendar_id'], ev_db))
            else:
                tec_nombre = ev_orig.get('tecnico_nombre') or ev_orig.get('tecnico', '')
                miembros = [(event_id, tec_nombre, calendar_id, ev_orig)]

        # Obtener rango de días (usar el primero de los originales como referencia)
        ev_ref = miembros[0][3]
        s_raw = ev_ref['inicio']
        e_raw = ev_ref['fin']
        d_start = datetime.strptime(s_raw[:10], "%Y-%m-%d")
        d_end   = datetime.strptime(e_raw[:10], "%Y-%m-%d")

        ot_base = utils.get_ot_base_from_event(ev_ref)
        props_base = ev_ref.get('extended_props') or {}

        # Limpiar is_complex flags al splittear
        import copy
        new_ext_props = props_base
        if isinstance(new_ext_props, str):
            try: new_ext_props = json.loads(new_ext_props)
            except: new_ext_props = {}
        new_ext_props = copy.deepcopy(new_ext_props)
        if 'private' in new_ext_props:
            new_ext_props['private'].pop('has_guests', None)

        # 3. Generar eventos individuales día a día
        current = d_start
        while current < d_end:
            target_day = current.strftime("%Y-%m-%d")
            ids_del_dia = []

            for (_, tec_nombre, cal_tec, ev_m) in miembros:
                new_ev_id = f"local_{uuid.uuid4().hex[:12]}"

                # Título inicial (se reformula si hay múltiples técnicos en el grupo del día)
                titulo_dia = ot_base

                db.guardar_evento_individual({
                    "id": new_ev_id,
                    "calendar_id": cal_tec,
                    "tecnico_nombre": tec_nombre,
                    "summary": titulo_dia,
                    "inicio": f"{target_day}T07:00:00-03:00",
                    "fin": f"{target_day}T16:00:00-03:00",
                    "ubicacion": ev_m.get("ubicacion", ''),
                    "descripcion": ev_m.get("descripcion", ''),
                    "extended_props": new_ext_props,
                    "version": 1,
                    "sync_status": "PENDING",
                    "pending_sync": 1
                })
                db.log_trace(new_ev_id, "mutation_created", {
                    "type": "CREATE", "origin": "split", "tecnico": tec_nombre, "dia": target_day
                }, calendar_id=cal_tec, tag="OUTBOUND_MUTATION")
                db.enqueue_sync(new_ev_id, cal_tec, tec_nombre, "CREATE")
                ids_del_dia.append((new_ev_id, tec_nombre))

            # Si hay múltiples técnicos en el día → formar grupo del día + reformular títulos
            if len(ids_del_dia) > 1:
                ini_list = [ini_map.get(t, '') for _, t in ids_del_dia]
                titulo_grupo_dia = utils.format_group_summary(ot_base, ini_list)
                nuevo_grupo_id = str(uuid.uuid4())
                new_group_event_ids = [eid for eid, _ in ids_del_dia]
                new_group_tec_nombres = [t for _, t in ids_del_dia]

                # Actualizar título de cada evento del día al canónico de grupo
                for eid_d, tec_d in ids_del_dia:
                    ev_d = db.resolve_event(eid_d)
                    if ev_d:
                        db.actualizar_evento_individual(
                            eid_d, ev_d['calendar_id'],
                            {"evento": titulo_grupo_dia},
                            sync_status='PENDING', pending_sync=1, origin='split_group'
                        )

                ots_ext = list(utils.extraer_ots(ot_base))
                db.crear_o_actualizar_grupo({
                    "grupo_id": nuevo_grupo_id,
                    "fecha": target_day,
                    "event_ids": new_group_event_ids,
                    "tecnico_nombres": new_group_tec_nombres,
                    "ot_nro": ots_ext[0] if ots_ext else "N/A"
                })
                await update_group_title(nuevo_grupo_id)

            current += timedelta(days=1)

        # 4. Borrar todos los eventos originales (local + Google)
        for (eid_orig, tec_orig, cal_orig, ev_o) in miembros:
            gid_orig = ev_o.get('google_event_id') or eid_orig
            db.log_trace(eid_orig, "mutation_created", {
                "type": "DELETE", "origin": "split_cleanup", "tecnico": tec_orig
            }, calendar_id=cal_orig, tag="OUTBOUND_MUTATION")
            db.enqueue_sync(gid_orig, cal_orig, tec_orig, "DELETE")
            db.eliminar_evento_individual(eid_orig)

        # 5. Disolver el grupo original si existe
        if grupo:
            db.eliminar_grupo(grupo['grupo_id'])

        db.update_last_sync()
        return {"status": "ok", "dias_generados": (d_end - d_start).days}

    except HTTPException:
        raise
    except Exception as e:
        import traceback; print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/eventos/{event_id}/individualizar")
async def individualizar_evento(event_id: str, calendar_id: str = Query(...)):
    await check_authorization()
    """Quita un evento de su grupo (sin borrarlo de Google). Si el grupo queda con 1, lo disuelve."""
    try:
        ev = db.resolve_event(event_id)
        if not ev:
            raise HTTPException(status_code=404, detail=f"Evento {event_id} no encontrado")
        event_id = ev['id']

        grupo = db.obtener_grupo_de_evento(event_id)
        if not grupo:
            return {"status": "ok", "message": "El evento ya es individual"}

        all_tecnicos_db = db.obtener_tecnicos()
        ini_map = {t['nombre']: t.get('iniciales', '') for t in all_tecnicos_db}

        remaining_ids = [eid for eid in grupo['event_ids'] if eid != event_id]
        
        # Encontrar los nombres de forma segura sin .index() que falla si hay inconsistencias
        remaining_names = []
        for eid in remaining_ids:
            found_name = ""
            for i, gid in enumerate(grupo['event_ids']):
                if gid == eid:
                    found_name = grupo['tecnico_nombres'][i]
                    break
            if found_name:
                remaining_names.append(found_name)

        # Limpiar título del evento individualizado
        ot_limpia = utils.get_ot_base_from_event(ev)
        db.actualizar_evento_individual(
            event_id, ev['calendar_id'],
            {"evento": ot_limpia},
            sync_status='PENDING', pending_sync=1, origin='individualizar'
        )
        gid_self = ev.get('google_event_id') or event_id
        db.enqueue_sync(gid_self, ev['calendar_id'], ev['tecnico_nombre'], "UPDATE")
        db.log_trace(event_id, "mutation_created", {
            "type": "UPDATE", "origin": "individualizar", "nuevo_titulo": ot_limpia
        }, calendar_id=ev['calendar_id'], tag="OUTBOUND_MUTATION")

        if len(remaining_ids) <= 1:
            # Disolver grupo
            db.eliminar_grupo(grupo['grupo_id'])
            # Limpiar título del último evento restante
            if remaining_ids:
                last_ev = db.resolve_event(remaining_ids[0])
                if last_ev:
                    ot_last = utils.get_ot_base_from_event(last_ev)
                    db.actualizar_evento_individual(
                        remaining_ids[0], last_ev['calendar_id'],
                        {"evento": ot_last},
                        sync_status='PENDING', pending_sync=1, origin='individualizar'
                    )
                    gid_last = last_ev.get('google_event_id') or remaining_ids[0]
                    db.enqueue_sync(gid_last, last_ev['calendar_id'], last_ev['tecnico_nombre'], "UPDATE")
        else:
            # Reformular títulos del grupo reducido
            db.crear_o_actualizar_grupo({
                **grupo, "event_ids": remaining_ids, "tecnico_nombres": remaining_names
            })
            await update_group_title(grupo['grupo_id'])

        db.update_last_sync()
        return {"status": "ok", "nuevo_titulo": ot_limpia}

    except HTTPException:
        raise
    except Exception as e:
        import traceback; print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/api/eventos/{event_id}/agregar_tecnico")
async def agregar_tecnico_a_grupo(event_id: str, tecnico_correo: str = Query(...), calendar_id: str = Query(...)):
    await check_authorization()
    """Agrega un nuevo tecnico a la misma OT/fecha, reformula títulos y encola updates."""
    try:
        # 1. Obtener evento base con resolución robusta
        base_ev = db.resolve_event(event_id)
        if not base_ev:
            raise HTTPException(status_code=404, detail="Evento base no encontrado")
        event_id = base_ev['id']  # Normalizar al ID canónico

        # 2. Resolver técnicos
        tecnicos = db.obtener_tecnicos()
        t_new = next((t for t in tecnicos if t['correo'] == tecnico_correo), None)
        if not t_new:
            raise HTTPException(status_code=404, detail="Técnico no encontrado")

        nuevo_nombre = t_new['nombre']
        ini_nuevo = t_new.get('iniciales', '')

        # Iniciales del técnico base
        base_tecnico = base_ev.get('tecnico_nombre') or base_ev.get('tecnico', '')
        t_base = next((t for t in tecnicos if t['nombre'] == base_tecnico), None)
        ini_base = t_base.get('iniciales', '') if t_base else ''

        # 3. Calcular título canónico del grupo
        ot_base = utils.get_ot_base_from_event(base_ev)
        grupo = db.obtener_grupo_de_evento(event_id)

        ini_map = {t['nombre']: t.get('iniciales', '') for t in tecnicos}
        if grupo:
            all_tec_nombres = list(grupo['tecnico_nombres']) + [nuevo_nombre]
            all_iniciales = [ini_map.get(n, '') for n in all_tec_nombres]
        else:
            all_iniciales = [ini_base, ini_nuevo]

        nuevo_titulo = utils.format_group_summary(ot_base, all_iniciales)

        # 4. Actualizar título de todos los eventos actuales del grupo + encolar UPDATE
        eventos_a_actualizar = list(grupo['event_ids']) if grupo else [event_id]
        for eid_upd in eventos_a_actualizar:
            ev_upd = db.resolve_event(eid_upd)
            if not ev_upd:
                continue
            db.actualizar_evento_individual(
                eid_upd, ev_upd['calendar_id'],
                {"evento": nuevo_titulo},
                sync_status='PENDING', pending_sync=1, origin='agregar_tecnico'
            )
            gid_upd = ev_upd.get('google_event_id') or eid_upd
            db.enqueue_sync(gid_upd, ev_upd['calendar_id'], ev_upd['tecnico_nombre'], "UPDATE")
            db.log_trace(eid_upd, "mutation_created", {
                "type": "UPDATE", "origin": "agregar_tecnico_titulo", "nuevo_titulo": nuevo_titulo
            }, calendar_id=ev_upd['calendar_id'], tag="OUTBOUND_MUTATION")

        # 5. Crear nuevo evento con título reformulado
        new_ev_id = f"local_{uuid.uuid4().hex[:12]}"
        
        # Limpiar is_complex flags al individualizar
        new_ext_props = base_ev.get('extended_props') or {}
        import copy
        if isinstance(new_ext_props, str):
            try: new_ext_props = json.loads(new_ext_props)
            except: new_ext_props = {}
        new_ext_props = copy.deepcopy(new_ext_props)
        if 'private' in new_ext_props:
            new_ext_props['private'].pop('has_guests', None)
            
        db.guardar_evento_individual({
            "id": new_ev_id,
            "calendar_id": tecnico_correo,
            "tecnico_nombre": nuevo_nombre,
            "summary": nuevo_titulo,
            "inicio": base_ev['inicio'],
            "fin": base_ev['fin'],
            "ubicacion": base_ev.get("ubicacion", ''),
            "descripcion": base_ev.get("descripcion", ''),
            "extended_props": new_ext_props,
            "version": 1,
            "sync_status": "PENDING",
            "pending_sync": 1
        })
        db.log_trace(new_ev_id, "mutation_created", {
            "type": "CREATE", "tecnico": nuevo_nombre, "calendar_id": tecnico_correo
        }, calendar_id=tecnico_correo, tag="OUTBOUND_MUTATION")
        db.enqueue_sync(new_ev_id, tecnico_correo, nuevo_nombre, "CREATE")

        # 6. Gestión de Grupos
        if grupo:
            new_ids = list(grupo['event_ids']) + [new_ev_id]
            new_nombres = list(grupo['tecnico_nombres']) + [nuevo_nombre]
            db.crear_o_actualizar_grupo({**grupo, "event_ids": new_ids, "tecnico_nombres": new_nombres})
            
            # Vincular el evento del técnico agregado al grupo
            db.vincular_evento_a_grupo(new_ev_id, grupo['grupo_id'])
            await update_group_title(grupo['grupo_id'])
        else:
            nuevo_grupo_id = str(uuid.uuid4())
            ots_extraidas = list(utils.extraer_ots(ot_base))
            ot_nro = ots_extraidas[0] if ots_extraidas else "N/A"
            db.crear_o_actualizar_grupo({
                "grupo_id": nuevo_grupo_id,
                "fecha": base_ev['inicio'][:10],
                "event_ids": [event_id, new_ev_id],
                "tecnico_nombres": [base_tecnico, nuevo_nombre],
                "ot_nro": ot_nro
            })
            
            # Vincular ambos eventos (base y nuevo) al nuevo grupo
            db.vincular_evento_a_grupo(event_id, nuevo_grupo_id)
            db.vincular_evento_a_grupo(new_ev_id, nuevo_grupo_id)

        target_gid = grupo['grupo_id'] if grupo else nuevo_grupo_id
        validate_group_integrity(db, target_gid)

        db.update_last_sync()
        return {"status": "ok", "new_event_id": new_ev_id, "nuevo_titulo": nuevo_titulo}
    except HTTPException:
        raise
    except Exception as e:
        import traceback; print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/grupos/tarjeta_salida")
async def obtener_tarjetas_salida(fecha: str = Query(...)):
    """Genera datos completos para la tarjeta de salida por grupos."""
    try:
        # 1. Obtener datos base
        grupos_db = db.obtener_grupos_fecha(fecha)
        ots_db = db.obtener_bd_ots()
        map_ots = {str(ot[utils.IDX_OT]): ot for ot in ots_db if len(ot) > utils.IDX_OT}
        
        eventos_all = db.obtener_eventos_dict()
        eventos_dia = [e for e in eventos_all if e.get('inicio', '')[:10] == fecha or e.get('Inicio', '')[:10] == fecha]
        ids_en_grupos = []
        for g in grupos_db: ids_en_grupos.extend(g['event_ids'])
        
        # 2. Mapeo de técnicos para iniciales nombre+apellido
        tecs_all = db.obtener_tecnicos()
        def get_inits(nombre):
            t_data = next((t for t in tecs_all if t['nombre'] == nombre), None)
            if t_data and t_data.get('iniciales'): return t_data['iniciales']
            return "".join([word[0].upper() for word in str(nombre).split(' ') if word])

        # 3. Agrupamiento por Técnicos involucrados (Grupo de Trabajo)
        agrupados = {}

        def _get_ots_from_ev(ev_data):
            e_ots = []
            has_meta = False
            try:
                ep = ev_data.get('extended_props') or ev_data.get('extendedProperties') or {}
                if isinstance(ep, str): ep = json.loads(ep)
                p = ep.get('private', {})
                if 'app_ots' in p:
                    has_meta = True
                    ro = p['app_ots']
                    if isinstance(ro, str): e_ots = json.loads(ro)
                    elif isinstance(ro, list): e_ots = ro
            except: pass
            
            if not has_meta:
                t = ev_data.get('summary') or ev_data.get('Evento') or ''
                extracted = list(utils.extraer_ots(t))
                # Filtrar solo OTs que realmente existen en la DB para evitar falsos positivos
                e_ots = [o for o in extracted if str(o) in map_ots]
            return e_ots

        def procesar_agrupacion(tecs, pats, veh, ev):
            ots_list = _get_ots_from_ev(ev)
            if not ots_list: return
            
            key = tuple(sorted(tecs))
            if key not in agrupados:
                agrupados[key] = {
                    'tecnicos': set(tecs),
                    'ots': set(),
                    'patrones': set(),
                    'vehiculos': set(),
                    'detalles_ots': []
                }
            
            for ot in ots_list:
                if ot not in agrupados[key]['ots']:
                    agrupados[key]['ots'].add(ot)
                    ot_info = map_ots.get(ot, [])
                    cliente = ev.get('cliente') or ev.get('Cliente')
                    if not cliente: cliente = ot_info[utils.IDX_CLIE] if len(ot_info) > utils.IDX_CLIE else "---"
                    
                    asunto = ot_info[utils.IDX_ASUNTO] if len(ot_info) > utils.IDX_ASUNTO else "---"
                    if not asunto or str(asunto).strip() == "":
                        asunto = "Sin asunto"
                    
                    direccion = ot_info[utils.IDX_DIRECCION] if len(ot_info) > utils.IDX_DIRECCION else "---"

                    # Resumen de partidas
                    filas_ot = [r for r in ots_db if len(r) > utils.IDX_OT and str(r[utils.IDX_OT]).strip() == ot]
                    conteo = {}
                    for f in filas_ot:
                        t = f[utils.IDX_TRAB].strip() if len(f) > utils.IDX_TRAB else ''
                        p = f[utils.IDX_PTS].strip() if len(f) > utils.IDX_PTS else ''
                        if t or p:
                            k = (t, p)
                            conteo[k] = conteo.get(k, 0) + 1
                    partidas = [{"trabajo": k[0] or "—", "puntos": k[1] or "—", "cant": v} for k, v in sorted(conteo.items())]

                    # Fechas Adicionales
                    fechas_adicionales = set()
                    for e_all in eventos_all:
                        e_ots = _get_ots_from_ev(e_all)
                        if ot in e_ots:
                            e_fecha = e_all.get('inicio', '')[:10] or e_all.get('Inicio', '')[:10]
                            if e_fecha and e_fecha != fecha:
                                fechas_adicionales.add(e_fecha)
                    
                    agrupados[key]['detalles_ots'].append({
                        'nro': ot,
                        'cliente': cliente,
                        'asunto': asunto,
                        'direccion': direccion,
                        'partidas': partidas,
                        'fechas_adicionales': sorted(list(fechas_adicionales))
                    })
            
            for p in (pats or []): agrupados[key]['patrones'].add(p)
            if veh: agrupados[key]['vehiculos'].add(veh)

        # A. Procesar Grupos registrados
        for g in grupos_db:
            info_ev = next((e for e in eventos_dia if e['id'] in g['event_ids']), None)
            if info_ev:
                procesar_agrupacion(g['tecnico_nombres'], g.get('patrones', []), g.get('vehiculo', ''), info_ev)

        # B. Procesar eventos individuales
        tecnicos_en_grupos = set()
        for g in grupos_db:
            for t in g.get('tecnico_nombres', []):
                tecnicos_en_grupos.add(t)

        for ev in eventos_dia:
            if ev['id'] in ids_en_grupos: continue
            
            tec = ev.get('tecnico_nombre') or ev.get('Técnico') or '---'
            # Si existe un grupo de trabajo, no se muestran tarjetas para técnicos individuales que ya están en el grupo
            if tec in tecnicos_en_grupos: continue

            props = ev.get('extended_props') or ev.get('extendedProperties') or {}
            if isinstance(props, str):
                try: props = json.loads(props)
                except: props = {}
            priv = props.get('private', {})
            pats = priv.get('app_patrones', '[]')
            if isinstance(pats, str):
                try: pats = json.loads(pats)
                except: pats = []
            
            procesar_agrupacion([tec], pats, priv.get('app_vehiculo', ''), ev)

        # 4. Formatear Resultado Final
        resultado = []
        for key, data in agrupados.items():
            inits = sorted([get_inits(t) for t in data['tecnicos']])
            tag = "/".join(inits)
            
            ots_txt = ", ".join(sorted(list(data['ots'])))
            clientes = " / ".join(list(set([str(d['cliente']) for d in data['detalles_ots']])))
            asuntos = " / ".join(list(set([str(d['asunto']) for d in data['detalles_ots']])))
            direcciones = " / ".join(list(set([str(d['direccion']) for d in data['detalles_ots']])))

            resultado.append({
                "grupo_id": f"group-{'-'.join(inits)}",
                "ot_nro": ots_txt,
                "tag": tag,
                "tecnicos": sorted(list(data['tecnicos'])),
                "patrones": sorted(list(data['patrones'])),
                "vehiculo": ", ".join(data['vehiculos']) if data['vehiculos'] else "N/A",
                "cliente": clientes,
                "direccion": direcciones, 
                "asunto": asuntos,
                "detalles_ots": data['detalles_ots']
            })
                
        return resultado
    except Exception as e:
        import traceback; print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/grupos/{grupo_id}/repair")
async def api_repair_group(grupo_id: str):
    await check_authorization()
    try:
        from group_repair import repair_group
        success, messages = repair_group(db, grupo_id)
        return {"status": "ok" if success else "error", "messages": messages}
    except Exception as e:
        import traceback; print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

class RegistrarGrupoParams(BaseModel):
    grupo_id: str
    ot_nro: str
    fecha: str
    event_ids: List[str]
    tecnicos: List[str]
    patrones: List[str]
    vehiculo: Optional[str] = None

@app.post("/api/grupos/registrar")
async def registrar_grupo(params: RegistrarGrupoParams):
    await check_authorization()
    try:
        db.crear_o_actualizar_grupo({
            "grupo_id": params.grupo_id,
            "ot_nro": params.ot_nro,
            "fecha": params.fecha,
            "event_ids": params.event_ids,
            "tecnico_nombres": params.tecnicos,
            "patrones": params.patrones,
            "vehiculo": params.vehiculo
        })

        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/grupos/evento/{event_id}")
async def obtener_grupo_evento(event_id: str):
    """Busca el grupo de un evento por google_event_id o por id interno (local_xxx)."""
    try:
        # Búsqueda directa por el ID recibido (puede ser google_event_id o local_id)
        grupo = db.obtener_grupo_de_evento(event_id)
        if grupo:
            return grupo
        # Fallback: el frontend puede pasar el google_event_id pero el grupo registra el id interno
        ev_interno = db.resolve_event(event_id)
        if ev_interno and ev_interno.get('id') and ev_interno['id'] != event_id:
            grupo = db.obtener_grupo_de_evento(ev_interno['id'])
            if grupo:
                return grupo
        return {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/eventos/{event_id}/quitar_tecnico")
async def quitar_tecnico(event_id: str, calendar_id: str = Query(...)):
    await check_authorization()
    """Elimina a un tecnico de un grupo y actualiza los títulos de los demás localmente."""
    try:
        # 1. Resolver evento e identidad
        ev_interno = db.resolve_event(event_id)
        if not ev_interno:
            # El borrado debe ser idempotente. Si ya no existe (ej. doble clic), retornamos OK.
            return {"status": "ok", "detail": "Evento ya eliminado"}

        event_id = ev_interno['id']
        calendar_id = ev_interno['calendar_id']
        tec_rem = ev_interno['tecnico']

        # 2. Identificar el grupo
        grupo = db.obtener_grupo_de_evento(event_id)
        if not grupo:
            google_id_to_delete = ev_interno.get('google_event_id') or event_id
            
            # Si es complejo y no está individualizado, borramos todos los eventos locales
            # que compartan el mismo google_event_id para garantizar que le pegamos al owner.
            if _is_complex_event(ev_interno):
                print(f"[DELETE] Evento complejo sin individualizar. Aplicando borrado global a {google_id_to_delete}")
                with db._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT id, calendar_id, tecnico_nombre FROM eventos WHERE google_event_id = ? OR id = ?", (google_id_to_delete, google_id_to_delete))
                    relatives = cursor.fetchall()
                
                for rel_id, rel_cal, rel_tec in relatives:
                    db.log_trace(rel_id, "mutation_created", {
                        "type": "DELETE",
                        "tecnico": rel_tec,
                        "calendar_id": rel_cal,
                        "origin": "complex_global_delete"
                    }, calendar_id=rel_cal, tag="OUTBOUND_MUTATION")
                    db.enqueue_sync(google_id_to_delete, rel_cal, rel_tec, "DELETE")
                    db.eliminar_evento_individual(rel_id)
                return {"status": "ok", "detail": "Evento complejo eliminado globalmente"}

            # Sin grupo, no complejo: Borrado simple local con sync outbound
            # [OUTBOUND_MUTATION] mutation_created
            db.log_trace(event_id, "mutation_created", {
                "type": "DELETE",
                "tecnico": tec_rem,
                "calendar_id": calendar_id
            }, calendar_id=calendar_id, tag="OUTBOUND_MUTATION")

            db.enqueue_sync(google_id_to_delete, calendar_id, tec_rem, "DELETE")
            db.eliminar_evento_individual(event_id)
            return {"status": "ok"}

        grupo_id = grupo['grupo_id']

        # 2. Encolar DELETE y marcar localmente
        # 3. Calcular nueva composición y encontrar el índice de forma segura
        # Resolver cada event_id del grupo para comparar con nuestro event_id físico y google_event_id
        idx_removed = -1
        google_id_to_compare = ev_interno.get('google_event_id') or event_id
        for i, gid in enumerate(grupo['event_ids']):
            if gid == event_id or gid == google_id_to_compare:
                idx_removed = i
                break
            # Por las dudas, resolver en BD
            mem = db.resolve_event(gid)
            if mem and (mem['id'] == event_id or mem.get('google_event_id') == google_id_to_compare):
                idx_removed = i
                break
                
        if idx_removed == -1:
            # Fallback en caso de inconsistencia extrema
            tec_rem = ev_interno.get('tecnico_nombre') or ev_interno.get('tecnico')
            new_tecnico_nombres = list(grupo['tecnico_nombres'])
            new_event_ids = [eid for eid in grupo['event_ids'] if eid != event_id and eid != google_id_to_compare]
        else:
            tec_rem = grupo['tecnico_nombres'][idx_removed]
            new_tecnico_nombres = [n for i, n in enumerate(grupo['tecnico_nombres']) if i != idx_removed]
            new_event_ids = [eid for i, eid in enumerate(grupo['event_ids']) if i != idx_removed]
        
        # [OUTBOUND_MUTATION] mutation_created
        db.log_trace(event_id, "mutation_created", {
            "type": "DELETE",
            "tecnico": tec_rem,
            "calendar_id": calendar_id
        }, calendar_id=calendar_id, tag="OUTBOUND_MUTATION")

        google_id_to_delete = ev_interno.get('google_event_id') or event_id
        db.enqueue_sync(google_id_to_delete, calendar_id, tec_rem, "DELETE")
        db.eliminar_evento_individual(event_id)
        
        # 4. Actualizar o disolver grupo
        if not new_event_ids or len(new_event_ids) <= 1:
            # Disolver grupo
            db.eliminar_grupo(grupo_id)
            # Limpiar título (quitar tag de iniciales) del miembro restante
            if new_event_ids:
                last_ev = db.resolve_event(new_event_ids[0])
                if last_ev:
                    from utils import get_ot_base_from_event
                    clean_title = get_ot_base_from_event(last_ev)
                    titulo_orig = last_ev.get('evento') or last_ev.get('summary') or ''
                    if clean_title and clean_title != titulo_orig:
                        db.actualizar_titulo_evento(new_event_ids[0], clean_title)
                        gid_last = last_ev.get('google_event_id') or new_event_ids[0]
                        tec_last = last_ev.get('tecnico_nombre') or last_ev.get('tecnico') or ''
                        db.enqueue_sync(gid_last, last_ev['calendar_id'], tec_last, "UPDATE")
                        db.log_trace(new_event_ids[0], "mutation_created", {
                            "type": "UPDATE", "origin": "grupo_disuelto_clean_title", "nuevo_titulo": clean_title
                        }, calendar_id=last_ev['calendar_id'], tag="GROUP_LIFECYCLE")
        else:
            db.crear_o_actualizar_grupo({**grupo, "event_ids": new_event_ids, "tecnico_nombres": new_tecnico_nombres})
            await update_group_title(grupo_id)
            
        if len(new_event_ids) > 1:
            validate_group_integrity(db, grupo_id)

        db.update_last_sync()

        return {"status": "ok"}
    except Exception as e:
        print("Error en quitar_tecnico:", e)
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
# SINCRONIZACIÓN
# ─────────────────────────────────────────────

@app.get("/api/sync/status")
async def get_sync_status():
    """
    Retorna el estado actual de la cola de sincronización.
    El frontend puede pollear este endpoint para mostrar indicadores de estado.
    """
    try:
        pending = db.count_queue_by_status("PENDING")
        processing = db.count_queue_by_status("PROCESSING")
        failed  = db.count_queue_by_status("FAILED")
        logs    = db.get_sync_logs(limit=20)

        return {
            "pending":    pending,
            "processing": processing,
            "failed":     failed,
            "last_sync":  db.get_last_sync(),
            "logs":       logs,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sync")
async def sync_cloud():
    print("[LEGACY_DISABLED] api_server.sync_cloud: El endpoint de sincronización masiva está desactivado.")
    return {
        "status": "legacy_disabled",
        "message": "La sincronización masiva ha sido desactivada en favor del Polling incremental.",
        "last_sync": db.get_last_sync()
    }
    """Sincroniza en un thread separado para no bloquear el event loop."""
    try:
        def _do_sync():
            svc_cal, svc_sheets = extractor._safe_get_google_services()
            
            # 1. Cargar Configuración Dinámica
            app_config = db.get_app_config()

            # 2. Obtener Técnicos desde la configuración en lugar de Sheets
            tecnicos_config = app_config.get("technicians", {})
            tecnicos = []
            for email, data in tecnicos_config.items():
                if data.get("enabled", False):
                    tecnicos.append({
                        "nombre": data.get("alias", email.split('@')[0]),
                        "correo": email,
                        "iniciales": data.get("iniciales", ""),
                        "servicio": data.get("service", "")
                    })
            
            # Si aún no han configurado nada, como fallback leemos de sheets para no romperles el sistema en la transición
            if not tecnicos:
                tecnicos = extractor.obtener_tecnicos(svc_sheets)

            db.guardar_tecnicos(tecnicos)

            ots, headers = extractor.actualizar_ots_desde_sheets(svc_sheets)
            if headers:
                ots_list = [headers] + [[item.get(h, "") for h in headers] for item in ots]
                db.guardar_bd_ots(ots_list)

            patrones = extractor.actualizar_patrones_desde_sheets(svc_sheets)
            db.guardar_patrones(patrones)

            vehiculos = extractor.actualizar_vehiculos_desde_sheets(svc_sheets)
            db.guardar_vehiculos(vehiculos)

            todos_eventos = []
            
            # Rangos dinámicos según configuración
            dias_pasados = int(app_config.get("sync_days_past", 30))
            dias_futuros = int(app_config.get("sync_days_future", 180))
            time_min = (datetime.datetime.utcnow() - datetime.timedelta(days=dias_pasados)).isoformat() + 'Z'
            time_max = (datetime.datetime.utcnow() + datetime.timedelta(days=dias_futuros)).isoformat() + 'Z'

            for t in tecnicos:
                try:
                    events_result = svc_cal.events().list(
                        calendarId=t['correo'],
                        timeMin=time_min,
                        timeMax=time_max,
                        maxResults=500,
                        singleEvents=True,
                        orderBy='startTime'
                    ).execute()
                    for item in events_result.get('items', []):
                        # Filtrar eventos "fantasma" (ubicaciones, tiempos de enfoque, etc.)
                        ev_type = item.get('eventType', 'default')
                        if ev_type in ['workingLocation', 'focusTime', 'outOfOffice']:
                            continue
                        
                        item["tecnico"] = t['nombre']
                        item['evento'] = item.get('summary', 'Sin título')
                        item['inicio'] = item['start'].get('dateTime', item['start'].get('date'))
                        item['fin'] = item['end'].get('dateTime', item['end'].get('date'))
                        item["ubicacion"] = item.get('location', '')
                        item["descripcion"] = item.get('description', '')
                        item['calendar_id'] = t['correo']
                        todos_eventos.append(item)
                except Exception as e:
                    print(f"Error descargando eventos de {t['nombre']}: {e}")

            db.guardar_eventos(todos_eventos)
            db.update_last_sync()

        return {
                "status": "ok",
                "message": "Sincronización completa",
                "last_sync": db.get_last_sync(),
                "tecnicos": len(tecnicos),
                "eventos": len(todos_eventos)
            }

        result = await run_in_threadpool(_do_sync)
        return result
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
# ARCHIVOS ESTÁTICOS
# ─────────────────────────────────────────────

@app.delete("/api/eventos/{event_id}")
async def eliminar_evento(event_id: str, calendar_id: str = Query(...)):
    await check_authorization()
    """Elimina un evento individual o lo quita del grupo."""
    return await quitar_tecnico(event_id, calendar_id)


# ─────────────────────────────────────────────────────────────────────────────
# POLLING — Google Calendar → Local
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/poll/status")
async def get_poll_status():
    """Estado del polling: último ciclo por calendario y cola de revisión pendiente."""
    status = db.get_poll_status()
    status["polling_active"] = poll_manager._running
    return status

@app.post("/api/poll/start")
async def start_poll():
    """Inicia el ciclo de polling tras validar el checklist. Idempotente."""
    await check_authorization()
    if poll_manager._running:
        return {"status": "already_running"}
    ok = await run_in_threadpool(poll_manager.start, sync_worker)
    if not ok:
        raise HTTPException(status_code=409,
            detail="Pre-polling checklist falló. Revisar logs del servidor.")
    return {"status": "started"}

@app.post("/api/poll/stop")
async def stop_poll():
    """Detiene el ciclo de polling."""
    await check_authorization()
    poll_manager.stop()
    return {"status": "stopped"}

@app.post("/api/poll/trigger")
async def trigger_poll():
    """Dispara un ciclo de polling inmediato (para testing/admin). No requiere que esté activo."""
    await check_authorization()
    await run_in_threadpool(poll_manager._poll_all_calendars)
    return {"status": "triggered"}

@app.get("/api/poll/review_queue")
async def get_review_queue(limit: int = 50):
    """Lista cambios críticos detectados por polling que esperan revisión humana."""
    return db.get_poll_review_queue(limit=limit)

@app.get("/api/poll/debug/recent")
async def get_poll_debug_recent(limit: int = 500):
    await check_authorization()
    # Traer trazas de eventos y resúmenes de ciclo
    traces = db.get_poll_logs(limit=limit, event_type="POLL_TRACE")
    summaries = db.get_poll_logs(limit=100, event_type="POLLING")
    
    cycles = {}
    
    # 1. Procesar resúmenes (cycle_started, cycle_completed)
    for s in summaries:
        detail = s.get("detail", {})
        cid = detail.get("cycle_id")
        if not cid: continue
        
        if cid not in cycles:
            cycles[cid] = {"cycle_id": cid, "events": [], "summary": {}}
            
        if s["event_type"] == "POLLING:cycle_started":
            cycles[cid]["timestamp_start"] = s["timestamp"]
            cycles[cid]["summary"]["started"] = detail
        elif s["event_type"] == "POLLING:cycle_completed":
            cycles[cid]["timestamp_end"] = s["timestamp"]
            cycles[cid]["summary"]["completed"] = detail

    # 2. Procesar trazas de eventos
    for t in traces:
        detail = t.get("detail", {})
        cid = detail.get("cycle_id", "unknown")
        if cid not in cycles:
            cycles[cid] = {"cycle_id": cid, "events": [], "summary": {}}
        
        cycles[cid]["events"].append({
            "correlation_id": detail.get("correlation_id"),
            "event_id": t.get("event_id"),
            "decision": detail.get("decision"),
            "persistence": detail.get("persistence"),
            "diff": detail.get("diff_result"),
            "local_status": detail.get("local_status"),
            "timestamp": t["timestamp"]
        })
        
    # Ordenar por timestamp descendente
    sorted_cycles = sorted(cycles.values(), key=lambda x: x.get("timestamp_start", ""), reverse=True)
    return sorted_cycles

@app.get("/api/poll/report/latest")
async def get_poll_report_latest():
    """Resumen analítico del último ciclo de polling."""
    await check_authorization()
    recent = poll_reporter.get_recent_cycles(limit=1)
    if not recent:
        raise HTTPException(status_code=404, detail="No cycles found")
    return poll_reporter.get_cycle_report(recent[0]["cycle_id"])

@app.get("/api/poll/report/recent")
async def get_poll_report_recent(limit: int = 20):
    """Últimos N ciclos con sus métricas operacionales."""
    await check_authorization()
    return poll_reporter.get_recent_cycles(limit=limit)

@app.get("/api/poll/report/event/{google_event_id}")
async def get_poll_report_event_history(google_event_id: str):
    """Historial completo de trazabilidad para un evento específico."""
    await check_authorization()
    return poll_reporter.get_event_history(google_event_id)

@app.get("/api/poll/report/drift/{calendar_id}")
async def get_poll_drift_report(calendar_id: str):
    """Detección de drift entre Google Calendar y SQLite para un técnico."""
    await check_authorization()
    return poll_reporter.perform_drift_detection(calendar_id)


# ─────────────────────────────────────────────────────────────────────────────
# ARBITRAJE HUMANO — Review Queue Semántica
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/review/pending")
async def get_pending_reviews(limit: int = 100):
    """
    [ARBITRATION] Lista los conflictos pendientes de revisión humana,
    enriquecidos con datos del evento local y snapshots.
    """
    return db.get_poll_review_queue(limit=limit)

@app.post("/api/review/{review_id}/accept")
async def accept_review(review_id: str):
    """
    [REVIEW_ACCEPTED] Acepta el cambio externo (Google → SQLite).
    - FIELD_CHANGE: aplica campos del diff al evento local, incrementa versión.
    - REMOTE_DELETE: marca evento como CANCELLED_IN_GOOGLE.

    [INBOUND_FIX] HTTP 422 si la mutación SQLite no ocurre (lookup miss).
    [OCC] HTTP 409 si el evento fue modificado después de detectar el conflicto (STALE_REVIEW).
    El operador recibe error explícito en lugar de false-200.
    """
    await check_authorization()
    try:
        result = db.accept_review(review_id)
        # Log trazabilidad
        db.write_poll_log(
            log_id=str(uuid.uuid4()),
            timestamp=datetime.datetime.utcnow().isoformat() + "Z",
            event_type="REVIEW_ACCEPTED",
            calendar_id=None,
            event_id=result["event_id"],
            version=None,
            detail=json.dumps(result)
        )
        return result
    except ValueError as e:
        err = str(e)
        # [OCC] Review obsoleto: el evento mutó después de la detección del conflicto
        if err.startswith("STALE_REVIEW"):
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "STALE_REVIEW",
                    "message": err,
                    "hint": "El evento fue modificado después de que este conflicto fue detectado. Refrescá el Inbox para ver el estado actualizado."
                }
            )
        # Distinguir: review no encontrado (404) vs mutación fallida (422)
        if "no encontrado en SQLite" in err or "lookup" in err.lower():
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "SQLITE_MUTATION_FAILED",
                    "message": err,
                    "hint": "El evento no pudo ser localizado en SQLite. Ver logs ARBITRATION_TRACE:SQLITE_LOOKUP_MISS para diagnóstico."
                }
            )
        raise HTTPException(status_code=404, detail=err)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/review/{review_id}/reject")
async def reject_review(review_id: str):
    """
    [REVIEW_REJECTED] Rechaza el cambio externo (SQLite → Google resync).
    - FIELD_CHANGE: encola UPDATE outbound con estado local.
    - REMOTE_DELETE: encola CREATE outbound para restaurar en Google.
    """
    await check_authorization()
    try:
        result = db.reject_review(review_id)
        db.write_poll_log(
            log_id=str(uuid.uuid4()),
            timestamp=datetime.datetime.utcnow().isoformat() + "Z",
            event_type="REVIEW_REJECTED",
            calendar_id=None,
            event_id=result["event_id"],
            version=None,
            detail=json.dumps(result)
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/review/{review_id}/defer")
async def defer_review(review_id: str):
    """
    [REVIEW_DEFERRED] Pospone un review sin tomar acción.
    El review no aparecerá en la lista PENDING hasta ser reanudado manualmente.
    """
    await check_authorization()
    try:
        result = db.defer_review(review_id)
        db.write_poll_log(
            log_id=str(uuid.uuid4()),
            timestamp=datetime.datetime.utcnow().isoformat() + "Z",
            event_type="REVIEW_DEFERRED",
            calendar_id=None,
            event_id=review_id,
            version=None,
            detail=json.dumps(result)
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/api/poll/review_queue/{review_id}/resolve")
async def resolve_review_legacy(review_id: str, action: str = Query(..., pattern="^(RESOLVED|IGNORED)$")):
    """[LEGACY] Usar /api/review/{id}/accept o /reject en su lugar."""
    await check_authorization()
    with db._get_connection() as conn:
        conn.execute(
            "UPDATE poll_review_queue SET status = ? WHERE review_id = ?",
            (action, review_id)
        )
        conn.commit()
    return {"status": action, "review_id": review_id}

@app.get("/api/poll/log")
async def get_poll_log(limit: int = 100):
    """Últimas entradas del log de polling para diagnóstico."""
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT log_id, timestamp, event_type, calendar_id, event_id, version, detail
            FROM poll_log ORDER BY timestamp DESC LIMIT ?
        """, (limit,))
        return [{"log_id": r[0], "timestamp": r[1], "event_type": r[2],
                 "calendar_id": r[3], "event_id": r[4], "version": r[5],
                 "detail": r[6]}
                for r in cursor.fetchall()]



class TraceLogRequest(BaseModel):
    event_id: str
    step: str
    detail: dict
    calendar_id: Optional[str] = None

@app.post("/api/trace")
async def log_frontend_trace(req: TraceLogRequest):
    """Permite al frontend registrar trazas de eventos en el log central."""
    db.log_trace(req.event_id, f"FRONTEND_{req.step}", req.detail, req.calendar_id)
    return {"status": "ok"}

# ─────────────────────────────────────────────────────────────────────────────
# POLL CONFIG — intervalo configurable desde UI
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/poll/config")
async def get_poll_config():
    """Lee la configuración de polling (intervalo)."""
    cfg = db.get_app_config()
    return {"interval_seconds": cfg.get("poll_interval_seconds", 300)}

@app.post("/api/poll/config")
async def set_poll_config(interval_seconds: int = Query(..., ge=60, le=3600)):
    """Guarda el intervalo de polling en app_config."""
    await check_authorization()
    cfg = db.get_app_config()
    cfg["poll_interval_seconds"] = interval_seconds
    db.set_app_config(cfg)
    import poll_manager as pm
    pm.POLL_INTERVAL_SECONDS = interval_seconds
    return {"status": "ok", "interval_seconds": interval_seconds}

@app.post("/api/poll/review_queue/{review_id}/apply")
async def apply_review_change(review_id: str):
    """
    Aplica un cambio crítico aprobado por el operador al evento local.
    Marca el review como APPLIED y, si es un DELETE, borra el evento.
    """
    await check_authorization()
    import traceback as tb
    try:
        row = db.get_review_by_id(review_id)
        if not row:
            raise HTTPException(status_code=404, detail="Review no encontrado")
        diff = json.loads(row["diff_json"])
        db.apply_poll_critical_change(row["event_id"], diff)
        with db._get_connection() as conn:
            conn.execute(
                "UPDATE poll_review_queue SET status='APPLIED' WHERE review_id=?",
                (review_id,)
            )
            conn.commit()
        return {"status": "APPLIED", "review_id": review_id, "event_id": row["event_id"]}
    except HTTPException:
        raise
    except Exception as e:
        print("[apply_review]", tb.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

# ── ADMIN & OBSERVABILITY ENDPOINTS ───────────────────────────
# ── ADMIN & OBSERVABILITY ENDPOINTS ───────────────────────────

@app.get("/api/system/drift_report")
async def get_system_drift_report():
    """
    [DRIFT_DETECTION] Reporte canónico de drift operacional.
    Cubre: eventos sin google_id, duplicados, reviews pendientes/reabiertos,
    CANCELLED visibles, fallas sync, polling lag, orphans, lookup_misses_24h.
    """
    await check_authorization()
    return observatory.get_full_drift_report()

@app.get("/api/admin/sync_health")
async def get_sync_health():
    await check_authorization()
    return observatory.get_dashboard_snapshot()

@app.get("/api/admin/drift_report")
async def get_drift_report():
    """[LEGACY] Usar /api/system/drift_report."""
    await check_authorization()
    return observatory.get_drift_report()

@app.get("/api/admin/event_timeline/{event_id}")
async def get_event_timeline(event_id: str):
    await check_authorization()
    return observatory.get_event_timeline(event_id)

@app.get("/api/admin/reconciliation_logs")
async def get_reconciliation_logs(limit: int = 50):
    await check_authorization()
    return observatory.get_reconciliation_decisions(limit=limit)

@app.get("/api/admin/sync_queue")
async def get_admin_sync_queue(limit: int = 50):
    await check_authorization()
    return db.get_pending_queue_items(limit=limit)

@app.get("/api/admin/poll_logs")
async def get_admin_poll_logs(limit: int = 100, type: str = None):
    await check_authorization()
    return db.get_poll_logs(limit=limit, event_type=type)

@app.get("/admin", include_in_schema=False)
async def admin_panel():
    from fastapi.responses import FileResponse
    path = get_resource_path("webapp/admin.html")
    return FileResponse(path)

# ── DRIFT MANAGER ENDPOINTS ───────────────────────────────────

@app.get("/api/drift")
async def get_drift_events():
    await check_authorization()
    # Leer drift events almacenados asincronamente
    drift_items = []
    try:
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT drift_id, event_id, calendar_id, drift_category, details_json, detected_at FROM drift_events ORDER BY detected_at DESC")
            for r in cursor.fetchall():
                import json
                try:
                    details = json.loads(r[4])
                except Exception:
                    details = {}
                drift_items.append({
                    "drift_id": r[0],
                    "event_id": r[1],
                    "calendar_id": r[2],
                    "drift_category": r[3],
                    "details": details,
                    "detected_at": r[5]
                })
    except Exception as e:
        print(f"Error fetching drift events: {e}")
        
    return {
        "status": "ok",
        "corrupt_sql": observatory.get_full_drift_report(),
        "drift_items": drift_items
    }



@app.get("/api/indicadores/ocupacion")
async def get_indicador_ocupacion(start_date: str, end_date: str):
    try:
        sd = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
        ed = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido")

    # Días hábiles sin feriados
    app_config = db.get_app_config()
    holiday_set = set(app_config.get("holidays", {}).keys())
    
    dias_habiles = []
    curr = sd
    while curr <= ed:
        if curr.weekday() < 5 and curr.strftime("%Y-%m-%d") not in holiday_set:
            dias_habiles.append(curr.strftime("%Y-%m-%d"))
        curr += datetime.timedelta(days=1)

    if not dias_habiles:
        return {"servicios": [], "dias_habiles_count": 0}

    tech_events = _build_tech_events()
    tecnicos_info = db.obtener_tecnicos()

    servicios_data = {}

    for t in tecnicos_info:
        nombre = t['nombre']
        t_servicios_raw = t.get("servicio", "")
        t_servicios = [s.strip() for s in t_servicios_raw.split(",") if s.strip()]
        if not t_servicios:
            t_servicios = ["Sin Servicio"]

        tech_sum_ot = 0.0
        tech_sum_all = 0.0

        for d_key in dias_habiles:
            evs = tech_events.get(nombre, {}).get(d_key, [])
            horas_ot_dia = 0.0
            horas_all_dia = 0.0
            for ev in evs:
                h = ev.get("horas", 0.0)
                horas_all_dia += h
                if ev.get("es_ot", False):
                    horas_ot_dia += h

            # Topar al 100% (9 horas)
            occ_ot_dia = min(1.0, horas_ot_dia / 9.0)
            occ_all_dia = min(1.0, horas_all_dia / 9.0)

            tech_sum_ot += occ_ot_dia
            tech_sum_all += occ_all_dia

        for srv in t_servicios:
            if srv not in servicios_data:
                servicios_data[srv] = {"techs_count": 0, "sum_ot": 0.0, "sum_all": 0.0}
            servicios_data[srv]["techs_count"] += 1
            servicios_data[srv]["sum_ot"] += tech_sum_ot
            servicios_data[srv]["sum_all"] += tech_sum_all

    res = []
    total_dias = len(dias_habiles)
    for srv, data in servicios_data.items():
        count = data["techs_count"]
        if count > 0 and total_dias > 0:
            avg_ot = data["sum_ot"] / (count * total_dias)
            avg_all = data["sum_all"] / (count * total_dias)
        else:
            avg_ot = 0.0
            avg_all = 0.0

        res.append({
            "servicio": srv,
            "ocupacion_ot": round(avg_ot * 100, 1),
            "ocupacion_all": round(avg_all * 100, 1),
            "tecnicos_count": count
        })

    res.sort(key=lambda x: x["ocupacion_all"], reverse=True)
    return {"servicios": res, "dias_habiles_count": total_dias}


# ── INICIO DE LA APLICACIÓN ───────────────────────────────────

webapp_path = get_resource_path("webapp")
app.mount("/", StaticFiles(directory=webapp_path, html=True), name="webapp")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
