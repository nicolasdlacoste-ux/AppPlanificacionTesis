from data_manager import DataManager
from hydration_service import HydrationService, RealOtRepository
from historical_hydrator import HistoricalHydrator

db = DataManager()
repo = RealOtRepository(db)
h_service = HydrationService(repo)

hydrator = HistoricalHydrator(db, h_service)
print("Ejecutando re-hidratación REAL (100 eventos)...")
hydrator.run(limit=100, dry_run=False)
