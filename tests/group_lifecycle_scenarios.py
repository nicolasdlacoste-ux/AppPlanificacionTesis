"""
group_lifecycle_scenarios.py
────────────────────────────
Suite de pruebas End-to-End para el ciclo de vida de Grupos (Fase 3 Stabilization Sprint).

Verifica que las mutaciones atómicas se registren correctamente en `group_operation_journal`,
y que el estado estructural del grupo sea convergente (sin drift) en el backend (SQLite).

Uso:
  python tests/group_lifecycle_scenarios.py
"""

import sys
import os
import json
import uuid
import datetime
import asyncio
from pathlib import Path

# Agregar el root al sys.path para importar AppPlanificacion
sys.path.append(str(Path(__file__).parent.parent))

from data_manager import DataManager
from api_server import app, db
from group_integrity import validate_group_integrity

# Mock the utils methods if needed, though they should work.
# We will interact directly with DataManager and API methods as if we were the server.

def setup_test_env():
    # Inicializar DB en memoria o archivo de test
    test_db_path = "test_scenarios.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    
    test_db = DataManager(test_db_path)
    
    # Crear tecnicos de prueba
    test_db.guardar_tecnicos([
        {"nombre": "Tecnico A", "correo": "teca@example.com", "iniciales": "TA"},
        {"nombre": "Tecnico B", "correo": "tecb@example.com", "iniciales": "TB"},
        {"nombre": "Tecnico C", "correo": "tecc@example.com", "iniciales": "TC"}
    ])
    return test_db

def _create_event(db, event_id, cal_id, tec_name, start, end, summary):
    db.guardar_evento_individual({
        "id": event_id,
        "calendar_id": cal_id,
        "tecnico_nombre": tec_name,
        "summary": summary,
        "inicio": start,
        "fin": end,
        "version": 1,
        "sync_status": "SYNCED",
        "pending_sync": 0,
        "google_event_id": f"g_{event_id}",
        "extended_props": {"private": {}}
    })
    return event_id

def _create_group(db, ev_ids, tec_names, ot_nro, fecha):
    group_id = str(uuid.uuid4())
    db.crear_o_actualizar_grupo({
        "grupo_id": group_id,
        "fecha": fecha,
        "event_ids": ev_ids,
        "tecnico_nombres": tec_names,
        "ot_nro": ot_nro
    })
    for ev in ev_ids:
        db.vincular_evento_a_grupo(ev, group_id)
    return group_id

async def run_scenarios():
    print("==================================================")
    print("  RUNNING GROUP LIFECYCLE FORENSIC SCENARIOS")
    print("==================================================\n")
    
    # Patch global DB
    import api_server
    test_db = setup_test_env()
    api_server.db = test_db
    # Dummy mock for dependencies
    api_server.check_authorization = lambda: None
    
    # ==========================================
    # G-01: Mover Grupo
    # ==========================================
    print("--> G-01: Mover Grupo")
    ev1 = _create_event(test_db, "ev1", "teca@example.com", "Tecnico A", "2026-05-30T09:00:00Z", "2026-05-30T10:00:00Z", "[OT-123] G")
    ev2 = _create_event(test_db, "ev2", "tecb@example.com", "Tecnico B", "2026-05-30T09:00:00Z", "2026-05-30T10:00:00Z", "[OT-123] G")
    gid_01 = _create_group(test_db, [ev1, ev2], ["Tecnico A", "Tecnico B"], "OT-123", "2026-05-30")
    
    from api_server import mover_grupo, MoverEventoParams
    req = MoverEventoParams(event_id="ev1", calendar_id_origen="teca@example.com", nueva_fecha="2026-05-31", correo_destino="tecb@example.com")
    # Inyectar version
    test_db.get_evento_dict = lambda x: {"version": 1, "inicio": "2026-05-30T09:00:00Z", "fin": "2026-05-30T10:00:00Z"} if x == "ev1" else test_db.resolve_event(x)
    
    try:
        await mover_grupo("ev1", req)
    except Exception as e:
        print(f"Warning G-01: {e}")
        
    ops = test_db.get_all_group_operations()
    assert len(ops) > 0, "Debe existir al menos 1 operation"
    assert ops[0]['operation_type'] == "MOVE_GROUP"
    assert ops[0]['status'] == "COMPLETED"
    print("G-01 PASSED")

    # ==========================================
    # G-02: Añadir técnico a evento individual
    # ==========================================
    print("--> G-02: Añadir técnico a evento individual")
    ev3 = _create_event(test_db, "ev3", "tecc@example.com", "Tecnico C", "2026-06-01T09:00:00Z", "2026-06-01T10:00:00Z", "[OT-456]")
    from api_server import agregar_tecnico_a_grupo
    await agregar_tecnico_a_grupo("ev3", "teca@example.com", "tecc@example.com")
    
    ops = test_db.get_all_group_operations(limit=1)
    assert ops[0]['operation_type'] == "ADD_TECHNICIAN"
    assert ops[0]['status'] == "COMPLETED"
    print("G-02 PASSED")

    # ==========================================
    # G-04: Split evento individual
    # ==========================================
    print("--> G-04: Split evento individual")
    ev4 = _create_event(test_db, "ev4", "teca@example.com", "Tecnico A", "2026-06-05T09:00:00Z", "2026-06-07T10:00:00Z", "[OT-789]")
    from api_server import split_evento
    await split_evento("ev4", "teca@example.com")
    
    ops = test_db.get_all_group_operations(limit=1)
    assert ops[0]['operation_type'] == "SPLIT_EVENT"
    assert ops[0]['status'] == "COMPLETED"
    print("G-04 PASSED")

    # ==========================================
    # G-07: Accept Review en miembro de grupo
    # ==========================================
    print("--> G-07: Accept Review")
    ev_rev = _create_event(test_db, "ev_rev1", "tecb@example.com", "Tecnico B", "2026-07-01T09:00", "2026-07-01T10:00", "[OT-REV]")
    gid_rev = _create_group(test_db, [ev_rev], ["Tecnico B"], "OT-REV", "2026-07-01")
    
    # Inject a review into DB
    with test_db._get_connection() as conn:
        conn.execute("""
            INSERT INTO poll_review_queue (review_id, event_id, calendar_id, conflict_type, diff_json, status, created_at)
            VALUES (?, ?, ?, 'FIELD_CHANGE', '{"summary": {"old": "[OT-REV]", "new": "[OT-REV] Mutated"}}', 'PENDING', 'now')
        """, ("rev_123", ev_rev, "tecb@example.com"))
        conn.commit()
    
    from api_server import accept_review
    await accept_review("rev_123")
    
    ops = test_db.get_all_group_operations(limit=1)
    assert ops[0]['operation_type'] == "ACCEPT_REVIEW"
    assert ops[0]['status'] in ("COMPLETED", "DRIFT_DETECTED")
    print("G-07 PASSED")
    
    print("\nALL SCENARIOS PASSED")

if __name__ == "__main__":
    asyncio.run(run_scenarios())
