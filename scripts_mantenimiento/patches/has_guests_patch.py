
import sys

with open("utils.py", "r", encoding="utf-8") as f:
    js = f.read()

target = """        # OTs normalization
        ots = OTNormalizationService.normalize(g_ev)"""
        
replacement = """        # OTs normalization
        ots = OTNormalizationService.normalize(g_ev)
        
        # Detect guests
        attendees = g_ev.get("attendees", [])
        has_guests = len(attendees) > 1 # Assuming owner is 1
        
        # Inject into extended_props to ensure frontend receives it
        if "private" not in ext: ext["private"] = {}
        ext["private"]["has_guests"] = "true" if has_guests else "false"
"""

if target in js:
    js = js.replace(target, replacement)
    with open("utils.py", "w", encoding="utf-8") as f:
        f.write(js)
    print("utils.py patched for has_guests")
else:
    print("Target not found in utils.py")

