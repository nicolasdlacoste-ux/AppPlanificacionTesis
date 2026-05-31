import json
import sys
import datetime

sys.path.append('.')
from utils import ExtendedPropertiesSanitizer

# Mock data
test_metadata = {
    "private": {
        "str_val": "hello",
        "int_val": 123,
        "bool_val": True,
        "none_val": None,
        "dict_val": {"nested": "value"},
        "list_val": [1, 2, 3],
        "date_val": datetime.date(2026, 5, 11),
        "dt_val": datetime.datetime(2026, 5, 11, 10, 0, 0)
    }
}

print("--- PAYLOAD PREVIO ---")
print(json.dumps(test_metadata, indent=2, default=str))

print("\n--- EJECUTANDO SANITIZACIÓN ---")
sanitized = ExtendedPropertiesSanitizer.sanitize(test_metadata)

print("\n--- PAYLOAD SANITIZADO ---")
print(json.dumps(sanitized, indent=2))

# Validaciones
private = sanitized.get("private", {})
errors = []

for k, v in private.items():
    if not isinstance(v, str):
        errors.append(f"ERROR: Key '{k}' is NOT a string ({type(v)})")

if "none_val" in private:
    errors.append("ERROR: 'none_val' should have been removed")

if private.get("bool_val") != "true":
    errors.append(f"ERROR: 'bool_val' expected 'true', got '{private.get('bool_val')}'")

if errors:
    print("\n--- RESULTADO: FALLIDO ---")
    for e in errors:
        print(e)
else:
    print("\n--- RESULTADO: COMPATIBILIDAD GOOGLE CONFIRMADA ---")
    print("Todos los valores en 'private' son strings.")
