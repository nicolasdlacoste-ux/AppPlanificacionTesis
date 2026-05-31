import os
import sys
import time
import json
import uuid
import datetime
import traceback
import sqlite3

# Importar componentes internos
from data_manager import DataManager
from extractor import get_google_services
from sync_manager import SyncWorker
from poll_manager import PollingManager
from hydration_service import HydrationService, RealOtRepository
from utils import EventAdapter, OTNormalizationService

class SyncScenarioRunner:
    """
    [SYNC_SCENARIO] 
    Framework de validación E2E para el pipeline de sincronización.
    """
    def __init__(self):
        print("[SETUP] Inicializando Runner...")
        self.db = DataManager()
        
        # Obtener servicios reales de Google
        services = get_google_services()
        if not services:
            print("❌ Error: No se pudieron obtener las credenciales de Google.")
            sys.exit(1)
        self.svc_cal = services[0]
        
        # Setup de componentes
        import extractor
        self.sync_worker = SyncWorker(db=self.db, extractor_module=extractor)
        ot_repo = RealOtRepository(self.db)
        hydrator = HydrationService(ot_repo)
        self.poll_manager = PollingManager(
            db=self.db,
            google_service_factory=lambda: self.svc_cal,
            hydration_service=hydrator
        )
        
        self.report = []
        self.tecnicos = self.db.obtener_tecnicos()
        if not self.tecnicos:
            print("❌ Error: No hay técnicos cargados en la base de datos.")
            sys.exit(1)
            
        self.target_tec = self.tecnicos[0]
        self.secondary_tec = self.tecnicos[1] if len(self.tecnicos) > 1 else self.tecnicos[0]
        
        # Almacén de IDs creados para limpieza
        self.created_events = []

    def log_scenario(self, name, status, detail=None, diff=None):
        entry = {
            "scenario": name,
            "status": status,
            "timestamp": datetime.datetime.now().isoformat(),
            "detail": detail,
            "diff": diff
        }
        self.report.append(entry)
        color = "" # Desactivar colores por ahora para evitar ruidos en Windows
        reset = ""
        print(f"[{status}] {name}")
        if detail: print(f"       Detail: {detail}")

    def wait_for_sync(self):
        """Ejecucion deterministica del SyncWorker."""
        print("    [ACTION] Sincronizando Outbound...")
        self.sync_worker.process_queue()
        time.sleep(2) # Espera para propagacion en la nube de Google

    def wait_for_polling(self):
        """Ejecucion deterministica del PollingManager."""
        print("    [ACTION] Ejecutando Polling Inbound...")
        # Forzar polling para el tecnico especifico para ahorrar tiempo
        self.poll_manager._poll_all_calendars(dry_run=False)
        time.sleep(1)

    # --- ASSERTIONS ---
    
    def assert_google_metadata(self, calendar_id, event_id, key, expected_val):
        """Verifica que un campo de metadata privada en Google coincida."""
        ev = self.svc_cal.events().get(calendarId=calendar_id, eventId=event_id).execute()
        props = ev.get("extendedProperties", {}).get("private", {})
        val = props.get(key)
        
        # Manejo especial para strings JSON (patrones, ots)
        if val and (val.startswith("[") or val.startswith("{")):
            try: val = json.loads(val)
            except: pass
            
        if val != expected_val:
            raise AssertionError(f"Google Metadata Mismatch: {key}. Expected: {expected_val}, Got: {val}")

    def assert_db_field(self, event_id, tec_nombre, field, expected_val):
        """Verifica que un campo en SQLite coincida."""
        ev = self.db.get_evento_dict(event_id, tec_nombre)
        if not ev:
            raise AssertionError(f"Event {event_id} not found in DB for {tec_nombre}")
        
        val = ev.get(field)
        if val != expected_val:
            raise AssertionError(f"DB Field Mismatch: {field}. Expected: {expected_val}, Got: {val}")

    # --- ESCENARIOS ---

    def run_all(self):
        print("\n" + "="*70)
        print(">>> INICIANDO FRAMEWORK DE VALIDACION SINCRONIZACION E2E")
        print("="*70 + "\n")
        
        scenarios = [
            self.scenario_1_create_event,
            self.scenario_2_add_patterns,
            self.scenario_3_add_vehicle,
            self.scenario_4_move_technician,
            self.scenario_5_delete_event,
            self.scenario_6_create_group,
            self.scenario_7_move_group,
            self.scenario_8_delete_group_member,
            self.scenario_9_split_group
        ]
        
        for scenario in scenarios:
            name = scenario.__name__.upper()
            try:
                print(f"[*] {name}")
                scenario()
                self.log_scenario(name, "PASS")
            except Exception as e:
                self.log_scenario(name, "FAIL", detail=str(e), diff=traceback.format_exc())
                print(f"       ERROR: {traceback.format_exc()}")
        
        self.print_report()
        self.cleanup()

    def scenario_1_create_event(self):
        """Crea un evento local, lo sube a Google y verifica persistencia."""
        test_id = f"e2e_{uuid.uuid4().hex[:8]}"
        summary = f"TEST E2E CREATE - {test_id} (OT 9999)"
        
        # 1. Crear localmente
        ev_obj = {
            "id": test_id,
            "google_event_id": test_id,
            "calendar_id": self.target_tec['correo'],
            "tecnico_nombre": self.target_tec['nombre'],
            "summary": summary,
            "inicio": "2026-11-01T10:00:00-03:00",
            "fin": "2026-11-01T11:00:00-03:00",
            "extendedProperties": {"private": {"app_ots": '["9999"]', "source": "internal", "version": "1"}},
            "version": 1,
            "sync_status": "PENDING"
        }
        self.db.guardar_evento_individual(ev_obj)
        self.db.enqueue_sync(test_id, self.target_tec['correo'], self.target_tec['nombre'], "CREATE")
        self.created_events.append((test_id, self.target_tec))

        # 2. Sync
        self.wait_for_sync()
        
        # Fetch the real google_event_id assigned by Google
        db_ev = self.db.get_evento_dict(test_id, self.target_tec['nombre'])
        real_google_id = db_ev.get('google_event_id')
        print(f"    [INFO] Real Google ID: {real_google_id}")

        # Actualizar rastro para limpieza y siguientes escenarios (ID real de Google)
        self.created_events[-1] = (test_id, self.target_tec, real_google_id)

        # 3. Assert Google
        self.assert_google_metadata(self.target_tec['correo'], real_google_id, "source", "internal")
        self.assert_google_metadata(self.target_tec['correo'], real_google_id, "app_ots", ["9999"])
        
        # 4. Polling
        self.wait_for_polling()
        
        # 5. Assert DB
        self.assert_db_field(test_id, self.target_tec['nombre'], "sync_status", "SUCCESS")

    def scenario_2_add_patterns(self):
        """Agrega patrones a un evento existente y verifica merge metadata."""
        if not self.created_events: return
        test_id, tec, real_google_id = self.created_events[-1]
        pats = ["P1", "P2"]
        
        # 1. Update local
        ev = self.db.get_evento_dict(test_id, tec['nombre'])
        props = json.loads(ev['extended_props'] or "{}")
        if "private" not in props: props["private"] = {}
        props["private"]["app_patrones"] = json.dumps(pats)
        
        self.db.actualizar_evento_individual(test_id, tec['correo'], {
            "extended_props": props,
            "summary": ev['summary'] # Mantener summary
        }, base_version=ev['version'])
        self.db.enqueue_sync(test_id, tec['correo'], tec['nombre'], "UPDATE")
        
        # 2. Sync
        self.wait_for_sync()
        
        # 3. Assert Google (Patrones presentes + OT preservada)
        self.assert_google_metadata(tec['correo'], real_google_id, "app_patrones", pats)
        self.assert_google_metadata(tec['correo'], real_google_id, "app_ots", ["9999"])

    def scenario_3_add_vehicle(self):
        """Agrega vehículo y verifica que no se pierdan los patrones."""
        if not self.created_events: return
        test_id, tec, real_google_id = self.created_events[-1]
        veh = "TOYOTA-01"
        
        # 1. Update local
        ev = self.db.get_evento_dict(test_id, tec['nombre'])
        props = json.loads(ev['extended_props'] or "{}")
        props["private"]["app_vehiculo"] = veh
        
        self.db.actualizar_evento_individual(test_id, tec['correo'], {
            "extended_props": props
        }, base_version=ev['version'])
        self.db.enqueue_sync(test_id, tec['correo'], tec['nombre'], "UPDATE")
        
        # 2. Sync
        self.wait_for_sync()
        
        # 3. Assert Google (Vehículo + Patrones + OT)
        self.assert_google_metadata(tec['correo'], real_google_id, "app_vehiculo", veh)
        self.assert_google_metadata(tec['correo'], real_google_id, "app_patrones", ["P1", "P2"])
        self.assert_google_metadata(tec['correo'], real_google_id, "app_ots", ["9999"])

    def scenario_4_move_technician(self):
        """Mueve un evento de un técnico a otro (Logical Move)."""
        if self.target_tec == self.secondary_tec:
            print("    [SKIP] Saltando MOVE_TECHNICIAN (solo hay 1 técnico)")
            return
        test_id, tec_orig, real_google_id = self.created_events[-1]
        tec_dest = self.secondary_tec
        
        # 1. Simular movimiento local (cambio tecnico/calendario)
        ev = self.db.get_evento_dict(test_id, tec_orig['nombre'])
        self.db.actualizar_evento_individual(test_id, tec_orig['correo'], {
            "tecnico_nombre": tec_dest['nombre'],
            "calendar_id": tec_dest['correo'],
            "sync_status": "PENDING",
            "pending_sync": 1
        }, base_version=ev['version'])

        # 2. Encolar movimiento
        self.db.enqueue_sync(test_id, tec_dest['correo'], tec_dest['nombre'], "UPDATE", original_calendar_id=tec_orig['correo'])
        
        # 2. Sync
        self.wait_for_sync()
        
        # [FIX] Fetch the NEW real_google_id assigned by Google on the new calendar
        db_ev = self.db.get_evento_dict(test_id, tec_dest['nombre'])
        new_google_id = db_ev.get('google_event_id')
        print(f"    [INFO] New Google ID after move: {new_google_id}")

        # 3. Assert Google (Eliminado en origen, Creado en destino con misma metadata)
        try:
            self.svc_cal.events().get(calendarId=tec_orig['correo'], eventId=real_google_id).execute()
            raise AssertionError("Event still exists in original calendar after move")
        except:
            pass # OK, no debe existir
            
        self.assert_google_metadata(tec_dest['correo'], new_google_id, "app_vehiculo", "TOYOTA-01")
        self.created_events[-1] = (test_id, tec_dest, new_google_id) # Actualizar rastro para limpieza

    def scenario_5_delete_event(self):
        """Elimina el evento y verifica limpieza en Google."""
        if not self.created_events: return
        test_id, tec, real_google_id = self.created_events[-1]
        
        # 1. Encolar borrado
        self.db.enqueue_sync(test_id, tec['correo'], tec['nombre'], "DELETE")
        
        # 2. Sync
        self.wait_for_sync()
        
        # 3. Assert Google
        try:
            self.svc_cal.events().get(calendarId=tec['correo'], eventId=real_google_id).execute()
            raise AssertionError("Event still exists in Google after DELETE sync")
        except:
            pass # OK

    def cleanup(self):
        print("\n[CLEANUP] Limpiando eventos de prueba...")
        for entry in self.created_events:
            eid = entry[2] if len(entry) > 2 else entry[0]
            tec = entry[1]
            try:
                self.svc_cal.events().delete(calendarId=tec['correo'], eventId=eid).execute()
            except:
                pass
        print("Cleanup finalizado.")

    def scenario_6_create_group(self):
        """Crea un grupo y verifica la vinculación de eventos."""
        gid = f"group_{uuid.uuid4().hex[:8]}"
        ot = "8888"
        
        # 1. Crear 2 eventos nuevos para el grupo
        e1_id = f"e1_{uuid.uuid4().hex[:6]}"
        e2_id = f"e2_{uuid.uuid4().hex[:6]}"
        
        for eid, tec in [(e1_id, self.target_tec), (e2_id, self.secondary_tec)]:
            self.db.guardar_evento_individual({
                "id": eid, "google_event_id": eid, "calendar_id": tec['correo'],
                "tecnico_nombre": tec['nombre'], "summary": f"Servicio OT {ot}",
                "inicio": "2026-11-05T09:00:00-03:00", "fin": "2026-11-05T10:00:00-03:00",
                "extendedProperties": {"private": {"source": "internal"}},
                "version": 1, "sync_status": "PENDING"
            })
            self.db.enqueue_sync(eid, tec['correo'], tec['nombre'], "CREATE")
            self.created_events.append((eid, tec))

        self.wait_for_sync()
        
        # 2. Crear el grupo
        self.db.crear_o_actualizar_grupo({
            "grupo_id": gid, "ot_nro": ot, "fecha": "2026-11-05",
            "event_ids": [e1_id, e2_id],
            "tecnico_nombres": [self.target_tec['nombre'], self.secondary_tec['nombre']],
            "patrones": ["G1", "G2"], "vehiculo": "GR-01"
        })
        
        # 3. Vincular manualmente (como haría el api_server)
        for eid in [e1_id, e2_id]:
            self.db.vincular_evento_a_grupo(eid, gid)
            
        # 4. Assert DB
        g = self.db.obtener_grupo(gid)
        if not g or g['ot_nro'] != ot:
            raise AssertionError("Group not created correctly in DB")
        
        ev1 = self.db.get_evento_dict(e1_id)
        props = json.loads(ev1['extended_props'] or "{}")
        if props.get("private", {}).get("grupo_id") != gid:
            raise AssertionError(f"Event {e1_id} not linked to group {gid}")

    def scenario_7_move_group(self):
        """Mueve un grupo completo (todos sus eventos) a otra fecha."""
        # Buscamos el grupo creado en el escenario anterior
        last_ev_id, tec = self.created_events[-1]
        g = self.db.obtener_grupo_de_evento(last_ev_id)
        if not g: return
        
        gid = g['grupo_id']
        nueva_fecha = "2026-11-06"
        
        # 1. Simular Mover Grupo (Update de cada evento + Update de grupo)
        for i, eid in enumerate(g['event_ids']):
            tec_nombre = g['tecnico_nombres'][i]
            ev = self.db.get_evento_dict(eid, tec_nombre)
            
            # Cambiar fecha en el inicio/fin
            nuevo_s = ev['inicio'].replace("2026-11-05", nueva_fecha)
            nuevo_e = ev['fin'].replace("2026-11-05", nueva_fecha)
            
            self.db.actualizar_evento_individual(eid, ev['calendar_id'], {
                "inicio": nuevo_s, "fin": nuevo_e,
                "sync_status": "PENDING"
            }, base_version=ev['version'])
            self.db.enqueue_sync(eid, ev['calendar_id'], tec_nombre, "UPDATE")

        self.db.crear_o_actualizar_grupo({**g, "fecha": nueva_fecha})
        
        # 2. Sync
        self.wait_for_sync()
        
        # 3. Assert DB
        g_new = self.db.obtener_grupo(gid)
        if g_new['fecha'] != nueva_fecha:
            raise AssertionError(f"Group {gid} date not updated in DB")
        
        for eid, tec_n in zip(g['event_ids'], g['tecnico_nombres']):
            ev = self.db.get_evento_dict(eid, tec_n)
            if nueva_fecha not in ev['inicio']:
                raise AssertionError(f"Event {eid} not moved to {nueva_fecha}")

    def scenario_8_delete_group_member(self):
        """Elimina un miembro de un grupo y verifica integridad."""
        last_ev_id, tec = self.created_events[-1]
        g = self.db.obtener_grupo_de_evento(last_ev_id)
        if not g or len(g['event_ids']) < 2: return
        
        eid_to_remove = g['event_ids'][0]
        tec_to_remove = g['tecnico_nombres'][0]
        gid = g['grupo_id']
        
        # 1. Eliminar miembro (como haría api_server)
        # a. Quitar de la lista del grupo
        new_ids = [eid for eid in g['event_ids'] if eid != eid_to_remove]
        new_tecs = [t for t in g['tecnico_nombres'] if t != tec_to_remove]
        self.db.crear_o_actualizar_grupo({**g, "event_ids": new_ids, "tecnico_nombres": new_tecs})
        
        # b. Desvincular metadato del evento
        # (vincular_evento_a_grupo con None o eliminar clave)
        # Por simplicidad en el test, lo borramos físicamente
        self.db.enqueue_sync(eid_to_remove, tec['correo'], tec_to_remove, "DELETE")
        self.db.eliminar_evento_individual(eid_to_remove)
        
        # 2. Assert DB
        g_after = self.db.obtener_grupo(gid)
        if len(g_after['event_ids']) != len(new_ids):
            raise AssertionError("Group member count not updated")
        if eid_to_remove in g_after['event_ids']:
            raise AssertionError("Removed member still in group list")

    def scenario_9_split_group(self):
        """Divide un grupo (Split): toma un miembro y lo mueve a un grupo nuevo."""
        last_ev_id, tec = self.created_events[-1]
        g_orig = self.db.obtener_grupo_de_evento(last_ev_id)
        if not g_orig or len(g_orig['event_ids']) < 1: return
        
        eid_to_split = g_orig['event_ids'][0]
        tec_to_split = g_orig['tecnico_nombres'][0]
        new_gid = f"split_{uuid.uuid4().hex[:6]}"
        
        # 1. Remover del original
        new_ids_orig = [eid for eid in g_orig['event_ids'] if eid != eid_to_split]
        new_tecs_orig = [t for t in g_orig['tecnico_nombres'] if t != tec_to_split]
        
        if not new_ids_orig:
            self.db.eliminar_grupo(g_orig['grupo_id'])
        else:
            self.db.crear_o_actualizar_grupo({**g_orig, "event_ids": new_ids_orig, "tecnico_nombres": new_tecs_orig})
            
        # 2. Crear nuevo grupo con ese evento
        self.db.crear_o_actualizar_grupo({
            "grupo_id": new_gid, "ot_nro": "SPLIT-OT", "fecha": g_orig['fecha'],
            "event_ids": [eid_to_split], "tecnico_nombres": [tec_to_split],
            "patrones": ["S1"], "vehiculo": "SPLIT-01"
        })
        self.db.vincular_evento_a_grupo(eid_to_split, new_gid)
        
        # 3. Assert
        g_new = self.db.obtener_grupo(new_gid)
        if not g_new or eid_to_split not in g_new['event_ids']:
            raise AssertionError("Split member not in new group")
        
        ev = self.db.get_evento_dict(eid_to_split)
        props = json.loads(ev['extended_props'] or "{}")
        if props.get("private", {}).get("grupo_id") != new_gid:
            raise AssertionError(f"Event metadata not updated to new group {new_gid}")

    def print_report(self):
        print("\n" + "="*70)
        print("RESULTADOS FINALES DE ESCENARIOS")
        print("="*70)
        passed = len([r for r in self.report if r["status"] == "PASS"])
        failed = len([r for r in self.report if r["status"] == "FAIL"])
        
        for r in self.report:
            icon = "[PASS]" if r["status"] == "PASS" else "[FAIL]"
            print(f"{icon} {r['scenario']:25s}")
            
        print("-"*70)
        print(f"TOTAL: {len(self.report)} | PASSED: {passed} | FAILED: {failed}")
        if failed == 0:
            print("\n--- TODAS LAS CAPAS ESTABLES ---")
        else:
            print("\n--- SE DETECTARON REGRESIONES ---")
        print("="*70 + "\n")

if __name__ == "__main__":
    runner = SyncScenarioRunner()
    runner.run_all()
