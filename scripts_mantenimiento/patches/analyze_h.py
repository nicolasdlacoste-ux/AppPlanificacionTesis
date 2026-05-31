from data_manager import DataManager
from hydration_service import HydrationService, RealOtRepository
from historical_hydrator import HistoricalHydrator

db = DataManager()
repo = RealOtRepository(db)
h_service = HydrationService(repo)

all_events = db.obtener_eventos_dict()
to_process = [ev for ev in all_events if h_service.needs_hydration(ev)][:20]

print("Análisis de los primeros 20 eventos que necesitan hidratación:")
for ev in to_process:
    summary = ev.get("summary") or "Sin título"
    ot = h_service.extract_ot_from_title(summary)
    data = repo.get_ot(ot) if ot else None
    print(f"- Title: {summary[:40]:40s} | OT: {str(ot):8s} | Repo Match: {data is not None}")
