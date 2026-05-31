import json
import time
from typing import List, Dict
from data_manager import DataManager
from hydration_service import HydrationService, RealOtRepository
from utils import _poll_log

class HistoricalHydrator:
    """
    Herramienta para normalizar eventos históricos en SQLite inyectando metadata faltante.
    """

    def __init__(self, db: DataManager, hydration_service: HydrationService):
        self.db = db
        self.hydrator = hydration_service

    def run(self, limit: int = 100, dry_run: bool = True):
        """
        Ejecuta el proceso de re-hidratación sobre un lote de eventos.
        """
        print(f"\n[REHYDRATION] Iniciando ciclo (limit={limit}, dry_run={dry_run})")
        
        # 1. Obtener eventos de la DB
        # Usamos obtener_eventos_dict que ya mapea extended_props
        all_events = self.db.obtener_eventos_dict()
        
        # 2. Filtrar los que necesitan hidratación
        to_process = []
        for ev in all_events:
            if self.hydrator.needs_hydration(ev):
                to_process.append(ev)
        
        # Limitar el lote
        to_process = to_process[:limit]
        
        stats = {
            "scanned": len(to_process),
            "applied": 0,
            "skipped": 0,
            "metadata_completed": 0,
            "no_match": 0,
            "errors": 0
        }

        if not to_process:
            print("[REHYDRATION] No hay eventos que requieran hidratación.")
            return stats

        for ev in to_process:
            try:
                event_id = ev["id"]
                summary = ev.get("summary") or ev.get("evento", "Sin título")
                
                # Simular estructura de Google para el hydrator
                # (El hydrator espera 'summary' y 'extendedProperties')
                fake_g_ev = {
                    "summary": summary,
                    "extendedProperties": ev.get("extendedProperties", {})
                }
                
                # Intentar hidratar
                enriched = self.hydrator.hydrate_event(fake_g_ev)
                new_ext = enriched.get("extendedProperties", {})
                
                # Comparar con lo que ya teníamos
                old_ext = ev.get("extendedProperties", {})
                
                # ¿Hubo cambios reales?
                has_changes = False
                for key in ["app_ot", "app_vehiculo", "app_patrones"]:
                    old_val = old_ext.get(key)
                    new_val = new_ext.get(key)
                    if new_val != old_val:
                        has_changes = True
                        break
                
                if not has_changes:
                    stats["skipped"] += 1
                    continue

                # Si llegamos aquí, hay mejoras posibles
                if new_ext.get("hydrated"):
                    stats["applied"] += 1
                    msg = f"Event '{summary[:30]}' enriched with OT {new_ext.get('app_ot')}"
                else:
                    stats["no_match"] += 1
                    msg = f"Event '{summary[:30]}' scanned, but no OT match found."

                # Log individual
                log_type = "hydration_applied" if new_ext.get("hydrated") else "metadata_completed"
                _poll_log(self.db, "REHYDRATION", log_type, 
                          {"summary": summary[:50], "new_metadata": new_ext},
                          event_id=event_id)

                if not dry_run:
                    # Persistir incrementalmente
                    self.db.actualizar_extended_props_incremental(event_id, new_ext)
                
                print(f"[REHYDRATION] {log_type}: {summary[:40]}...")

            except Exception as e:
                stats["errors"] += 1
                print(f"[REHYDRATION] Error procesando evento {ev.get('id')}: {e}")
                _poll_log(self.db, "REHYDRATION", "parse_failed", {"error": str(e)}, event_id=ev.get('id'))

        # Resumen final
        self._print_summary(stats, dry_run)
        _poll_log(self.db, "REHYDRATION", "batch_completed", stats)
        
        return stats

    def _print_summary(self, stats, dry_run):
        total = stats["scanned"]
        if total == 0: return
        
        perc_enriched = round((stats["applied"] / total) * 100, 1) if total > 0 else 0
        
        print("\n" + "="*40)
        print(f" RESUMEN DE RE-HYDRATION {'(DRY RUN)' if dry_run else ''}")
        print("="*40)
        print(f" - Eventos escaneados:    {total}")
        print(f" - Eventos enriquecidos:  {stats['applied']} ({perc_enriched}%)")
        print(f" - Datos completados:     {stats['metadata_completed']}")
        print(f" - Sin match de OT:       {stats['no_match']}")
        print(f" - Ignorados/Sin cambio:  {stats['skipped']}")
        print(f" - Errores:               {stats['errors']}")
        print("="*40 + "\n")

if __name__ == "__main__":
    # Script mode
    from data_manager import DataManager
    db = DataManager()
    repo = RealOtRepository(db)
    h_service = HydrationService(repo)
    
    hydrator = HistoricalHydrator(db, h_service)
    # Ejecutar dry-run por defecto de los primeros 100
    hydrator.run(limit=100, dry_run=True)
