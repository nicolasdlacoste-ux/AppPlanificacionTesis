"""
Prueba unitaria del FieldOwnershipRegistry y su integración con _compute_diff.
Verifica que los falsos positivos de CRITICAL_DIFF en extended_props son eliminados.
"""
import json
import sys
import os
sys.path.append(os.path.abspath('.'))

from field_ownership import FieldOwnershipRegistry, FieldOwnership
from poll_manager import _compute_diff
from utils import _normalize

passed = 0
failed = 0

def assert_eq(label, actual, expected):
    global passed, failed
    if actual == expected:
        print(f"  [OK] {label}")
        passed += 1
    else:
        print(f"  [FAIL] {label}: expected {expected}, got {actual}")
        failed += 1

# ═══════════════════════════════════════════════════════════════════════
print("TEST 1: SAFE field classification")
assert_eq("descripcion is SHARED_SAFE", 
    FieldOwnershipRegistry.classify_field("descripcion").value, "SHARED_SAFE")
assert_eq("ubicacion is SHARED_SAFE",
    FieldOwnershipRegistry.classify_field("ubicacion").value, "SHARED_SAFE")

# ═══════════════════════════════════════════════════════════════════════
print("\nTEST 2: CRITICAL field classification")
assert_eq("summary is SHARED_CRITICAL",
    FieldOwnershipRegistry.classify_field("summary").value, "SHARED_CRITICAL")
assert_eq("inicio is SHARED_CRITICAL",
    FieldOwnershipRegistry.classify_field("inicio").value, "SHARED_CRITICAL")
assert_eq("tecnico_nombre is SHARED_CRITICAL",
    FieldOwnershipRegistry.classify_field("tecnico_nombre").value, "SHARED_CRITICAL")

# ═══════════════════════════════════════════════════════════════════════
print("\nTEST 3: PLANNER_OWNED private props")
assert_eq("app_vehiculo is PLANNER_OWNED",
    FieldOwnershipRegistry.classify_private_prop("app_vehiculo").value, "PLANNER_OWNED")
assert_eq("app_patrones is PLANNER_OWNED",
    FieldOwnershipRegistry.classify_private_prop("app_patrones").value, "PLANNER_OWNED")
assert_eq("source is PLANNER_OWNED",
    FieldOwnershipRegistry.classify_private_prop("source").value, "PLANNER_OWNED")

# ═══════════════════════════════════════════════════════════════════════
print("\nTEST 4: extended_props diff — CRITICAL_DIFF false positive elimination")

# Simula el escenario real del Test 1: Local tiene metadata rica, Google devuelve subset
local = {
    "summary": "8511 (AYUDIN) - CAL - LR",
    "inicio": "2026-05-15T07:00:00-03:00",
    "fin": "2026-05-15T16:00:00-03:00",
    "ubicacion": "",
    "descripcion": "Patrones: AK-083, AK-087a",
    "extended_props": json.dumps({
        "private": {
            "app_patrones": "[\"AK-083\", \"AK-087a\"]",
            "app_vehiculo": "Hilux",
            "source": "internal",
            "sync_origin": "sync_worker",
            "app_ot": "8511",
            "hydrated": "true"
        }
    })
}

g_mapped = {
    "summary": "8511 (AYUDIN) - CAL - LR",
    "inicio": "2026-05-15T07:00:00-03:00",
    "fin": "2026-05-15T16:00:00-03:00",
    "ubicacion": "",
    "descripcion": "Patrones: AK-083, AK-087a\n[TEST_SAFE] 2026-05-10 18:47:58",
    "extended_props": json.dumps({
        "private": {
            "app_patrones": "[\"AK-083\", \"AK-087a\"]"
        }
    })
}

diff = _compute_diff(local, g_mapped)
print(f"  Diff keys: {list(diff.keys())}")

# La descripción cambió → debe ser SAFE
assert_eq("descripcion detected as safe",
    diff.get("descripcion", {}).get("category"), "safe")

# extended_props: las ÚNICAS diferencias son PLANNER_OWNED (vehiculo, source, etc.)
# → NO debe generar un diff de extended_props
assert_eq("extended_props NOT in diff (planner_owned filtered out)",
    "extended_props" not in diff, True)

# ═══════════════════════════════════════════════════════════════════════
print("\nTEST 5: extended_props diff — real shared change IS detected")

local2 = dict(local)
g_mapped2 = {
    "summary": "8511 (AYUDIN) - CAL - LR",
    "inicio": "2026-05-15T07:00:00-03:00",
    "fin": "2026-05-15T16:00:00-03:00",
    "ubicacion": "",
    "descripcion": "Patrones: AK-083, AK-087a",
    "extended_props": json.dumps({
        "private": {
            "app_patrones": "[\"AK-083\", \"AK-087a\"]",
            "some_shared_field": "new_value"
        }
    })
}

diff2 = _compute_diff(local2, g_mapped2)
assert_eq("extended_props IS in diff (has shared change)",
    "extended_props" in diff2, True)
if "extended_props" in diff2:
    assert_eq("category is metadata_change",
        diff2["extended_props"]["category"], "metadata_change")

# ═══════════════════════════════════════════════════════════════════════
print("\nTEST 6: summary change -> CRITICAL")

g_mapped3 = dict(g_mapped)
g_mapped3["summary"] = "[MODIFIED] 8511 (AYUDIN)"
g_mapped3["descripcion"] = local["descripcion"]  # no change
g_mapped3["extended_props"] = local["extended_props"]  # no change

diff3 = _compute_diff(local, g_mapped3)
assert_eq("summary is critical",
    diff3.get("summary", {}).get("category"), "critical")
assert_eq("ownership is SHARED_CRITICAL",
    diff3.get("summary", {}).get("ownership"), "SHARED_CRITICAL")

# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print(f"RESULTS: {passed} passed, {failed} failed")
if failed > 0:
    sys.exit(1)
