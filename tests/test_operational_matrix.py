"""
tests/test_operational_matrix.py

[ETAPA 1 — OPERATIONAL TEST MATRIX]
Matriz formal de pruebas operacionales para los workflows críticos.
Usa DB SQLite en memoria y mocks de Google Calendar.

Ejecutar:
    python -m pytest tests/test_operational_matrix.py -v

Con Google real (opcional, requiere credenciales):
    python -m pytest tests/test_operational_matrix.py -v --real-google
"""
import sys
import os
import json
import uuid
import pytest
from unittest.mock import MagicMock, patch

# Agregar raíz del proyecto al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data_manager import DataManager
from tests.convergence_helpers import assert_event_converged, build_expected
from utils import assert_metadata_integrity


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _make_event(
    event_id: str = None,
    tecnico: str = "Nicolás",
    calendar_id: str = "nicolas@akrimet.com",
    summary: str = "8775 (DROGUERIA TEST)",
    fecha: str = "2026-05-23",
    app_ots: list = None,
    app_patrones: list = None,
    app_vehiculo: str = "",
    google_event_id: str = None,
    sync_status: str = "SUCCESS",
    pending_sync: int = 0,
) -> dict:
    """Construye un evento mínimo válido para insertar en la DB."""
    eid = event_id or f"local_{uuid.uuid4().hex[:12]}"
    ots = app_ots if app_ots is not None else ["8775"]
    patrones = app_patrones if app_patrones is not None else []
    return {
        "id": eid,
        "calendar_id": calendar_id,
        "tecnico_nombre": tecnico,
        "summary": summary,
        "inicio": f"{fecha}T07:00:00-03:00",
        "fin": f"{fecha}T16:00:00-03:00",
        "ubicacion": "Av. Test 123",
        "descripcion": "Test",
        "extended_props": json.dumps({
            "private": {
                "app_ots": json.dumps(ots),
                "app_patrones": json.dumps(patrones),
                "app_vehiculo": app_vehiculo,
                "source": "internal",
            }
        }),
        "version": 1,
        "sync_status": sync_status,
        "pending_sync": pending_sync,
        "google_event_id": google_event_id or eid,
        "source": "internal",
    }


@pytest.fixture
def db(tmp_path):
    """DataManager con DB SQLite en memoria temporal."""
    db_path = str(tmp_path / "test_planificacion.db")
    dm = DataManager(db_path=db_path)
    return dm


# ─── METADATA INTEGRITY ───────────────────────────────────────────────────────

class TestMetadataIntegrity:
    """Verifica que assert_metadata_integrity detecta correctamente los issues."""

    def test_evento_completo_sin_issues(self):
        ev = _make_event(app_ots=["8775"], app_patrones=["P01"], app_vehiculo="ABC123")
        issues = assert_metadata_integrity(ev, context="test")
        assert issues == [], f"No debería haber issues: {issues}"

    def test_evento_sin_app_ots(self):
        ev = _make_event()
        # Forzar extended_props sin app_ots
        ev["extended_props"] = json.dumps({"private": {"app_patrones": "[]", "app_vehiculo": ""}})
        issues = assert_metadata_integrity(ev, context="test")
        assert any("app_ots_MISSING" in i for i in issues), f"Debería detectar app_ots faltante: {issues}"

    def test_evento_sin_app_patrones(self):
        ev = _make_event()
        ev["extended_props"] = json.dumps({"private": {"app_ots": '["8775"]', "app_vehiculo": ""}})
        issues = assert_metadata_integrity(ev, context="test")
        assert any("app_patrones_MISSING" in i for i in issues), f"Debería detectar app_patrones faltante: {issues}"

    def test_app_ots_json_invalido(self):
        ev = _make_event()
        ev["extended_props"] = json.dumps({"private": {"app_ots": "no-es-json", "app_patrones": "[]", "app_vehiculo": ""}})
        issues = assert_metadata_integrity(ev, context="test")
        assert any("app_ots_INVALID_JSON" in i for i in issues)

    def test_evento_null(self):
        issues = assert_metadata_integrity(None)
        assert issues == ["EVENT_NULL_OR_INVALID"]

    def test_app_vehiculo_tipo_incorrecto(self):
        ev = _make_event()
        ev["extended_props"] = json.dumps({"private": {
            "app_ots": '["8775"]', "app_patrones": "[]", "app_vehiculo": 12345
        }})
        issues = assert_metadata_integrity(ev, context="test")
        assert any("app_vehiculo_WRONG_TYPE" in i for i in issues)


# ─── WATERMARK ANTI-REOPEN ────────────────────────────────────────────────────

class TestWatermarkAntiReopen:
    """Verifica el comportamiento del watermark anti-reopen en enqueue_review."""

    def test_reopen_bloqueado_si_g_updated_antes_de_resolved_at(self, db):
        """Review no se reabre si g_updated <= resolved_at del último accept."""
        gid = f"gev_{uuid.uuid4().hex[:8]}"

        # Crear un review y simularlo como ACCEPTED con resolved_at
        review_id = db.enqueue_review(
            event_id="ev001",
            calendar_id="test@akrimet.com",
            diff={"summary": {"old": "A", "new": "B", "category": "critical"}},
            conflict_type="FIELD_CHANGE",
            google_event_id=gid,
            g_updated="2026-05-20T10:00:00Z",
        )
        assert review_id is not None

        # Marcar como ACCEPTED con resolved_at
        with db._get_connection() as conn:
            conn.execute(
                "UPDATE poll_review_queue SET status='ACCEPTED', resolved_at=? WHERE review_id=?",
                ("2026-05-20T10:05:00Z", review_id)
            )
            conn.commit()

        # Intentar reabrir con g_updated ANTERIOR al resolved_at → debe bloquearse
        result = db.enqueue_review(
            event_id="ev001",
            calendar_id="test@akrimet.com",
            diff={"summary": {"old": "A", "new": "B", "category": "critical"}},
            conflict_type="FIELD_CHANGE",
            google_event_id=gid,
            g_updated="2026-05-20T09:00:00Z",  # ANTES del resolved_at
        )
        assert result is None, "El review no debe reabrirse si g_updated <= resolved_at"

    def test_reopen_permitido_si_g_updated_despues_de_resolved_at(self, db):
        """Review SÍ se reabre si g_updated > resolved_at (cambio genuino post-accept)."""
        gid = f"gev_{uuid.uuid4().hex[:8]}"

        review_id = db.enqueue_review(
            event_id="ev002",
            calendar_id="test@akrimet.com",
            diff={"summary": {"old": "A", "new": "B", "category": "critical"}},
            conflict_type="FIELD_CHANGE",
            google_event_id=gid,
            g_updated="2026-05-20T10:00:00Z",
        )
        assert review_id is not None

        with db._get_connection() as conn:
            conn.execute(
                "UPDATE poll_review_queue SET status='ACCEPTED', resolved_at=? WHERE review_id=?",
                ("2026-05-20T10:05:00Z", review_id)
            )
            conn.commit()

        # Intentar con g_updated POSTERIOR al resolved_at → debe crearse nuevo review
        new_review = db.enqueue_review(
            event_id="ev002",
            calendar_id="test@akrimet.com",
            diff={"summary": {"old": "B", "new": "C", "category": "critical"}},
            conflict_type="FIELD_CHANGE",
            google_event_id=gid,
            g_updated="2026-05-21T08:00:00Z",  # DESPUÉS del resolved_at
        )
        assert new_review is not None, "Debe crear nuevo review para cambio genuino post-accept"

    def test_deduplicacion_pending(self, db):
        """No duplicar reviews si ya hay uno PENDING para el mismo gid."""
        gid = f"gev_{uuid.uuid4().hex[:8]}"

        r1 = db.enqueue_review(
            event_id="ev003", calendar_id="test@akrimet.com",
            diff={"summary": {"old": "A", "new": "B", "category": "critical"}},
            conflict_type="FIELD_CHANGE", google_event_id=gid,
        )
        assert r1 is not None

        r2 = db.enqueue_review(
            event_id="ev003", calendar_id="test@akrimet.com",
            diff={"summary": {"old": "A", "new": "B", "category": "critical"}},
            conflict_type="FIELD_CHANGE", google_event_id=gid,
        )
        assert r2 is None, "No debe duplicar review PENDING"


# ─── CONVERGENCE HELPERS ──────────────────────────────────────────────────────

class TestConvergenceHelpers:
    """Verifica que assert_event_converged detecta divergencias correctamente."""

    def test_evento_convergido_ok(self, db):
        ev = _make_event(
            event_id="conv001",
            tecnico="Nicolás",
            sync_status="SUCCESS",
            pending_sync=0,
            google_event_id="gev_conv001",
            app_ots=["8775"],
        )
        db.guardar_evento_individual(ev)

        result = assert_event_converged(
            db, "conv001",
            build_expected(
                tecnico_nombre="Nicolás",
                sync_status="SUCCESS",
                pending_sync=0,
                app_ots=["8775"],
            )
        )
        assert result is not None

    def test_falla_por_tecnico_incorrecto(self, db):
        ev = _make_event(event_id="conv002", tecnico="Nicolás", sync_status="SUCCESS")
        db.guardar_evento_individual(ev)

        with pytest.raises(AssertionError) as exc_info:
            assert_event_converged(
                db, "conv002",
                build_expected(tecnico_nombre="Mario")  # Técnico incorrecto
            )
        assert "tecnico_nombre" in str(exc_info.value)

    def test_falla_por_sync_status_pendiente(self, db):
        # Insertar directamente via SQL para controlar sync_status
        # (guardar_evento_individual no persiste este campo en su INSERT básico)
        ev = _make_event(event_id="conv003", google_event_id="gev_conv003")
        db.guardar_evento_individual(ev)
        # Forzar sync_status=PENDING y pending_sync=1 directamente
        with db._get_connection() as conn:
            conn.execute(
                "UPDATE eventos SET sync_status='PENDING', pending_sync=1 WHERE id='conv003'"
            )
            conn.commit()

        with pytest.raises(AssertionError) as exc_info:
            assert_event_converged(
                db, "conv003",
                build_expected(sync_status="SUCCESS")
            )
        assert "sync_status" in str(exc_info.value)

    def test_falla_por_google_id_local(self, db):
        ev = _make_event(event_id="conv004", google_event_id="local_abc123")
        db.guardar_evento_individual(ev)

        with pytest.raises(AssertionError) as exc_info:
            assert_event_converged(
                db, "conv004",
                build_expected(google_event_id_not_local=True)
            )
        assert "google_event_id" in str(exc_info.value)

    def test_falla_por_ots_incorrectas(self, db):
        ev = _make_event(event_id="conv005", app_ots=["8775"], google_event_id="gev_ok")
        db.guardar_evento_individual(ev)

        with pytest.raises(AssertionError) as exc_info:
            assert_event_converged(
                db, "conv005",
                build_expected(app_ots=["9999"])  # OT incorrecta
            )
        assert "app_ots" in str(exc_info.value)

    def test_evento_inexistente(self, db):
        with pytest.raises(AssertionError) as exc_info:
            assert_event_converged(db, "no_existe", build_expected())
        assert "no encontrado" in str(exc_info.value)


# ─── DRIFT REPORT ─────────────────────────────────────────────────────────────

class TestDriftReport:
    """Verifica que el drift report detecta correctamente los indicadores."""

    def test_drift_report_sin_problemas(self, db):
        from sync_observatory import SyncObservatoryService
        obs = SyncObservatoryService(db)
        report = obs.get_full_drift_report()

        assert "summary" in report
        assert "indicators" in report
        assert "timestamp" in report
        # Sin eventos, todo debe estar en 0
        assert report["indicators"]["events_without_google_id"]["count"] == 0
        assert report["indicators"]["duplicate_events"]["count"] == 0
        assert report["summary"]["total_issues"] == 0
        assert report["summary"]["has_drift"] is False

    def test_drift_report_detecta_sin_google_id(self, db):
        from sync_observatory import SyncObservatoryService
        obs = SyncObservatoryService(db)

        # Insertar evento sin google_event_id real
        ev = _make_event(
            event_id="drift001",
            google_event_id="local_drift001",
            sync_status="PENDING",
        )
        db.guardar_evento_individual(ev)

        report = obs.get_full_drift_report()
        assert report["indicators"]["events_without_google_id"]["count"] >= 1

    def test_drift_report_detecta_sync_failures(self, db):
        from sync_observatory import SyncObservatoryService
        obs = SyncObservatoryService(db)

        # Insertar item FAILED en sync_queue
        with db._get_connection() as conn:
            conn.execute("""
                INSERT INTO sync_queue
                    (queue_id, event_id, calendar_id, tecnico, operation, created_at, status, error_msg)
                VALUES (?, ?, ?, ?, ?, ?, 'FAILED', ?)
            """, (
                str(uuid.uuid4()), "fail_ev001", "test@akrimet.com",
                "Nicolás", "UPDATE", "2026-05-23T10:00:00", "Connection error"
            ))
            conn.commit()

        report = obs.get_full_drift_report()
        assert report["indicators"]["sync_failures"]["count"] >= 1
        assert report["summary"]["has_drift"] is True

    def test_drift_report_estructura_completa(self, db):
        from sync_observatory import SyncObservatoryService
        obs = SyncObservatoryService(db)
        report = obs.get_full_drift_report()

        expected_keys = [
            "events_without_google_id", "duplicate_events", "pending_reviews",
            "reopened_reviews", "cancelled_visible", "sync_failures",
            "polling_lag", "orphan_events", "lookup_misses_24h"
        ]
        for key in expected_keys:
            assert key in report["indicators"], f"Falta indicador: {key}"


# ─── LOOKUP MISS TAG ──────────────────────────────────────────────────────────

class TestLookupMissLog:
    """Verifica que el tag LOOKUP_MISS se emite cuando rows_affected=0."""

    def test_lookup_miss_logueado_cuando_evento_no_existe(self, db):
        """actualizar_evento_individual con ID inexistente debe loguear LOOKUP_MISS."""
        result = db.actualizar_evento_individual(
            "evento_que_no_existe",
            "test@akrimet.com",
            {"summary": "Test"},
            origin="test_lookup_miss"
        )
        # Debe retornar None (no encontró la fila)
        assert result is None

        # Verificar que se logueó LOOKUP_MISS
        logs = db.get_poll_logs(limit=50, event_type="LOOKUP_MISS")
        assert len(logs) > 0, "Debe haber al menos un log con tag LOOKUP_MISS"
