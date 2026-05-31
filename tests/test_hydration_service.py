"""
Tests for HydrationService – ejecutar con: python test_hydration_service.py
Cubre los casos principales de hydration.
"""
from hydration_service import HydrationService, OtRepository

# Colores ANSI para consola
OK = "\033[92m[OK]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"

passed = 0
failed = 0


def assert_equal(label, actual, expected):
    global passed, failed
    if actual == expected:
        print(f"  {OK}  {label}")
        passed += 1
    else:
        print(f"  {FAIL} {label}")
        print(f"       expected: {expected}")
        print(f"       got:      {actual}")
        failed += 1


repo = OtRepository()
service = HydrationService(repo)

# ─────────────────────────────────────────────
# CASO 1: OT encontrada con datos en repo
# ─────────────────────────────────────────────
print("\n[Caso 1] Título con OT conocida (OT12345)")
ev = {"summary": "Revisión OT12345 – cliente X", "extendedProperties": {}}
result = service.hydrate_event(ev)
ext = result["extendedProperties"]
assert_equal("hydrated = True",         ext.get("hydrated"),      True)
assert_equal("app_ot = '12345'",        ext.get("app_ot"),        "12345")
assert_equal("app_vehiculo correcto",   ext.get("app_vehiculo"),  "Camión A")
assert_equal("app_patrones correctos",  ext.get("app_patrones"),  ["Pat‑A", "Pat‑B"])

# ─────────────────────────────────────────────
# CASO 2: Formato alternativo [#67890]
# ─────────────────────────────────────────────
print("\n[Caso 2] Título con patrón [#67890]")
ev = {"summary": "Inspección [#67890]", "extendedProperties": {}}
result = service.hydrate_event(ev)
ext = result["extendedProperties"]
assert_equal("hydrated = True",        ext.get("hydrated"),      True)
assert_equal("app_ot = '67890'",       ext.get("app_ot"),        "67890")
assert_equal("app_vehiculo correcto",  ext.get("app_vehiculo"),  "Furgón B")

# ─────────────────────────────────────────────
# CASO 3: OT no existe en el repositorio
# ─────────────────────────────────────────────
print("\n[Caso 3] OT detectada pero no existe en repo (OT99999)")
ev = {"summary": "Trabajo OT99999", "extendedProperties": {}}
result = service.hydrate_event(ev)
ext = result["extendedProperties"]
assert_equal("hydrated = False",    ext.get("hydrated"),     False)
assert_equal("app_ot = '99999'",    ext.get("app_ot"),       "99999")
assert_equal("app_vehiculo = None", ext.get("app_vehiculo"), None)
assert_equal("app_patrones = []",   ext.get("app_patrones"), [])

# ─────────────────────────────────────────────
# CASO 4: Sin OT en el título
# ─────────────────────────────────────────────
print("\n[Caso 4] Evento sin OT en el título")
ev = {"summary": "Reunión de equipo", "extendedProperties": {}}
result = service.hydrate_event(ev)
ext = result["extendedProperties"]
assert_equal("hydrated = False",    ext.get("hydrated"),     False)
assert_equal("app_ot = None",       ext.get("app_ot"),       None)
assert_equal("app_vehiculo = None", ext.get("app_vehiculo"), None)

# ─────────────────────────────────────────────
# CASO 5: Sin extendedProperties en el evento
# ─────────────────────────────────────────────
print("\n[Caso 5] Evento sin campo extendedProperties (evento manual)")
ev = {"summary": "Mantenimiento OT-12345"}
result = service.hydrate_event(ev)
ext = result.get("extendedProperties", {})
assert_equal("extendedProperties creado", isinstance(ext, dict), True)
assert_equal("hydrated = True",           ext.get("hydrated"),   True)
assert_equal("app_ot = '12345'",          ext.get("app_ot"),     "12345")

# ─────────────────────────────────────────────
# CASO 6: El evento original NO se muta
# ─────────────────────────────────────────────
print("\n[Caso 6] El evento original no debe ser mutado")
original = {"summary": "Reparación OT_67890", "extendedProperties": {}}
original_before = dict(original)
_ = service.hydrate_event(original)
assert_equal("original intacto", original, original_before)

# ─────────────────────────────────────────────
# Resumen
# ─────────────────────────────────────────────
print(f"\n{'='*40}")
print(f"  Resultado: {passed} pasados, {failed} fallidos")
print(f"{'='*40}")
if failed > 0:
    exit(1)
