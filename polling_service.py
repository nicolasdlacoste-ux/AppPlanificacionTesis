from poll_manager import PollingManager
from hydration_service import HydrationService, RealOtRepository
from datetime import datetime

class PollingService:
    """
    Servicio síncrono dedicado exclusivamente a orquestar la lectura 
    desde Google Calendar. No utiliza threads ni se integra con la subida.
    """
    def __init__(self, db, google_service_factory):
        self.db = db
        self.google_service_factory = google_service_factory
        
        # Inyectar HydrationService
        ot_repo = RealOtRepository(db)
        hydrator = HydrationService(ot_repo)
        
        # Instanciamos el manager original una sola vez para reusar su lógica interna
        # sin arrancar sus hilos (start() no es llamado).
        self._legacy_manager = PollingManager(
            self.db, 
            self.google_service_factory, 
            hydration_service=hydrator
        )

    def run_cycle(self):
        """
        Ejecuta un ciclo secuencial iterando sobre todos los calendarios.
        """
        print("[PollingService] Iniciando ciclo de lectura...")
        tecnicos = self.db.obtener_tecnicos()
        
        for tec in tecnicos:
            calendar_id = tec.get("correo")
            tec_nombre = tec.get("nombre", "Desconocido")
            
            if calendar_id:
                self.poll_calendar(calendar_id, tec_nombre)
                
        print("[PollingService] Ciclo finalizado.")

    def poll_calendar(self, calendar_id: str, tec_nombre: str):
        """
        Delega el procesamiento pesado a las funciones existentes en poll_manager.
        """
        try:
            # Llamamos a la función interna que hace el GET y procesa los eventos
            stats = self._legacy_manager._poll_calendar(calendar_id, tec_nombre)
            
            # Guardar el timestamp actual para que el próximo ciclo
            # solo traiga los deltas (cambios nuevos) y no entre en un loop infinito
            now_iso = datetime.utcnow().isoformat() + "Z"
            self.db.update_last_poll_time(calendar_id, now_iso)
            
            print(f"[PollingService] OK - {calendar_id} -> Cambios: {stats.get('changes', 0)}")
            return stats
        
        except Exception as e:
            # Stub de manejo de errores
            print(f"[PollingService] ERROR en {calendar_id}: {str(e)}")
            return None
