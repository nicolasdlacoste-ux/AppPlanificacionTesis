"""
tests/convergence_helpers.py

[ETAPA 2 — CONVERGENCE ASSERTIONS]
Helper assert_event_converged para verificar que un evento está convergido
entre SQLite y (opcionalmente) Google Calendar.

Uso en tests:
    from tests.convergence_helpers import assert_event_converged, build_expected

    assert_event_converged(db, event_id, expected={
        "tecnico_nombre": "Nicolás",
        "sync_status": "SUCCESS",
        "app_ots": ["8775"],
        "google_event_id_not_local": True,
    })

Para tests con Google real (--real-google):
    assert_event_converged(db, event_id, expected={...}, google_service=svc)
"""
import json
from typing import Optional


def _get_private(event: dict) -> dict:
    """Extrae extended_props.private de un evento, cualquiera sea el dialecto."""
    ext = event.get("extended_props") or event.get("extendedProperties") or {}
    if isinstance(ext, str):
        try:
            ext = json.loads(ext)
        except Exception:
            ext = {}
    private = ext.get("private", {}) if isinstance(ext, dict) else {}
    return private if isinstance(private, dict) else {}


def assert_event_converged(
    db,
    event_id: str,
    expected: dict,
    google_service=None,
    context: str = "",
) -> dict:
    """
    Verifica que un evento esté convergido entre SQLite (y opcionalmente Google Calendar).

    Parámetros de `expected` reconocidos:
        tecnico_nombre          str   — técnico esperado
        calendar_id             str   — calendar_id esperado
        sync_status             str   — estado sync esperado (default: "SUCCESS")
        pending_sync            int   — pendiente de sync (default: 0)
        google_event_id_not_local bool — True = google_event_id no debe ser local_*
        google_event_id         str   — valor exacto esperado del google_event_id
        app_ots                 list  — OTs esperadas en extended_props.private
        app_patrones            list  — patrones esperados (comparación de conjunto)
        app_vehiculo            str   — vehículo esperado
        summary_contains        str   — subcadena que debe estar en summary
        inicio_starts_with      str   — prefijo esperado en inicio (ej: "2026-05-23")
        fin_starts_with         str   — prefijo esperado en fin

    Si google_service se provee, también compara contra el evento real de Google.

    Lanza AssertionError con detalle completo si hay divergencia.
    Retorna el evento local como dict si todo OK.
    """
    ctx = f" [{context}]" if context else ""

    # ── 1. Leer de SQLite ─────────────────────────────────────────────────────
    ev = db.resolve_event(event_id)
    assert ev is not None, (
        f"[CONVERGENCE{ctx}] Evento '{event_id}' no encontrado en SQLite"
    )

    local_id = ev.get("id", event_id)
    private = _get_private(ev)
    failures = []

    # ── 2. Verificar campos locales ───────────────────────────────────────────
    if "tecnico_nombre" in expected:
        actual = ev.get("tecnico_nombre") or ev.get("tecnico", "")
        if actual != expected["tecnico_nombre"]:
            failures.append(
                f"tecnico_nombre: esperado='{expected['tecnico_nombre']}' actual='{actual}'"
            )

    if "calendar_id" in expected:
        actual = ev.get("calendar_id", "")
        if actual != expected["calendar_id"]:
            failures.append(
                f"calendar_id: esperado='{expected['calendar_id']}' actual='{actual}'"
            )

    exp_sync = expected.get("sync_status", "SUCCESS")
    actual_sync = ev.get("sync_status", "")
    if actual_sync != exp_sync:
        failures.append(
            f"sync_status: esperado='{exp_sync}' actual='{actual_sync}'"
        )

    exp_pending = expected.get("pending_sync", 0)
    actual_pending = ev.get("pending_sync", 0)
    if int(actual_pending) != int(exp_pending):
        failures.append(
            f"pending_sync: esperado={exp_pending} actual={actual_pending}"
        )

    gid = ev.get("google_event_id") or ""
    if expected.get("google_event_id_not_local", False):
        if not gid or gid.startswith("local_"):
            failures.append(
                f"google_event_id: esperado=ID real de Google, actual='{gid}'"
            )

    if "google_event_id" in expected and not expected.get("google_event_id_not_local"):
        if gid != expected["google_event_id"]:
            failures.append(
                f"google_event_id: esperado='{expected['google_event_id']}' actual='{gid}'"
            )

    if "summary_contains" in expected:
        summary = ev.get("summary", "")
        if expected["summary_contains"] not in summary:
            failures.append(
                f"summary: '{expected['summary_contains']}' no encontrado en '{summary}'"
            )

    if "inicio_starts_with" in expected:
        inicio = ev.get("inicio", "")
        if not inicio.startswith(expected["inicio_starts_with"]):
            failures.append(
                f"inicio: esperado que empiece con '{expected['inicio_starts_with']}' actual='{inicio}'"
            )

    if "fin_starts_with" in expected:
        fin = ev.get("fin", "")
        if not fin.startswith(expected["fin_starts_with"]):
            failures.append(
                f"fin: esperado que empiece con '{expected['fin_starts_with']}' actual='{fin}'"
            )

    # ── 3. Verificar metadata ─────────────────────────────────────────────────
    if "app_ots" in expected:
        raw = private.get("app_ots", "[]")
        actual_ots = json.loads(raw) if isinstance(raw, str) else (raw or [])
        exp_set = set(str(x) for x in expected["app_ots"])
        actual_set = set(str(x) for x in actual_ots)
        if exp_set != actual_set:
            failures.append(
                f"app_ots: esperado={sorted(exp_set)} actual={sorted(actual_set)}"
            )

    if "app_patrones" in expected:
        raw = private.get("app_patrones", "[]")
        actual_pat = json.loads(raw) if isinstance(raw, str) else (raw or [])
        exp_set = set(str(x) for x in expected["app_patrones"])
        actual_set = set(str(x) for x in actual_pat)
        if exp_set != actual_set:
            failures.append(
                f"app_patrones: esperado={sorted(exp_set)} actual={sorted(actual_set)}"
            )

    if "app_vehiculo" in expected:
        actual_veh = private.get("app_vehiculo", "")
        if actual_veh != expected["app_vehiculo"]:
            failures.append(
                f"app_vehiculo: esperado='{expected['app_vehiculo']}' actual='{actual_veh}'"
            )

    # ── 4. Verificar contra Google (opcional) ─────────────────────────────────
    if google_service and gid and not gid.startswith("local_"):
        calendar_id = ev.get("calendar_id") or expected.get("calendar_id", "")
        try:
            g_ev = google_service.events().get(
                calendarId=calendar_id, eventId=gid
            ).execute()
            g_summary = g_ev.get("summary", "")
            if ev.get("summary") != g_summary:
                failures.append(
                    f"GOOGLE divergence — summary: local='{ev.get('summary')}' google='{g_summary}'"
                )
            # Verificar metadata en Google
            g_ext = g_ev.get("extendedProperties", {})
            g_priv = g_ext.get("private", {}) if isinstance(g_ext, dict) else {}
            if g_priv.get("source") != "internal":
                failures.append(
                    f"GOOGLE anti_loop: source esperado='internal' actual='{g_priv.get('source')}'"
                )
        except Exception as e:
            failures.append(f"GOOGLE fetch error: {e}")

    # ── 5. Resultado ──────────────────────────────────────────────────────────
    if failures:
        detail = "\n  ".join(failures)
        raise AssertionError(
            f"[CONVERGENCE{ctx}] Evento '{local_id}' no convergido:\n  {detail}\n"
            f"  SQLite snapshot: sync_status={ev.get('sync_status')} "
            f"pending_sync={ev.get('pending_sync')} "
            f"google_event_id={ev.get('google_event_id')}"
        )

    return ev


def build_expected(
    tecnico_nombre: str = None,
    sync_status: str = "SUCCESS",
    pending_sync: int = 0,
    google_event_id_not_local: bool = True,
    app_ots: list = None,
    app_patrones: list = None,
    app_vehiculo: str = None,
    summary_contains: str = None,
    fecha: str = None,
    **kwargs,
) -> dict:
    """
    Constructor de expected dict para assert_event_converged.
    Permite construir el dict de expectativas de forma legible en los tests.
    """
    result = {
        "sync_status": sync_status,
        "pending_sync": pending_sync,
        "google_event_id_not_local": google_event_id_not_local,
    }
    if tecnico_nombre is not None:
        result["tecnico_nombre"] = tecnico_nombre
    if app_ots is not None:
        result["app_ots"] = [str(x) for x in app_ots]
    if app_patrones is not None:
        result["app_patrones"] = app_patrones
    if app_vehiculo is not None:
        result["app_vehiculo"] = app_vehiculo
    if summary_contains is not None:
        result["summary_contains"] = summary_contains
    if fecha is not None:
        result["inicio_starts_with"] = fecha
    result.update(kwargs)
    return result
