from hydration_service import HydrationService, RealOtRepository
from data_manager import DataManager

db = DataManager()
repo = RealOtRepository(db)
h = HydrationService(repo)

title = "8825 ( AKRIMET) - CAL - ND/NM"
ot = h.extract_ot_from_title(title)
print(f"Title: {title}")
print(f"Extracted OT: {ot}")

if ot:
    data = repo.get_ot(ot)
    print(f"Data in Repo: {data}")
    
    # Test hydration
    ev = {"summary": title, "extendedProperties": {}}
    enriched = h.hydrate_event(ev)
    print(f"Enriched: {enriched['extendedProperties']}")
