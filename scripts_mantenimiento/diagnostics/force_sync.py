import data_manager
import poll_manager
import extractor

def _make_google_service():
    svc_cal, svc_sheets = extractor._safe_get_google_services()
    return svc_cal

def run_sync():
    print("Iniciando forzado de sincronización de Google Calendar...")
    db = data_manager.DataManager('planificacion.db')
    pm = poll_manager.PollingManager(db, _make_google_service)
    
    tecnicos = db.obtener_tecnicos()
    for tec in tecnicos:
        print(f"Sincronizando calendario de: {tec['nombre']} ({tec['correo']})")
        try:
            pm._poll_calendar(tec['correo'], tec['nombre'])
        except Exception as e:
            print(f"Error sincronizando {tec['correo']}: {e}")
        
    print("¡Sincronización completada con éxito!")

if __name__ == '__main__':
    run_sync()
