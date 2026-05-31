import re
import json
from typing import Dict, List, Optional


class OtRepository:
    """Mock repository for OT data. In production this would query a DB or cache."""

    def __init__(self):
        # Simple in‑memory mock: ot_id -> data
        self._data = {
            "12345": {"vehicle": "Camión A", "patterns": ["Pat‑A", "Pat‑B"]},
            "67890": {"vehicle": "Furgón B", "patterns": ["Pat‑C"]},
        }

    def get_ot(self, ot_id: str) -> Optional[Dict]:
        return self._data.get(ot_id)


class RealOtRepository:
    """Repositorio real que consulta la tabla 'grupos' de SQLite.

    La tabla grupos ya relaciona ot_nro, vehiculo y patrones de forma directa.
    Si la OT nunca tuvo un grupo, devuelve None y hydration queda en False.
    """

    def __init__(self, db) -> None:
        self._db = db

    def get_ot(self, ot_id: str) -> Optional[Dict]:
        """Busca la OT en la tabla grupos por ot_nro.
        Devuelve {"vehicle": str, "patterns": list} o None si no existe.
        """
        with self._db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT vehiculo, patrones FROM grupos WHERE ot_nro = ? LIMIT 1",
                (ot_id,)
            )
            row = cursor.fetchone()
        if not row:
            return None
        patrones_raw = row[1]
        try:
            patrones = json.loads(patrones_raw) if patrones_raw else []
        except Exception:
            patrones = []
        return {
            "vehicle": row[0],
            "patterns": patrones,
        }


class HydrationService:
    """Enrich a raw Google Calendar event with OT, vehicle and pattern data.

    - No side‑effects (no DB writes, no Google API calls).
    - Returns a *new* dict; the original event is left untouched.
    """

    OT_REGEX = re.compile(r"\bOT[-_]?([0-9]{4,})\b", re.IGNORECASE)
    ALT_REGEX = re.compile(r"\[#([0-9]{4,})\]", re.IGNORECASE)
    AGGRESSIVE_REGEX = re.compile(r"\b([0-9]{4,})\b")

    def __init__(self, ot_repo: OtRepository):
        self.ot_repo = ot_repo

    # ---------------------------------------------------------------------
    def hydrate_event(self, event: Dict) -> Dict:
        """Public API – takes a raw event and returns an enriched copy.

        Expected input keys:
            - "summary": str (title)
            - "extendedProperties": optional dict (may be empty)
        Output adds/updates the "extendedProperties" dict with:
            - "app_ot": detected OT id (str) or None
            - "app_vehiculo": vehicle name or None
            - "app_patrones": list of patterns or []
            - "hydrated": bool flag indicating whether enrichment succeeded
        """
        # shallow copy to avoid mutating caller's dict (but we need deep copy for nested dicts like extProps)
        enriched = dict(event)
        title = enriched.get("summary", "")
        ot_id = self.extract_ot_from_title(title)
        # Prepare extendedProperties container - copy it to avoid mutation
        original_ext = enriched.get("extendedProperties", {})
        if not isinstance(original_ext, dict):
            ext = {}
        else:
            ext = dict(original_ext) # copy!
        if ot_id:
            ot_found = self.attach_related_data(ext, ot_id)
            ext["app_ot"] = ot_id
            ext["hydrated"] = ot_found  # True solo si la OT existe en el repositorio
        else:
            # No OT found – still mark as not hydrated
            ext["app_ot"] = None
            ext["app_vehiculo"] = None
            ext["app_patrones"] = []
            ext["hydrated"] = False
        enriched["extendedProperties"] = ext
        return enriched

    # ---------------------------------------------------------------------
    def extract_ot_from_title(self, title: str) -> Optional[str]:
        """Return the OT number found in the title, or None.
        Supports patterns like "OT12345", "[#12345]" and aggressive 4+ digit matching.
        """
        if not title:
            return None
        m = self.OT_REGEX.search(title)
        if m:
            return m.group(1)
        m = self.ALT_REGEX.search(title)
        if m:
            return m.group(1)
        m = self.AGGRESSIVE_REGEX.search(title)
        if m:
            return m.group(1)
        return None

    # ---------------------------------------------------------------------
    def attach_related_data(self, ext_props: Dict, ot_id: str) -> bool:
        """Lookup OT data and insert vehicle and patterns into the extended dict.
        Returns True if the OT was found in the repository, False otherwise.
        """
        ot_data = self.ot_repo.get_ot(ot_id)
        if not ot_data:
            ext_props["app_vehiculo"] = None
            ext_props["app_patrones"] = []
            return False  # OT detectada en título pero no existe en el repo
        ext_props["app_vehiculo"] = ot_data.get("vehicle")
        ext_props["app_patrones"] = ot_data.get("patterns", [])
        return True

    # ---------------------------------------------------------------------
    def needs_hydration(self, event: Dict) -> bool:
        """True si al evento le faltan uno o más campos críticos de hydration.

        Usar para decidir si un evento existente necesita ser re-hidratado.
        Campos requeridos: app_ot, app_vehiculo, app_patrones.
        """
        ext = event.get("extendedProperties", {})
        if not isinstance(ext, dict):
            return True
        REQUIRED = {"app_ot", "app_vehiculo", "app_patrones"}
        return not REQUIRED.issubset(ext.keys())

# -------------------------------------------------------------------------
# Simple manual test (executed when run as script)
if __name__ == "__main__":
    repo = OtRepository()
    service = HydrationService(repo)
    raw_event = {
        "summary": "Revisión OT12345 – cliente X",
        "extendedProperties": {}
    }
    print(service.hydrate_event(raw_event))
