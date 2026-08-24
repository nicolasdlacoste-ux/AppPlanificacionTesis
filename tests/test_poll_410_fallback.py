import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import unittest
from unittest.mock import MagicMock
import poll_manager
from data_manager import DataManager

class MockHttpError(Exception):
    def __init__(self, status_code, message):
        self.status_code = status_code
        self.resp = type('Resp', (), {'status': status_code})()
        super().__init__(message)

def test_poll_410_fallback():
    # Mock de DB
    db_mock = MagicMock(spec=DataManager)
    db_mock.get_last_poll_time.return_value = "2026-06-25T01:22:50.872513Z"
    
    # Mock de Google Calendar Service
    svc_mock = MagicMock()
    events_mock = MagicMock()
    
    calls = []
    def mock_list(**kwargs):
        calls.append(dict(kwargs))
        m_exec = MagicMock()
        if "updatedMin" in kwargs:
            m_exec.execute.side_effect = MockHttpError(410, "<HttpError 410 when requesting ... updatedMinTooLongAgo>")
        else:
            m_exec.execute.return_value = {"items": [{"id": "g_123", "status": "confirmed"}]}
        return m_exec

    events_mock.list.side_effect = mock_list
    svc_mock.events.return_value = events_mock
    
    pm = poll_manager.PollingManager(db=db_mock, google_service_factory=lambda: svc_mock)
    
    stats = pm._poll_calendar("test@akrimet.com", "Test Tech")
    
    # Verificaciones
    print("CALLS:", calls)
    assert len(calls) == 2, f"Se esperaban 2 llamadas, hubo {len(calls)}"
    assert "updatedMin" in calls[0], "La primera llamada debía contener updatedMin"
    assert "updatedMin" not in calls[1], "La segunda llamada (fallback) NO debía contener updatedMin"
    assert stats["processed"] == 1
    print("SUCCESS: Test de auto-recuperación ante Error 410 pasó correctamente.")

if __name__ == "__main__":
    test_poll_410_fallback()
