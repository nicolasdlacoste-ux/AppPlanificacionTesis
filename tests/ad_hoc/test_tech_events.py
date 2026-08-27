import datetime
import json
import sqlite3

conn = sqlite3.connect('planificacion.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()
c.execute("SELECT * FROM eventos")
eventos = [dict(r) for r in c.fetchall()]

tech_events = {}
for ev in eventos:
    tech = str(ev.get("tecnico_nombre", "")).strip()
    if 'Nicol' not in tech: continue
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
                    
                    if is_weekend: h = 0.0
                    elif i == 0: h = max(0.0, 16.0 - max(7.0, start_dt.hour + start_dt.minute / 60))
                    elif i == dias: h = max(0.0, min(16.0, end_dt.hour + end_dt.minute / 60) - 7.0)
                    else: h = 9.0
                    
                tech_events[tech].setdefault(dk, []).append({
                    "sort": sort_val, "sort_end": sort_end_val, "text": desc,
                    "horas": h, "es_ot": es_ot,
                    "original_text": summary,
                    "extendedProperties": props,
                    "id": ev.get("id"), "calendar_id": ev.get("calendar_id"),
                    "Inicio": ev.get("inicio"), "Fin": ev.get("fin"),
                    "description": ev.get("descripcion", "")
                })
    except Exception as e:
        pass

for k, v in tech_events.items():
    print(f"--- {k} ---")
    for dk, evs in sorted(v.items()):
        if dk >= '2026-08-26':
            print(f"{dk}: {[(e['original_text'], e['es_ot']) for e in evs]}")

