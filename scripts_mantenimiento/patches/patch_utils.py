import os, re

text = open('utils.py', encoding='utf-8').read()

old_norm = r'''        # 2\. Parsear a datetime aware\s+if isinstance\(val, str\):\s+if "T" not in val:\s+# All-day date \(YYYY-MM-DD\)\s+try:\s+dt_naive = datetime\.datetime\.strptime\(val, "%Y-%m-%d"\)\s+dt = ARG_TZ\.localize\(dt_naive\)\s+except: return val'''

new_norm = '''        # 2. Parsear a datetime aware
        if isinstance(val, str):
            if "T" not in val:
                # All-day date (YYYY-MM-DD) -> PRESERVAR FORMATO!
                if len(val) == 10: return val
                try:
                    dt_naive = datetime.datetime.strptime(val, "%Y-%m-%d")
                    dt = ARG_TZ.localize(dt_naive)
                except: return val'''

text = re.sub(old_norm, new_norm, text)

old_prep = r'''    @staticmethod\s+def prepare_for_google\(val\) -> dict:\s+"""[^"]+"""\s+norm = TimeNormalizationService\.normalize_to_utc_z\(val\)\s+if not norm: return None\s+return \{"dateTime": norm\}'''

new_prep = '''    @staticmethod
    def prepare_for_google(val) -> dict:
        """
        [TIME_NORMALIZATION] Genera el payload para Google Calendar API.
        Usa UTC Z y NUNCA envia timeZone redundante (evita HTTP 400).
        Si es un string All-Day (YYYY-MM-DD), retorna {"date": ...}
        """
        norm = TimeNormalizationService.normalize_to_utc_z(val)
        if not norm: return None
        if "T" not in norm:
            return {"date": norm[:10]}
        return {"dateTime": norm}'''

text = re.sub(old_prep, new_prep, text)
open('utils.py', 'w', encoding='utf-8').write(text)
print("Patched utils.py with regex!")
