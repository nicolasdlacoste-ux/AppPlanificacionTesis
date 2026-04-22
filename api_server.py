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
import threading
import time
import uuid
import re
import googleapiclient.errors
import sys

import utils
import engine
from data_manager import DataManager
import extractor

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
        # Si han pasado más de 30s sin pulso, cerramos el proceso completo
        if time.time() - _last_heartbeat > 30:
            print("\n[!] Heartbeat perdido (ventana cerrada). Finalizando aplicación...")
            os._exit(0)

# Iniciar hilo de monitoreo
threading.Thread(target=_watchdog_shutdown, daemon=True).start()

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def generar_descripcion_enriquecida(base_desc, patrones, vehiculo):
    """
    Combina la descripción base con los patrones y el vehículo en un bloque visual.
    Si ya existe un bloque previo, lo reemplaza.
    """
    # Limpiar base_desc de bloques anteriores si existen (usamos el separador como guía)
    if base_desc and "──────────" in base_desc:
        # Dividir por el separador y tomar la primera parte
        base_desc = base_desc.split("──────────")[0].strip()
    
    metadata_lines = []
    if patrones:
        # Asegurar que patrones sea una lista
        p_list = patrones if isinstance(patrones, list) else [patrones]
        metadata_lines.append(f"🛠️ Patrones: {', '.join(p_list)}")
    if vehiculo:
        metadata_lines.append(f"🚐 Vehículo: {vehiculo}")
    
    if not metadata_lines:
        return (base_desc or "").strip()
        
    res = (base_desc or "").strip()
    res += "\n\n─────────────────────────────────────────────\n"
    res += "\n".join(metadata_lines)
    res += "\n─────────────────────────────────────────────"
    return res.strip()

def _build_tech_events():
    """Construye el diccionario tech_events que espera engine.py desde la DB."""
    eventos = db.obtener_eventos_dict()
    tech_events = {}

    for ev in eventos:
        tech = str(ev.get("Técnico", "")).strip()
        if not tech:
            continue
        if tech not in tech_events:
            tech_events[tech] = {}

        start_str = ev.get("Inicio", "")
        end_str = ev.get("Fin", "")
        summary = ev.get("Evento", "")

        if not start_str or not end_str:
            continue

        idx_p = summary.find(')')
        ot = summary[:idx_p + 1].strip() if idx_p != -1 else summary.split('-')[0].strip()
        es_todo_el_dia = "T" not in start_str
        es_ot = (ot and ot[0].isdigit()) or "RESERVA" in summary.upper()

        try:
            if es_todo_el_dia:
                start_date = datetime.datetime.strptime(start_str, "%Y-%m-%d").date()
                end_date = datetime.datetime.strptime(end_str, "%Y-%m-%d").date()
                dias = max(1, (end_date - start_date).days)
                for i in range(dias):
                    d = start_date + datetime.timedelta(days=i)
                    dk = d.strftime("%Y-%m-%d")
                    tech_events[tech].setdefault(dk, []).append({
                        "sort": 700, "sort_end": 1600, "text": f"07:00-16:00 | {ot}",
                        "horas": 0.0 if d.weekday() >= 5 else 9.0, "es_ot": es_ot,
                        "original_text": summary,
                        "extendedProperties": ev.get("extendedProperties", {}),
                        "id": ev.get("id"), "calendar_id": ev.get("calendar_id"),
                        "Inicio": start_str, "Fin": end_str,
                        "description": ev.get("Descripción", "")
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
                        "extendedProperties": ev.get("extendedProperties", {}),
                        "id": ev.get("id"), "calendar_id": ev.get("calendar_id"),
                        "Inicio": start_str, "Fin": end_str,
                        "description": ev.get("Descripción", "")
                    })
        except Exception as e:
            print(f"Error procesando evento {summary}: {e}")

    for t in tech_events:
        for d in tech_events[t]:
            tech_events[t][d].sort(key=lambda x: (x["sort"], x.get("sort_end", 9999)))

    return tech_events


@app.post("/api/heartbeat")
async def receive_heartbeat():
    global _last_heartbeat
    _last_heartbeat = time.time()
    return {"status": "alive"}


# ─────────────────────────────────────────────
# ENDPOINTS DE LECTURA
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
            if "nombre" in first or "patron" in first:
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
                        "direccion": row[utils.IDX_DIRECCION].strip() if len(row) > utils.IDX_DIRECCION else "",
                        "fecha": row[utils.IDX_FECHA] if len(row) > utils.IDX_FECHA else ""
                    }
                else:
                    if trabajo_item and trabajo_item not in ots_agrupadas[nro_ot]["trabajos"]:
                        ots_agrupadas[nro_ot]["trabajos"].append(trabajo_item)
        
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
        result = []
        for ev in eventos_raw:
            result.append({
                "id": ev["id"],
                "resourceId": ev["Técnico"],
                "title": ev["Evento"],
                "start": ev["Inicio"],
                "end": ev["Fin"],
                "description": ev.get("Descripción", ""),
                "extendedProperties": ev.get("extendedProperties", {}),
                "calendarId": ev.get("calendar_id", ""),
            })
        return result
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

@app.post("/api/engine/buscar")
async def buscar_disponibilidad(params: BuscarParams):
    try:
        tech_events = _build_tech_events()
        tecnicos_info = db.obtener_tecnicos()
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
            ots_objetivo=params.ots_seleccionadas
        )
        res_flex = engine.buscar_disponibilidad(
            tech_events, tecnicos_info, params.n_tec, params.jornadas,
            params.consecutivo, params.viaje, f_inicio, 120, ignorar_no_ots=True,
            patrones_requeridos=params.patrones_requeridos,
            excluir_conflictos_pats=params.excluir_conflictos_pats,
            ots_objetivo=params.ots_seleccionadas
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
                                               ots_objetivo=params.ots_seleccionadas)
        res_flex = engine.buscar_disponibilidad(tech_events, tecnicos_info, params.n_tec, params.jornadas,
                                                params.consecutivo, params.viaje, f_pivot, 120,
                                                ignorar_no_ots=True, patrones_requeridos=params.patrones_requeridos,
                                                excluir_conflictos_pats=params.excluir_conflictos_pats,
                                                ots_objetivo=params.ots_seleccionadas)
        return {"estrictas": ser(res_est), "flexibles": ser(res_flex)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
# CREACIÓN / MOVIMIENTO / ELIMINACIÓN
# ─────────────────────────────────────────────

class CrearEventoParams(BaseModel):
    correo_tecnico: str
    titulo: str
    descripcion: str = ""
    fecha: str  # YYYY-MM-DD
    h_start: float = 7.0
    h_dur: float = 9.0
    patrones: List[str] = []
    ots: List[str] = []
    vehiculo: Optional[str] = None
    requiere_vehiculo: bool = False

@app.post("/api/eventos/crear")
async def crear_evento(params: CrearEventoParams):
    try:
        fecha = datetime.date.fromisoformat(params.fecha)
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

        inicio_str = f"{params.fecha}T{h_int:02d}:{m_int:02d}:00-03:00"
        fin_str    = f"{params.fecha}T{h_fin_int:02d}:{m_fin_int:02d}:00-03:00"

        desc_enriquecida = generar_descripcion_enriquecida(params.descripcion, params.patrones, params.vehiculo)

        event_body = {
            'summary': params.titulo,
            'description': desc_enriquecida,
            'start': {'dateTime': inicio_str, 'timeZone': 'America/Argentina/Buenos_Aires'},
            'end':   {'dateTime': fin_str,    'timeZone': 'America/Argentina/Buenos_Aires'},
            'extendedProperties': {'private': metadata}
        }

        def _insert():
            svc_cal, _ = extractor.get_google_services()
            return svc_cal.events().insert(
                calendarId=params.correo_tecnico, body=event_body
            ).execute()

        result = await run_in_threadpool(_insert)
        event_id = result.get("id")

        # Resolver nombre del técnico desde el correo para la DB local
        tec_nombre = params.correo_tecnico
        tecs = db.obtener_tecnicos()
        t_match = next((t for t in tecs if t['correo'] == params.correo_tecnico), None)
        if t_match:
            tec_nombre = t_match['nombre']

        # Persistir inmediatamente en SQLite (sin esperar el próximo sync completo)
        db.guardar_evento_individual({
            "id": event_id,
            "calendar_id": params.correo_tecnico,
            "tecnico_nombre": tec_nombre,
            "summary": params.titulo,
            "inicio": inicio_str,
            "fin": fin_str,
            "ubicacion": "",
            "descripcion": params.descripcion,
            "extendedProperties": {'private': metadata}
        })
        db.update_last_sync()

        # Retornar evento en el formato que espera _eventos[] del frontend
        return {
            "status": "ok",
            "event_id": event_id,
            "event": {
                "id": event_id,
                "resourceId": tec_nombre,
                "title": params.titulo,
                "start": inicio_str,
                "end": fin_str,
                "description": params.descripcion,
                "extendedProperties": {'private': metadata},
                "calendarId": params.correo_tecnico,
            }
        }
    except Exception as e:
        import traceback; print(traceback.format_exc())
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
    vehiculo: Optional[str] = None
    requiere_vehiculo: Optional[bool] = None

@app.patch("/api/eventos/{event_id}/mover")
async def mover_evento(event_id: str, params: MoverEventoParams):
    try:
        svc_cal, _ = await run_in_threadpool(extractor.get_google_services)

        # Fetch current event
        ev_actual = svc_cal.events().get(
            calendarId=params.calendar_id_origen, eventId=event_id
        ).execute()
        start_orig = ev_actual["start"].get("dateTime", ev_actual["start"].get("date"))
        end_orig = ev_actual["end"].get("dateTime", ev_actual["end"].get("date"))

        nueva_f = datetime.date.fromisoformat(params.nueva_fecha)
        tz_suffix = "-03:00"

        if params.h_start is not None:
            # Si se proporciona h_start pero no h_dur, calculamos la duración original
            dur = params.h_dur
            if dur is None:
                try:
                    dt_s = datetime.datetime.fromisoformat(start_orig.replace('Z', '+00:00'))
                    dt_e = datetime.datetime.fromisoformat(end_orig.replace('Z', '+00:00'))
                    dur = (dt_e - dt_s).total_seconds() / 3600.0
                except:
                    dur = 1.0 # Fallback 1h si algo falla
            
            hs = params.h_start
            he = hs + dur
            h_int, m_int = int(hs), int((hs % 1) * 60)
            he_int, me_int = int(he), int((he % 1) * 60)
            nuevo_s = f"{nueva_f}T{h_int:02d}:{m_int:02d}:00{tz_suffix}"
            nuevo_e = f"{nueva_f}T{he_int:02d}:{me_int:02d}:00{tz_suffix}"
        elif "T" in start_orig:
            # Conservar hora original, solo cambiar fecha
            dt_s = datetime.datetime.fromisoformat(start_orig.replace('Z', '+00:00'))
            dt_e = datetime.datetime.fromisoformat(end_orig.replace('Z', '+00:00'))
            delta = (nueva_f - dt_s.date()).days
            new_s_dt = dt_s + datetime.timedelta(days=delta)
            new_e_dt = dt_e + datetime.timedelta(days=delta)
            nuevo_s = new_s_dt.strftime(f"%Y-%m-%dT%H:%M:%S{tz_suffix}")
            nuevo_e = new_e_dt.strftime(f"%Y-%m-%dT%H:%M:%S{tz_suffix}")
        else:
            nuevo_s = nueva_f.isoformat()
            nuevo_e = (nueva_f + datetime.timedelta(days=1)).isoformat()

        # ── Actualizar metadatos con los cambios recibidos ───────────────
        metadata = ev_actual.get('extendedProperties', {}).get('private', {})
        if params.ots is not None:
            metadata["app_ots"] = json.dumps(params.ots)
        if params.patrones is not None:
            metadata["app_patrones"] = json.dumps(params.patrones)
        if params.vehiculo is not None:
            metadata["app_vehiculo"] = params.vehiculo
        if params.requiere_vehiculo is not None:
            metadata["app_requiere_vehiculo"] = str(params.requiere_vehiculo).lower()

        full_props = ev_actual.get('extendedProperties', {}).copy()
        full_props["private"] = metadata

        # ── Descripción enriquecida ───────────────────────────────────────
        try:
            pats_actuales = json.loads(metadata.get('app_patrones', '[]') or '[]')
        except:
            pats_actuales = []

        base_desc = params.descripcion if params.descripcion is not None else ev_actual.get('description', '')
        if any(x is not None for x in [params.descripcion, params.patrones, params.vehiculo]):
            desc_final = generar_descripcion_enriquecida(
                base_desc,
                params.patrones if params.patrones is not None else pats_actuales,
                params.vehiculo if params.vehiculo is not None else metadata.get('app_vehiculo', '')
            )
        else:
            desc_final = base_desc

        # ── Resolver técnico destino ──────────────────────────────────────
        target_cal = params.correo_destino or params.calendar_id_origen
        tecs = db.obtener_tecnicos()
        t_match = next((t for t in tecs if t['correo'] == target_cal or t['nombre'] == target_cal), None)
        tec_nombre = t_match['nombre'] if t_match else target_cal

        nuevo_titulo = params.titulo if params.titulo is not None else ev_actual.get('summary', '')

        # ── Cuerpo completo del evento ────────────────────────────────────
        event_body = {
            "summary":     nuevo_titulo,
            "description": desc_final,
            "start": {"dateTime": nuevo_s, "timeZone": "America/Argentina/Buenos_Aires"},
            "end":   {"dateTime": nuevo_e, "timeZone": "America/Argentina/Buenos_Aires"},
            "extendedProperties": {"private": metadata}
        }

        # ── Mover entre técnicos con fallback inteligente ─────────────────
        cambio_tecnico = bool(params.correo_destino and params.correo_destino != params.calendar_id_origen)
        nuevo_event_id = event_id

        if cambio_tecnico:
            try:
                # Intento primario: API nativa de Google (preserva el ID original)
                svc_cal.events().move(
                    calendarId=params.calendar_id_origen,
                    eventId=event_id,
                    destination=params.correo_destino
                ).execute()
                svc_cal.events().patch(
                    calendarId=target_cal, eventId=event_id, body=event_body
                ).execute()
                print(f"[mover] move() exitoso → id={event_id}")

            except googleapiclient.errors.HttpError as http_err:
                # Fallback: evento es copia de asistente o restringido, Google no permite moverlo/parchearlo
                # → Eliminar en origen e insertar en destino con los mismos datos
                is_restr = (http_err.status_code == 400 and 'cannotChangeOrganizer' in str(http_err)) or (http_err.status_code == 403)
                if is_restr:
                    print(f"[mover] Error {http_err.status_code} detectado → delete+insert fallback")
                    svc_cal.events().delete(
                        calendarId=params.calendar_id_origen, eventId=event_id
                    ).execute()
                    result = svc_cal.events().insert(
                        calendarId=target_cal, body=event_body
                    ).execute()
                    nuevo_event_id = result.get("id")
                    print(f"[mover] Re-creado tras error {http_err.status_code} con nuevo id={nuevo_event_id}")
                else:
                    raise  # Otro error HTTP → propagar sin ocultar
        else:
            # Mismo técnico: patch directo (hora, fecha, campos adicionales)
            try:
                svc_cal.events().patch(
                    calendarId=target_cal, eventId=event_id, body=event_body
                ).execute()
            except googleapiclient.errors.HttpError as http_err:
                if http_err.status_code == 403:
                    # Fallback para 403 Forbidden en el mismo calendario
                    print(f"[mover] 403 Forbidden en mismo técnico → delete+insert fallback")
                    svc_cal.events().delete(
                        calendarId=params.calendar_id_origen, eventId=event_id
                    ).execute()
                    result = svc_cal.events().insert(
                        calendarId=target_cal, body=event_body
                    ).execute()
                    nuevo_event_id = result.get("id")
                    print(f"[mover] Re-creado tras 403 con nuevo id={nuevo_event_id}")
                else:
                    raise

        # ── Persistir en SQLite ───────────────────────────────────────────
        if nuevo_event_id != event_id:
            # ID cambió tras re-creación → reemplazar registro
            db.eliminar_evento_individual(event_id)
            db.guardar_evento_individual({
                "id":            nuevo_event_id,
                "calendar_id":   target_cal,
                "tecnico_nombre":tec_nombre,
                "summary":       nuevo_titulo,
                "inicio":        nuevo_s,
                "fin":           nuevo_e,
                "ubicacion":     "",
                "descripcion":   desc_final,
                "extendedProperties": full_props
            })
        else:
            db.actualizar_evento_individual(nuevo_event_id, target_cal, {
                "Técnico":    tec_nombre,
                "Evento":     nuevo_titulo,
                "Inicio":     nuevo_s,
                "Fin":        nuevo_e,
                "Descripción":desc_final,
                "extendedProperties": full_props
            })

        db.update_last_sync()
        return {"status": "ok", "event_id": nuevo_event_id}
    except Exception as e:
        import traceback
        err_msg = f"{type(e).__name__}: {str(e) or 'Error interno sin mensaje'}"
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=err_msg)


@app.post("/api/eventos/{event_id}/split")
async def split_evento(event_id: str, calendar_id: str = Query(...)):
    """Divide un evento multi-día en N eventos de un solo día (07:00-16:00)."""
    try:
        svc_cal, _ = await run_in_threadpool(extractor.get_google_services)
        
        # 1. Obtener el evento original
        ev = svc_cal.events().get(calendarId=calendar_id, eventId=event_id).execute()
        titulo = ev.get('summary', 'Sin título')
        desc = ev.get('description', '')
        props = ev.get('extendedProperties', {})
        
        s_raw = ev['start'].get('dateTime') or ev['start'].get('date')
        e_raw = ev['end'].get('dateTime') or ev['end'].get('date')
        
        from datetime import datetime, timedelta
        d_start = datetime.strptime(s_raw[:10], "%Y-%m-%d")
        d_end = datetime.strptime(e_raw[:10], "%Y-%m-%d")
        
        # 1b. Lógica de Grupos: Identificar participantes
        attendees = ev.get('attendees', [])
        correos_grupo = [calendar_id] + [a['email'] for a in attendees if a.get('email')]
        correos_grupo = list(set(correos_grupo)) # Unicos
        
        # Mapear correos a nombres de técnicos para la tabla grupos
        tecs_db = db.obtener_tecnicos()
        map_correo_nombre = {t['correo']: t['nombre'] for t in tecs_db}
        map_correo_init = {t['correo']: t['iniciales'] for t in tecs_db}
        nombres_grupo = [map_correo_nombre.get(c, c) for c in correos_grupo]
        inits_grupo = [map_correo_init.get(c, c) for c in correos_grupo]
        
        # OT y Patrones
        ots_found = list(utils.extraer_ots(titulo))
        ot_principal = ots_found[0] if ots_found else "N/A"
        pats_str = props.get('private', {}).get('app_patrones', '[]')
        try: pats = json.loads(pats_str)
        except: pats = []
        vehiculo = props.get('private', {}).get('app_vehiculo', '')
        
        # Ajustar título con iniciales si hay grupo
        if len(inits_grupo) > 1:
            tag = "/".join(sorted(inits_grupo))
            if tag not in titulo:
                titulo = f"{titulo} - {tag}"

        # 2. Generar eventos individuales
        current = d_start
        while current < d_end:
            target_day = current.strftime("%Y-%m-%d")
            grupo_id = str(uuid.uuid4())
            new_event_ids = []
            
            # Insertar evento para cada integrante del grupo
            for correo in correos_grupo:
                new_ev = {
                    'summary': titulo,
                    'description': desc,
                    'start': {'dateTime': f"{target_day}T07:00:00-03:00", 'timeZone': 'America/Argentina/Buenos_Aires'},
                    'end':   {'dateTime': f"{target_day}T16:00:00-03:00", 'timeZone': 'America/Argentina/Buenos_Aires'},
                    'extendedProperties': props,
                    'attendees': attendees # Preservar invitados originales para que Google sincronice
                }
                res = svc_cal.events().insert(calendarId=correo, body=new_ev).execute()
                new_event_ids.append(res['id'])
            
            # Registrar Grupo en SQLite
            db.crear_o_actualizar_grupo({
                "grupo_id": grupo_id,
                "ot_nro": ot_principal,
                "fecha": target_day,
                "event_ids": new_event_ids,
                "tecnico_nombres": nombres_grupo,
                "patrones": pats,
                "vehiculo": vehiculo
            })
            
            current += timedelta(days=1)
            
        # 3. Eliminar el original
        svc_cal.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        
        db.update_last_sync()
        return {"status": "ok"}
    except Exception as e:
        import traceback; print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/eventos/{event_id}/agregar_tecnico")
async def agregar_tecnico_a_grupo(event_id: str, tecnico_correo: str = Query(...), calendar_id: str = Query(...)):
    """Agrega un técnico a un evento existente, creando/actualizando un grupo."""
    try:
        svc_cal, _ = await run_in_threadpool(extractor.get_google_services)
        
        # 1. Obtener evento base
        ev = svc_cal.events().get(calendarId=calendar_id, eventId=event_id).execute()
        original_title = ev.get('summary', '')
        
        # 2. Mapear técnicos
        tecs = db.obtener_tecnicos()
        map_correo_init = {t['correo']: t['iniciales'] for t in tecs}
        map_correo_nombre = {t['correo']: t['nombre'] for t in tecs}
        
        # 3. Identificar grupo actual o crear uno
        grupo = db.obtener_grupo_de_evento(event_id)
        fecha = (ev['start'].get('dateTime') or ev['start'].get('date'))[:10]
        ots = list(utils.extraer_ots(original_title))
        ot_nro = ots[0] if ots else "N/A"
        
        if not grupo:
            grupo_id = str(uuid.uuid4())
            event_ids = [event_id]
            tecnico_nombres = [map_correo_nombre.get(calendar_id, calendar_id)]
            inits = [map_correo_init.get(calendar_id, '?')]
        else:
            grupo_id = grupo['grupo_id']
            event_ids = grupo['event_ids']
            tecnico_nombres = grupo['tecnico_nombres']
            inits = [map_correo_init.get(c, '?') for c in map_correo_init if map_correo_nombre.get(c) in tecnico_nombres]

        # Agregar el nuevo
        if tecnico_correo not in [t['correo'] for t in tecs if t['nombre'] in tecnico_nombres]:
            new_tec_nombre = map_correo_nombre.get(tecnico_correo)
            new_tec_init = map_correo_init.get(tecnico_correo, '?')
            if new_tec_nombre not in tecnico_nombres:
                tecnico_nombres.append(new_tec_nombre)
                inits.append(new_tec_init)

        # 4. Actualizar Títulos de todos los eventos del grupo
        # Normalizar iniciales (ND/LR/...)
        inits_clean = []
        for n in tecnico_nombres:
            # Buscar iniciales por nombre
            t_data = next((t for t in tecs if t['nombre'] == n), None)
            if t_data: inits_clean.append(t_data['iniciales'])
            else: inits_clean.append('?')

        tag = "/".join(sorted(list(set(inits_clean))))
        # Limpiar cualquier tag previo del título base
        cleaned_title = re.sub(r'\s*-\s*[A-Z]{1,3}(/[A-Z]{1,3})*\s*$', '', original_title).strip()
        new_title = f"{cleaned_title} - {tag}"
        
        print(f"[AgregarTec] Nuevo título generado: {new_title}")
        
        # Duplicar evento para el nuevo técnico
        new_ev_body = ev.copy()
        new_ev_body['summary'] = new_title
        # Limpiar IDs de Google para que sea un insert limpio
        new_ev_body.pop('id', None); new_ev_body.pop('etag', None)
        
        res_new = svc_cal.events().insert(calendarId=tecnico_correo, body=new_ev_body).execute()
        event_ids.append(res_new['id'])
        
        # Actualizar los títulos de los anteriores
        # Necesitamos saber qué ID de evento corresponde a qué técnico para parchar el calendario correcto
        # Re-mapeamos para mayor seguridad
        map_nombre_correo = {t['nombre']: t['correo'] for t in tecs}
        
        # Obtenemos los técnicos actuales del grupo desde la base de datos (antes de insertar el nuevo)
        # O si es nuevo, solo el organizador
        if grupo:
            # Parchar los existentes
            for i, old_id in enumerate(grupo['event_ids']):
                try:
                    tec_name = grupo['tecnico_nombres'][i]
                    cal_target = map_nombre_correo.get(tec_name)
                    if cal_target:
                        svc_cal.events().patch(calendarId=cal_target, eventId=old_id, body={'summary': new_title}).execute()
                except: continue
        else:
            # Si no había grupo, parchar el evento original del organizador
            try:
                svc_cal.events().patch(calendarId=calendar_id, eventId=event_id, body={'summary': new_title}).execute()
            except: pass

        # 5. Guardar en SQLite
        db.crear_o_actualizar_grupo({
            "grupo_id": grupo_id,
            "ot_nro": ot_nro,
            "fecha": fecha,
            "event_ids": list(set(event_ids)),
            "tecnico_nombres": tecnico_nombres,
            "patrones": json.loads(ev.get('extendedProperties',{}).get('private',{}).get('app_patrones','[]')),
            "vehiculo": ev.get('extendedProperties',{}).get('private',{}).get('app_vehiculo','')
        })
        
        db.update_last_sync()
        return {"status": "ok", "new_event_id": res_new['id']}
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
        
        eventos_dia = [e for e in db.obtener_eventos_dict() if e['Inicio'][:10] == fecha]
        ids_en_grupos = []
        for g in grupos_db: ids_en_grupos.extend(g['event_ids'])
        
        # 2. Mapeo de técnicos para iniciales nombre+apellido
        tecs_all = db.obtener_tecnicos()
        def get_inits(nombre):
            # Buscar en DB primero por si tiene iniciales definidas
            t_data = next((t for t in tecs_all if t['nombre'] == nombre), None)
            if t_data and t_data.get('iniciales'): return t_data['iniciales']
            # Fallback a iniciales de Nombre y Apellido
            return "".join([word[0].upper() for word in nombre.split(' ') if word])

        # 3. Agrupamiento por Técnicos involucrados (Grupo de Trabajo)
        # Key: tuple(sorted(nombres_tecnicos))
        agrupados = {}

        def procesar_agrupacion(tecs, pats, veh, ev):
            # Normalizar OTs del evento
            titulo = ev.get('Evento', '')
            ots_list = list(utils.extraer_ots(titulo))
            if not ots_list: return
            
            key = tuple(sorted(tecs))
            if key not in agrupados:
                agrupados[key] = {
                    'tecnicos': set(tecs),
                    'ots': set(),
                    'patrones': set(),
                    'vehiculos': set(),
                    'detalles_ots': [] # Lista de {ot, cliente, servicio}
                }
            
            for ot in ots_list:
                if ot not in agrupados[key]['ots']:
                    agrupados[key]['ots'].add(ot)
                    ot_info = map_ots.get(ot, [])
                    agrupados[key]['detalles_ots'].append({
                        'nro': ot,
                        'cliente': ev.get('Cliente', (ot_info[utils.IDX_CLIE] if len(ot_info) > utils.IDX_CLIE else "---")),
                        'servicio': ev.get('Descripción', (ot_info[utils.IDX_TRAB] if len(ot_info) > utils.IDX_TRAB else "---"))
                    })
            
            for p in (pats or []): agrupados[key]['patrones'].add(p)
            if veh: agrupados[key]['vehiculos'].add(veh)

        # A. Procesar Grupos registrados
        for g in grupos_db:
            info_ev = next((e for e in eventos_dia if e['id'] in g['event_ids']), None)
            if info_ev:
                procesar_agrupacion(g['tecnico_nombres'], g.get('patrones', []), g.get('vehiculo', ''), info_ev)

        # B. Procesar eventos individuales
        for ev in eventos_dia:
            if ev['id'] in ids_en_grupos: continue
            
            props = ev.get('extendedProperties', {})
            if isinstance(props, str):
                try: props = json.loads(props)
                except: props = {}
            priv = props.get('private', {})
            pats = priv.get('app_patrones', '[]')
            if isinstance(pats, str):
                try: pats = json.loads(pats)
                except: pats = []
            
            procesar_agrupacion([ev.get('Técnico', '---')], pats, priv.get('app_vehiculo', ''), ev)

        # 4. Formatear Resultado Final
        resultado = []
        for key, data in agrupados.items():
            # Construir Tag de iniciales ND/LR
            inits = sorted([get_inits(t) for t in data['tecnicos']])
            tag = "/".join(inits)
            
            # Formatear OTs, Clientes y Servicios para impresión
            ots_txt = ", ".join(sorted(list(data['ots'])))
            clientes = " / ".join(list(set([d['cliente'] for d in data['detalles_ots']])))
            servicios = " / ".join(list(set([d['servicio'] for d in data['detalles_ots']])))

            resultado.append({
                "grupo_id": f"group-{'-'.join(inits)}",
                "ot_nro": ots_txt,
                "tag": tag,
                "tecnicos": sorted(list(data['tecnicos'])),
                "patrones": sorted(list(data['patrones'])),
                "vehiculo": ", ".join(data['vehiculos']) if data['vehiculos'] else "N/A",
                "cliente": clientes,
                "direccion": "Ver OTs", 
                "servicio": servicios
            })
                
        return resultado
    except Exception as e:
        import traceback; print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


class RegistrarGrupoParams(BaseModel):
    grupo_id: str
    ot_nro: str
    fecha: str
    event_ids: List[str]
    tecnicos: List[str]
    patrones: Optional[List[str]] = []
    vehiculo: Optional[str] = None

@app.post("/api/grupos/registrar")
async def registrar_grupo(params: RegistrarGrupoParams):
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
    try:
        grupo = db.obtener_grupo_de_evento(event_id)
        if not grupo: return {}
        return grupo
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/eventos/{event_id}/quitar_tecnico")
async def quitar_tecnico(event_id: str, calendar_id: str = Query(...)):
    """Elimina a un técnico de un grupo y actualiza los títulos de los demás."""
    try:
        svc_cal, _ = await run_in_threadpool(extractor.get_google_services)
        
        # 1. Identificar el grupo
        grupo = db.obtener_grupo_de_evento(event_id)
        if not grupo:
            # Si no hay grupo, es un borrado normal
            svc_cal.events().delete(calendarId=calendar_id, eventId=event_id).execute()
            db.eliminar_evento_individual(event_id)
            return {"status": "ok"}

        # 2. Borrar el evento del técnico solicitado
        try:
            svc_cal.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        except: pass # Si ya no existe, seguimos
        
        db.eliminar_evento_individual(event_id)
        
        # 3. Actualizar el registro del grupo en SQLite
        new_event_ids = [eid for eid in grupo['event_ids'] if eid != event_id]
        
        # Buscar el nombre del técnico a remover desde el calendar_id (correo)
        tecs_db = db.obtener_tecnicos()
        t_rem = next((t for t in tecs_db if t['correo'] == calendar_id), None)
        new_tecnico_nombres = grupo['tecnico_nombres']
        if t_rem:
            new_tecnico_nombres = [n for n in grupo['tecnico_nombres'] if n != t_rem['nombre']]

        if not new_event_ids:
            # Grupo vacío, eliminarlo
            db.eliminar_grupo(grupo['grupo_id'])
            db.update_last_sync()
            return {"status": "ok"}

        # 4. Sincronizar Títulos de los que quedan
        inits = []
        for n in new_tecnico_nombres:
            t_data = next((t for t in tecs_db if t['nombre'] == n), None)
            if t_data: inits.append(t_data['iniciales'])

        # Solo si queda más de uno, mantenemos el tag. Si queda uno, lo quitamos.
        tag = "/".join(sorted(inits)) if len(inits) > 1 else ""
        
        # Limpiar tag viejo del título
        # El título actual lo obtenemos de uno de los eventos que quedan
        any_id = new_event_ids[0]
        # Necesitamos el calendar_id de ese técnico
        idx_in_orig = grupo['event_ids'].index(any_id)
        tec_name = grupo['tecnico_nombres'][idx_in_orig]
        if tec_name == (t_rem['nombre'] if t_rem else None): # Just in case index shifted
            idx_in_orig = next(i for i, eid in enumerate(grupo['event_ids']) if eid != event_id)
            tec_name = grupo['tecnico_nombres'][idx_in_orig]
            
        any_cal = next((t['correo'] for t in tecs_db if t['nombre'] == tec_name), None)
        
        if any_cal:
            base_ev = svc_cal.events().get(calendarId=any_cal, eventId=any_id).execute()
            old_title = base_ev.get('summary', '')
            # Regex más flexible: busca " - " seguido de iniciales (letras/números/slashes) al final
            cleaned_title = re.sub(r'\s*-\s*[A-Za-z0-9/]+\s*$', '', old_title).strip()
            new_title = f"{cleaned_title} - {tag}" if tag else cleaned_title
            
            # Parchamos a todos los que quedan
            map_name_mail = {t['nombre']: t['correo'] for t in tecs_db}
            for i, eid in enumerate(grupo['event_ids']):
                if eid == event_id: continue
                try:
                    c_target = map_name_mail.get(grupo['tecnico_nombres'][i])
                    if c_target:
                        svc_cal.events().patch(calendarId=c_target, eventId=eid, body={'summary': new_title}).execute()
                        # Actualizar en SQLite local también
                        db.actualizar_evento_individual(eid, c_target, {"Evento": new_title})
                except: continue

        # 5. Actualizar grupo en SQLite
        if len(new_event_ids) > 1:
            db.crear_o_actualizar_grupo({
                **grupo,
                "event_ids": new_event_ids,
                "tecnico_nombres": new_tecnico_nombres
            })
        else:
            db.eliminar_grupo(grupo['grupo_id']) # Si queda 1, ya no es grupo

        db.update_last_sync()
        return {"status": "ok"}
    except Exception as e:
        import traceback; print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/eventos/{event_id}")
async def eliminar_evento(event_id: str, calendar_id: str = Query(...)):
    # Usar lógica de desasignación para mantener consistencia de grupos
    return await quitar_tecnico(event_id, calendar_id)


# ─────────────────────────────────────────────
# SINCRONIZACIÓN
# ─────────────────────────────────────────────

@app.get("/api/sync")
async def sync_cloud():
    """Sincroniza en un thread separado para no bloquear el event loop."""
    try:
        def _do_sync():
            svc_cal, svc_sheets = extractor.get_google_services()

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
            # timeMin = ahora - 30 días para ver eventos pasados recientes
            time_min = (datetime.datetime.utcnow() - datetime.timedelta(days=30)).isoformat() + 'Z'
            time_max = (datetime.datetime.utcnow() + datetime.timedelta(days=180)).isoformat() + 'Z'

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
                        # Filtrar eventos "fantasma" (Ubicaciones, tiempos de enfoque, etc.)
                        ev_type = item.get('eventType', 'default')
                        if ev_type in ['workingLocation', 'focusTime', 'outOfOffice']:
                            continue
                        
                        item['Técnico'] = t['nombre']
                        item['Evento'] = item.get('summary', 'Sin título')
                        item['Inicio'] = item['start'].get('dateTime', item['start'].get('date'))
                        item['Fin'] = item['end'].get('dateTime', item['end'].get('date'))
                        item['Descripción'] = item.get('description', '')
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
webapp_path = get_resource_path("webapp")
app.mount("/", StaticFiles(directory=webapp_path, html=True), name="webapp")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
