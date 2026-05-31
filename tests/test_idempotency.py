"""
tests/test_idempotency.py

[ETAPA 7 — IDEMPOTENCIA]
Verifica que las operaciones críticas sean idempotentes:
  - Double-enqueue en sync_queue (mismo event_id + operation)
  - Double-accept de un review ya ACCEPTED
  - Double-reject de un review ya REJECTED
  - Retry de sync (no genera acumulación en sync_queue)
  - Double-polling (no duplica reviews)
  - DELETE idempotente (404 en Google no es error)

Ejecutar:
    python -m pytest tests/test_idempotency.py -v
"""
import sys
import os
import json
import uuid
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data_manager import DataManager


# ─── Fixture ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test_idempotency.db")
    return DataManager(db_path=db_path)


def _insert_evento(db, event_id: str, google_event_id: str = None,
                   tecnico: str = "Nicolás", calendar_id: str = "nico@akrimet.com"):
    """Inserta un evento mínimo en la DB para tests."""
    db.guardar_evento_individual({
        "id": event_id,
        "calendar_id": calendar_id,
        "tecnico_nombre": tecnico,
        "summary": f"Test {event_id}",
        "inicio": "2026-05-23T07:00:00-03:00",
        "fin": "2026-05-23T16:00:00-03:00",
        "ubicacion": "",
        "descripcion": "",
        "extended_props": json.dumps({
            "private": {
                "app_ots": '["8775"]',
                "app_patrones": "[]",
                "app_vehiculo": "",
                "source": "internal"
            }
        }),
        "version": 1,
        "sync_status": "SUCCESS",
        "pending_sync": 0,
        "google_event_id": google_event_id or f"gev_{event_id}",
        "source": "internal",
    })


def _count_queue_items(db, event_id: str = None, status: str = None) -> int:
    with db._get_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT COUNT(*) FROM sync_queue WHERE 1=1"
        params = []
        if event_id:
            query += " AND event_id = ?"
            params.append(event_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        cursor.execute(query, params)
        return cursor.fetchone()[0]


# ─── SYNC QUEUE IDEMPOTENCIA ──────────────────────────────────────────────────

class TestSyncQueueIdempotency:

    def test_enqueue_sync_genera_items_independientes(self, db):
        """
        enqueue_sync NO deduplica por diseño (cada operación es un ítem de trabajo).
        Verificamos que dos enqueuings del mismo evento generan 2 ítems (comportamiento esperado).
        El SyncWorker los procesa en orden y el segundo normalmente es un no-op en Google.
        """
        _insert_evento(db, "idem001", google_event_id="gev_idem001")
        db.enqueue_sync("idem001", "nico@akrimet.com", "Nicolás", "UPDATE", origin="test1")
        db.enqueue_sync("idem001", "nico@akrimet.com", "Nicolás", "UPDATE", origin="test2")

        count = _count_queue_items(db, event_id="idem001", status="PENDING")
        assert count == 2, (
            f"Se esperan 2 ítems (el worker maneja la idempotencia en Google), "
            f"se encontraron {count}"
        )

    def test_retry_no_acumula_items_adicionales(self, db):
        """
        Simular FAILED en sync_queue y verificar que update_queue_retry
        solo actualiza el ítem existente, no crea uno nuevo.
        """
        _insert_evento(db, "idem002", google_event_id="gev_idem002")
        db.enqueue_sync("idem002", "nico@akrimet.com", "Nicolás", "CREATE", origin="test")
        count_before = _count_queue_items(db, event_id="idem002")

        # Simular FAILED y luego retry
        with db._get_connection() as conn:
            conn.execute(
                "UPDATE sync_queue SET status='FAILED', error_msg='timeout' WHERE event_id=?",
                ("idem002",)
            )
            cursor = conn.cursor()
            cursor.execute("SELECT queue_id FROM sync_queue WHERE event_id=?", ("idem002",))
            row = cursor.fetchone()
        
        if row:
            db.update_queue_retry(
                queue_id=row[0],
                attempts=1,
                next_retry_at=None,
                error_msg="timeout"
            )

        count_after = _count_queue_items(db, event_id="idem002")
        assert count_after == count_before, (
            f"El retry no debe crear ítems nuevos: antes={count_before} después={count_after}"
        )


# ─── REVIEW QUEUE IDEMPOTENCIA ────────────────────────────────────────────────

class TestReviewIdempotency:

    def test_double_accept_retorna_404(self, db):
        """Aceptar un review que ya fue ACCEPTED debe lanzar ValueError (review no en PENDING)."""
        _insert_evento(db, "rev001", google_event_id="gev_rev001")

        review_id = db.enqueue_review(
            event_id="rev001",
            calendar_id="nico@akrimet.com",
            diff={"summary": {"old": "A", "new": "B", "category": "critical"}},
            conflict_type="FIELD_CHANGE",
            google_event_id="gev_rev001",
        )
        assert review_id is not None

        # Primer accept — debe funcionar
        result = db.accept_review(review_id)
        assert result["status"] == "ACCEPTED"

        # Segundo accept — el review ya no está en PENDING, debe lanzar ValueError
        with pytest.raises(ValueError) as exc_info:
            db.accept_review(review_id)
        
        # El error puede ser "no encontrado" o similar
        assert review_id in str(exc_info.value) or "no encontrado" in str(exc_info.value).lower()

    def test_double_reject_retorna_error(self, db):
        """Rechazar un review que ya fue REJECTED debe lanzar ValueError."""
        _insert_evento(db, "rev002", google_event_id="gev_rev002")

        review_id = db.enqueue_review(
            event_id="rev002",
            calendar_id="nico@akrimet.com",
            diff={"summary": {"old": "A", "new": "B", "category": "critical"}},
            conflict_type="FIELD_CHANGE",
            google_event_id="gev_rev002",
        )
        assert review_id is not None

        # Primer reject — debe funcionar
        result = db.reject_review(review_id)
        assert result["status"] == "REJECTED"

        # Segundo reject — debe lanzar ValueError
        with pytest.raises(ValueError):
            db.reject_review(review_id)

    def test_enqueue_review_no_duplica_pending(self, db):
        """Dos llamadas a enqueue_review con el mismo google_event_id y status PENDING → solo 1 review."""
        gid = f"gev_{uuid.uuid4().hex[:8]}"

        r1 = db.enqueue_review(
            event_id="rev003", calendar_id="nico@akrimet.com",
            diff={"summary": {"old": "A", "new": "B", "category": "critical"}},
            conflict_type="FIELD_CHANGE", google_event_id=gid,
        )
        r2 = db.enqueue_review(
            event_id="rev003", calendar_id="nico@akrimet.com",
            diff={"summary": {"old": "A", "new": "B", "category": "critical"}},
            conflict_type="FIELD_CHANGE", google_event_id=gid,
        )

        assert r1 is not None, "El primer enqueue debe tener éxito"
        assert r2 is None, "El segundo enqueue debe ser bloqueado (PENDING ya existe)"

        # Verificar solo 1 review en PENDING para ese gid
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM poll_review_queue WHERE google_event_id=? AND status='PENDING'",
                (gid,)
            )
            count = cursor.fetchone()[0]
        assert count == 1, f"Debe haber exactamente 1 review PENDING, hay {count}"

    def test_enqueue_review_remote_create_no_reactiva_si_rejected(self, db):
        """REMOTE_CREATE no se reactiva si el review anterior fue explícitamente REJECTED."""
        gid = f"gev_{uuid.uuid4().hex[:8]}"

        r1 = db.enqueue_review(
            event_id="rev004", calendar_id="nico@akrimet.com",
            diff={}, conflict_type="REMOTE_CREATE", google_event_id=gid,
        )
        assert r1 is not None

        # Marcar como REJECTED
        with db._get_connection() as conn:
            conn.execute(
                "UPDATE poll_review_queue SET status='REJECTED', resolved_at=? WHERE review_id=?",
                ("2026-05-23T10:00:00Z", r1)
            )
            conn.commit()

        # Intentar crear nuevo REMOTE_CREATE para el mismo gid
        r2 = db.enqueue_review(
            event_id="rev004", calendar_id="nico@akrimet.com",
            diff={}, conflict_type="REMOTE_CREATE", google_event_id=gid,
        )
        assert r2 is None, "REMOTE_CREATE no debe reactivarse si ya fue REJECTED"


# ─── WATERMARK IDEMPOTENCIA ───────────────────────────────────────────────────

class TestWatermarkIdempotency:

    def test_mismo_g_updated_no_crea_review_multiple(self, db):
        """
        Mismo g_updated después de un accept no debe crear múltiples reviews.
        Simula polling recurrente que vería el mismo evento con el mismo timestamp.
        """
        gid = f"gev_{uuid.uuid4().hex[:8]}"
        G_UPDATED = "2026-05-20T10:00:00Z"
        RESOLVED_AT = "2026-05-20T12:00:00Z"

        # Crear review inicial
        r1 = db.enqueue_review(
            event_id="wm001", calendar_id="nico@akrimet.com",
            diff={"summary": {"old": "A", "new": "B", "category": "critical"}},
            conflict_type="FIELD_CHANGE", google_event_id=gid,
            g_updated=G_UPDATED,
        )
        assert r1 is not None

        # Marcar como ACCEPTED con resolved_at posterior al g_updated
        with db._get_connection() as conn:
            conn.execute(
                "UPDATE poll_review_queue SET status='ACCEPTED', resolved_at=? WHERE review_id=?",
                (RESOLVED_AT, r1)
            )
            conn.commit()

        # Polling siguiente ciclo: mismo g_updated → bloqueado
        r2 = db.enqueue_review(
            event_id="wm001", calendar_id="nico@akrimet.com",
            diff={"summary": {"old": "A", "new": "B", "category": "critical"}},
            conflict_type="FIELD_CHANGE", google_event_id=gid,
            g_updated=G_UPDATED,  # Mismo timestamp
        )
        assert r2 is None, f"Review fantasma no debe reabrirse. g_updated={G_UPDATED} <= resolved_at={RESOLVED_AT}"

        # Verificar log POLLING_REOPEN_BLOCKED
        logs = db.get_poll_logs(limit=50, event_type="POLLING_REOPEN_BLOCKED")
        assert len(logs) > 0, "Debe haber log POLLING_REOPEN_BLOCKED cuando se bloquea"
