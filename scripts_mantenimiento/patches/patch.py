import re
content = open('poll_manager.py', 'r', encoding='utf-8').read()

content = content.replace(
    'local = self.db.find_by_google_event_id(gid)',
    'local = self.db.find_by_google_event_id(gid, calendar_id)'
)

strategy4 = '''    # Estrategia 4: Búsqueda de hermanos implícitos por google_event_id
    if not grupo:
        local = db.find_by_google_event_id(event_id) or db.get_evento_dict(event_id)
        if local:
            gid = local.get("google_event_id")
            if gid:
                with db._get_connection() as conn:
                    rows = conn.execute("SELECT id FROM eventos WHERE google_event_id = ?", (gid,)).fetchall()
                if len(rows) > 1:
                    event_ids = [r[0] for r in rows]
                    grupo_id = f"impl_{gid}"
                    return {
                        "is_grouped": True,
                        "group_id": grupo_id,
                        "member_count": len(event_ids),
                        "member_event_ids": event_ids
                    }

    if not grupo:
        return {"is_grouped": False, "group_id": None,'''

content = content.replace('    if not grupo:\n        return {"is_grouped": False, "group_id": None,', strategy4)

handle_cancelled_new = '''        local = self.db.find_by_google_event_id(event_id, calendar_id)
        if local:
            # Capturar snapshot local antes de encolar
            local_snapshot = {
                "summary": local.get("summary"),
                "tecnico": local.get("tecnico_nombre"),
                "inicio": local.get("inicio"),
                "fin": local.get("fin"),
                "extended_props": local.get("extended_props"),
            }
            # [WATERMARK_ANTI_REOPEN] Para REMOTE_DELETE, el g_ev viene del ciclo de polling
            # Los eventos cancelados pueden tener un campo 'updated' que usamos como watermark
            g_updated = g_ev.get("updated") if g_ev else None
            review_id = self.db.enqueue_review(
                event_id=local["id"],
                calendar_id=calendar_id,
                diff={"_action": {"old": "EXISTS", "new": "DELETE", "category": "critical"}},
                conflict_type="REMOTE_DELETE",
                google_event_id=event_id,
                local_snapshot=local_snapshot,
                remote_snapshot={"status": "cancelled"},
                recommended_action="REVIEW_DELETE",
                g_updated=g_updated,
            )
            
            # Auto-arbitraje de reasignaciones (Case 1)
            with self.db._get_connection() as conn:
                active_siblings = conn.execute(
                    "SELECT id FROM eventos WHERE google_event_id = ? AND calendar_id != ? AND sync_status != 'CANCELLED_IN_GOOGLE'", 
                    (event_id, calendar_id)
                ).fetchall()
                
            if len(active_siblings) > 0:
                self.db.accept_review(review_id)
                _poll_log(self.db, "POLL_INBOUND_TRACE", "AUTO_ARBITRATED_DELETE", {"event_id": local["id"], "reason": "sibling_exists"})
                
            _poll_log(self.db, "POLL_INBOUND_TRACE", "DELETE_DETECTED",
                      {
                          "cycle_id": self._current_cycle_id,
                          "google_event_id": event_id,
                          "local_id": local["id"],
                          "review_id": review_id,
                          "decision": "delete_detected",
                          "persistence": "review_queued",
                          "note": "Cancelado en Google — pendiente de arbitraje humano"
                      },
                      calendar_id=calendar_id, event_id=event_id)
        else:'''

handle_cancelled_old = '''        local = self.db.find_by_google_event_id(event_id)
        if local:
            # Capturar snapshot local antes de encolar
            local_snapshot = {
                "summary": local.get("summary"),
                "tecnico": local.get("tecnico_nombre"),
                "inicio": local.get("inicio"),
                "fin": local.get("fin"),
                "extended_props": local.get("extended_props"),
            }
            # [WATERMARK_ANTI_REOPEN] Para REMOTE_DELETE, el g_ev viene del ciclo de polling
            # Los eventos cancelados pueden tener un campo 'updated' que usamos como watermark
            g_updated = g_ev.get("updated") if g_ev else None
            review_id = self.db.enqueue_review(
                event_id=local["id"],
                calendar_id=calendar_id,
                diff={"_action": {"old": "EXISTS", "new": "DELETE", "category": "critical"}},
                conflict_type="REMOTE_DELETE",
                google_event_id=event_id,
                local_snapshot=local_snapshot,
                remote_snapshot={"status": "cancelled"},
                recommended_action="REVIEW_DELETE",
                g_updated=g_updated,
            )
            _poll_log(self.db, "POLL_INBOUND_TRACE", "DELETE_DETECTED",
                      {
                          "cycle_id": self._current_cycle_id,
                          "google_event_id": event_id,
                          "local_id": local["id"],
                          "review_id": review_id,
                          "decision": "delete_detected",
                          "persistence": "review_queued",
                          "note": "Cancelado en Google — pendiente de arbitraje humano"
                      },
                      calendar_id=calendar_id, event_id=event_id)
        else:'''

content = content.replace(handle_cancelled_old, handle_cancelled_new)

open('poll_manager.py', 'w', encoding='utf-8').write(content)
print('Done!')
