import json
import math
import datetime
import itertools
import utils

def obtener_slots_ocupados(tech_events, nombre, date_key, ignorar_no_ots=False):
    """Retorna (set_ocupados, lista_conflictos)."""
    n_norm = str(nombre).strip()
    evs = tech_events.get(n_norm, {}).get(date_key, [])
    ocupados = set()
    conflictos = []
    
    for ev in evs:
        s_val = ev.get("sort", 0); e_val = ev.get("sort_end", 2400)
        s_h = s_val // 100 + (s_val % 100) / 60.0
        e_h = e_val // 100 + (e_val % 100) / 60.0
        
        es_ot = ev.get("es_ot", False)
        marcar_ocupado = True
        if ignorar_no_ots and not es_ot:
            marcar_ocupado = False

        for i in range(11): 
            h_i = 7.0 + i
            h_next = h_i + 1.0
            if s_h < h_next and e_h > h_i:
                if marcar_ocupado:
                    ocupados.add(i)
                else:
                    conflictos.append(f"{ev.get('original_text', ev.get('text'))}")
    
    return ocupados, list(set(conflictos))

def buscar_bloque_libre(tech_events, nombres, date_key, horas_req, ignorar_no_ots=False, patrones_requeridos=None, ots_objetivo=None):
    """Busca el primer slot disponible y detecta conflictos de patrones inteligentes."""
    slots_ocupados_total = set()
    conflictos_totales = []
    conflictos_patrones = []
    
    # Normalizar OTs objetivo
    ots_obj_set = utils.extraer_ots(ots_objetivo) if ots_objetivo else set()
    
    for nm in nombres:
        ocu, conf = obtener_slots_ocupados(tech_events, nm, date_key, ignorar_no_ots)
        slots_ocupados_total.update(ocu)
        conflictos_totales.extend(conf)
        
    # Detección de conflictos de patrones (Nivel Global)
    if patrones_requeridos:
        for p in patrones_requeridos:
            # { normal_name: set_ots } de quien está usando el patrón p en este día
            quien_usa_p = {}
            for t_name, dias_eventos in tech_events.items():
                evs_global = dias_eventos.get(date_key, [])
                p_en_uso = False
                ots_tec = set()
                for ev in evs_global:
                    props = ev.get('extendedProperties', {}).get('private', {})
                    p_asig = []
                    try: p_asig = json.loads(props.get('app_patrones', '[]'))
                    except: pass
                    
                    if p in p_asig: p_en_uso = True
                    ots_tec.update(utils.extraer_ots(props.get('app_ots', ev.get('text', ''))))
                
                if p_en_uso:
                    quien_usa_p[utils.normalizar_texto(t_name)] = ots_tec
            
            if quien_usa_p:
                # Agregamos virtualmente a los técnicos que estamos buscando para ver si "caben" sin conflicto
                for nm in nombres:
                    quien_usa_p[utils.normalizar_texto(nm)] = ots_obj_set
                
                hay_conf, _ = utils.evaluar_conflicto(quien_usa_p)
                if hay_conf:
                    # Reportar quién lo usa y dónde para el primer técnico conflictivo encontrado
                    for t_orig, t_ots in quien_usa_p.items():
                        # Si no es de los que estamos intentando agendar, es el que causa el conflicto externo
                        if t_orig not in [utils.normalizar_texto(n) for n in nombres]:
                            conflictos_patrones.append({
                                "patron": p,
                                "tecnico": t_orig,
                                "donde": ", ".join(t_ots) if t_ots else "Otro proyecto"
                            })
    
    n_slots_nec = math.ceil(horas_req)
    for start_slot in range(11 - n_slots_nec + 1):
        bloque = range(start_slot, start_slot + n_slots_nec)
        if all(s not in slots_ocupados_total for s in bloque):
            # Solo si el bloque está libre, reportamos los conflictos de patrones
            # (Si el bloque está ocupado, el conflicto de tiempo es primario)
            return 7.0 + start_slot, list(set(conflictos_totales)), conflictos_patrones
            
    return None, [], []

def son_consecutivos(fechas, viaje):
    for i in range(len(fechas) - 1):
        d1, d2 = fechas[i], fechas[i+1]
        diff = (d2 - d1).days
        if viaje:
            if diff != 1: return False
        else:
            ok = (diff == 1) or (d1.weekday() == 4 and d2.weekday() == 0 and diff == 3)
            if not ok: return False
    return True

def buscar_disponibilidad(tech_events, tecnicos_info, n_tec, dias_nec, consecutivo, viaje, f_inicio, ventana, 
                           ignorar_no_ots=False, n_resultados=3, patrones_requeridos=None, excluir_conflictos_pats=False, ots_objetivo=None):
    """Lógica centralizada de búsqueda de disponibilidad con detección de patrones y filtro."""
    f_fin = f_inicio + datetime.timedelta(days=ventana)
    workdays = [f_inicio + datetime.timedelta(days=i) for i in range((f_fin - f_inicio).days + 1) 
                if (f_inicio + datetime.timedelta(days=i)).weekday() < 5]

    n_full = int(dias_nec)
    h_resto = (dias_nec - n_full) * 9.0
    n_total_dias = math.ceil(dias_nec)

    candidatos = []
    for combo in itertools.combinations(tecnicos_info, n_tec):
        nombres = [t["nombre"] for t in combo]
        dias_validos = []
        for wd in workdays:
            dk = wd.strftime("%Y-%m-%d")
            # 9 horas
            h_start_9, conf9, conf_p9 = buscar_bloque_libre(tech_events, nombres, dk, 9.0, ignorar_no_ots, patrones_requeridos, ots_objetivo)
            # Fracción
            h_req_resto = h_resto if h_resto > 0 else 9.0
            h_start_r, confr, conf_pr = buscar_bloque_libre(tech_events, nombres, dk, h_req_resto, ignorar_no_ots, patrones_requeridos, ots_objetivo)
            
            # Aplicar exclusión de conflictos si está solicitada
            if excluir_conflictos_pats:
                if h_start_9 is not None and conf_p9: h_start_9 = None
                if h_start_r is not None and conf_pr: h_start_r = None

            if h_start_9 is not None:
                dias_validos.append({"date": wd, "h_start": h_start_9, "full": True, "conf": conf9, "conf_patrones": conf_p9})
            elif h_start_r is not None:
                dias_validos.append({"date": wd, "h_start": h_start_r, "full": False, "conf": confr, "conf_patrones": conf_pr})

        if len(dias_validos) < n_total_dias: continue

        for i in range(len(dias_validos) - n_total_dias + 1):
            ventana_dias = dias_validos[i : i + n_total_dias]
            fechas_puras = [dv["date"] for dv in ventana_dias]
            
            if consecutivo and not son_consecutivos(fechas_puras, viaje): continue
            
            full_count = sum(1 for dv in ventana_dias if dv["full"])
            if full_count < n_full: continue
            
            opcion_fechas = []
            nombres_combo = [t["nombre"] for t in combo]
            for idx, dv in enumerate(ventana_dias):
                h_dur = 9.0 if (idx < n_full) else h_resto
                if h_dur == 0: h_dur = 9.0
                opcion_fechas.append({
                    "date": dv["date"],
                    "h_start": dv["h_start"],
                    "h_dur": h_dur,
                    "conf": dv.get("conf", []),
                    "conf_patrones": dv.get("conf_patrones", []),
                    "tecnicos": nombres_combo
                })
            
            candidatos.append({
                "tecnicos": combo,
                "fechas": opcion_fechas,
                "f0": fechas_puras[0]
            })

    candidatos.sort(key=lambda x: x["f0"])
    resultado, vistos = [], set()
    for c in candidatos:
        if len(resultado) >= n_resultados: break
        key = (c["f0"], frozenset(t["nombre"] for t in c["tecnicos"]))
        if key not in vistos:
            vistos.add(key); resultado.append(c)
    return resultado
