"""
field_ownership.py
──────────────────
Sistema formal de ownership y clasificación semántica de campos
para la reconciliación Polling ↔ SQLite.

Define autoridad por campo para eliminar:
  - CRITICAL_DIFF falsos positivos
  - overwrite ambiguo de metadata
  - drift innecesario entre Google y Planner
  - conflictos de metadata (vehículo/patrones)

Categorías:
  PLANNER_OWNED   — Google NO debe sobrescribir. Autoridad local.
  GOOGLE_OWNED    — Siempre aceptar desde Google. Autoridad remota.
  SHARED_SAFE     — Auto-merge permitido sin revisión.
  SHARED_CRITICAL — Requieren revisión humana antes de aplicar.
"""

import json
from enum import Enum
from typing import Optional


class FieldOwnership(Enum):
    """Categoría de autoridad de un campo."""
    PLANNER_OWNED   = "PLANNER_OWNED"
    GOOGLE_OWNED    = "GOOGLE_OWNED"
    SHARED_SAFE     = "SHARED_SAFE"
    SHARED_CRITICAL = "SHARED_CRITICAL"


# ── REGISTRO DE CAMPOS ──────────────────────────────────────────────────────

# Campos de primer nivel del evento (columnas de la tabla `eventos`)
_TOP_LEVEL_REGISTRY = {
    # SHARED_CRITICAL — cambios que requieren revisión humana
    "summary":        FieldOwnership.SHARED_CRITICAL,
    "inicio":         FieldOwnership.SHARED_CRITICAL,
    "fin":            FieldOwnership.SHARED_CRITICAL,
    "tecnico_nombre": FieldOwnership.SHARED_CRITICAL,

    # SHARED_SAFE — auto-merge sin revisión
    "descripcion":    FieldOwnership.SHARED_SAFE,
    "ubicacion":      FieldOwnership.SHARED_SAFE,
}

# Campos dentro de extendedProperties.private
_PRIVATE_PROPS_REGISTRY = {
    # PLANNER_OWNED — el polling NUNCA debe sobrescribir estos
    "app_vehiculo":    FieldOwnership.PLANNER_OWNED,
    "app_patrones":    FieldOwnership.PLANNER_OWNED,
    "app_ot":          FieldOwnership.PLANNER_OWNED,
    "app_ots":         FieldOwnership.PLANNER_OWNED,
    "grupo_id":        FieldOwnership.PLANNER_OWNED,
    "hydrated":        FieldOwnership.PLANNER_OWNED,
    "source":          FieldOwnership.PLANNER_OWNED,
    "sync_origin":     FieldOwnership.PLANNER_OWNED,
    "sync_status":     FieldOwnership.PLANNER_OWNED,
    "pending_sync":    FieldOwnership.PLANNER_OWNED,
    "mutation_type":   FieldOwnership.PLANNER_OWNED,
    "last_local_update": FieldOwnership.PLANNER_OWNED,
    "version":         FieldOwnership.PLANNER_OWNED,

    # GOOGLE_OWNED — metadatos de sistema que siempre vienen de Google
    # (normalmente no están en private, pero por si acaso)
}

# Campos de nivel raíz del evento Google que son GOOGLE_OWNED
_GOOGLE_SYSTEM_FIELDS = {
    "status", "etag", "htmlLink", "created", "updated",
    "organizer", "creator", "iCalUID", "sequence",
    "kind", "colorId", "recurringEventId",
}


# ── API PÚBLICA ──────────────────────────────────────────────────────────────

class FieldOwnershipRegistry:
    """
    Registro centralizado de ownership de campos.
    Usado por poll_manager para tomar decisiones de reconciliación.
    """

    @staticmethod
    def classify_field(field_name: str) -> FieldOwnership:
        """Clasifica un campo de primer nivel."""
        return _TOP_LEVEL_REGISTRY.get(field_name, FieldOwnership.SHARED_SAFE)

    @staticmethod
    def classify_private_prop(prop_name: str) -> FieldOwnership:
        """Clasifica un campo dentro de extendedProperties.private."""
        return _PRIVATE_PROPS_REGISTRY.get(prop_name, FieldOwnership.SHARED_SAFE)

    @staticmethod
    def is_google_system_field(field_name: str) -> bool:
        """True si el campo es metadata de sistema de Google (nunca genera conflicto)."""
        return field_name in _GOOGLE_SYSTEM_FIELDS

    @staticmethod
    def classify_diff(local: dict, g_mapped: dict, normalize_fn=None) -> dict:
        """
        Calcula el diff entre el estado local y el estado mapeado de Google,
        clasificando cada campo según su ownership.

        Retorna: {
            field_name: {
                "old": ..., "new": ...,
                "ownership": FieldOwnership,
                "category": "safe" | "critical" | "planner_owned" | "google_owned"
            }
        }
        """
        if normalize_fn is None:
            normalize_fn = lambda v: str(v).strip() if v is not None else ""

        diff = {}

        # 1. Campos de primer nivel (excepto extended_props, que tiene tratamiento especial)
        TOP_FIELDS = ("summary", "inicio", "fin", "ubicacion", "descripcion")
        for field in TOP_FIELDS:
            old = normalize_fn(local.get(field))
            new = normalize_fn(g_mapped.get(field))
            if old != new:
                ownership = FieldOwnershipRegistry.classify_field(field)
                diff[field] = {
                    "old": old,
                    "new": new,
                    "ownership": ownership.value,
                    "category": _ownership_to_category(ownership),
                }

        # 2. Diff semántico de extended_props
        ext_diff = FieldOwnershipRegistry.classify_extended_props_diff(
            local.get("extended_props"),
            g_mapped.get("extended_props"),
        )
        if ext_diff:
            diff["extended_props"] = ext_diff

        return diff

    @staticmethod
    def classify_extended_props_diff(local_ext_raw, google_ext_raw) -> Optional[dict]:
        """
        Diff semántico de extendedProperties.

        En lugar de comparar el JSON completo como string, parsea ambos lados,
        descompone `private` en campos individuales, y aplica ownership a cada uno.

        Retorna None si no hay diferencias relevantes (tras filtrar PLANNER_OWNED).
        Retorna un dict con la estructura del diff si hay cambios que importan.
        """
        # Parsear
        local_ext = _parse_ext(local_ext_raw)
        google_ext = _parse_ext(google_ext_raw)

        local_private = local_ext.get("private", {})
        google_private = google_ext.get("private", {})

        if isinstance(local_private, str):
            try: local_private = json.loads(local_private)
            except: local_private = {}
        if isinstance(google_private, str):
            try: google_private = json.loads(google_private)
            except: google_private = {}

        # Obtener todas las claves
        all_keys = set(local_private.keys()) | set(google_private.keys())

        changes = {}
        planner_owned_filtered = []

        for key in all_keys:
            local_val = _norm_prop_val(local_private.get(key))
            google_val = _norm_prop_val(google_private.get(key))

            if local_val == google_val:
                continue

            ownership = FieldOwnershipRegistry.classify_private_prop(key)

            if ownership == FieldOwnership.PLANNER_OWNED:
                # Registrar para logging pero NO incluir en el diff funcional
                planner_owned_filtered.append({
                    "field": key,
                    "owner": ownership.value,
                    "local_val": local_val,
                    "google_val": google_val,
                    "action": "overwrite_blocked",
                })
                continue

            # Campo compartido o Google-owned con diferencia real
            changes[key] = {
                "old": local_val,
                "new": google_val,
                "ownership": ownership.value,
            }

        if not changes:
            # Todas las diferencias eran PLANNER_OWNED → no hay diff real
            return None

        return {
            "old": json.dumps(local_ext, ensure_ascii=False),
            "new": json.dumps(google_ext, ensure_ascii=False),
            "ownership": "MIXED",
            "category": "metadata_change",
            "field_details": changes,
            "planner_owned_filtered": planner_owned_filtered,
        }

    @staticmethod
    def build_ownership_log(field: str, ownership: FieldOwnership,
                            incoming_source: str, action: str,
                            old_val=None, new_val=None) -> dict:
        """Construye un log entry de [FIELD_OWNERSHIP]."""
        return {
            "field": field,
            "owner": ownership.value,
            "incoming_source": incoming_source,
            "reconciliation_action": action,
            "overwrite_blocked": ownership == FieldOwnership.PLANNER_OWNED and action == "blocked",
            "old_value": str(old_val)[:100] if old_val else None,
            "new_value": str(new_val)[:100] if new_val else None,
        }


# ── HELPERS INTERNOS ─────────────────────────────────────────────────────────

def _ownership_to_category(ownership: FieldOwnership) -> str:
    """Mapea ownership a la categoría legacy usada en el diff."""
    return {
        FieldOwnership.PLANNER_OWNED:   "planner_owned",
        FieldOwnership.GOOGLE_OWNED:    "google_owned",
        FieldOwnership.SHARED_SAFE:     "safe",
        FieldOwnership.SHARED_CRITICAL: "critical",
    }[ownership]


def _parse_ext(raw) -> dict:
    """Parsea extended_props desde string JSON o dict."""
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
    if isinstance(raw, dict):
        return raw
    return {}


def _norm_prop_val(val) -> str:
    """Normaliza un valor de propiedad para comparación."""
    if val is None:
        return ""
    if isinstance(val, (dict, list)):
        return json.dumps(val, sort_keys=True, ensure_ascii=False)
    return str(val).strip()
