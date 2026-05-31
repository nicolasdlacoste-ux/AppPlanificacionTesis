from data_manager import DataManager

db = DataManager()
eventos = db.obtener_eventos_dict()
if len(eventos) > 0:
    print(f"Loaded {len(eventos)} events.")
    ev = eventos[-1]
    d_s, h_s = db._parse_time(ev["Inicio"])
    d_e, h_e = db._parse_time(ev["Fin"])
    print(f"Test Event: {ev['Evento']} ({ev['Técnico']}) on {d_s} from {h_s} to {h_e}")
    
    # Try creating a conflict with same technician
    conflict = db.check_conflictos_negocio(
        tecnico=ev['Técnico'],
        vehiculo=None,
        patrones=None,
        fecha=d_s,
        h_start=h_s,
        h_end=h_e,
        ignore_event_ids=[]
    )
    print(f"Technician Conflict Test: {conflict}")
    
    # If ignoring its own ID, it shouldn't conflict
    conflict_ignore = db.check_conflictos_negocio(
        tecnico=ev['Técnico'],
        vehiculo=None,
        patrones=None,
        fecha=d_s,
        h_start=h_s,
        h_end=h_e,
        ignore_event_ids=[ev["id"]]
    )
    print(f"Technician Conflict Ignore Test (should be None): {conflict_ignore}")
else:
    print("No events in DB to test against.")
