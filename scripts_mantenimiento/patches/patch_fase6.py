# coding=utf-8
"""
FASE 6 - Patch script para api_server.py
Aplica 3 correcciones quirurgicas al grupo lifecycle:
  Bug 1: Reasignacion de tecnico mantiene al miembro en el grupo
  Bug 2: Lookup robusto via db.resolve_event en mover_grupo
  Bonus: Guard para nueva_fecha=None en mover_grupo
"""

with open("api_server.py", "r", encoding="utf-8") as f:
    code = f.read()

changes = 0

# ===========================================================================
# BUG 1 FIX — mover_evento, seccion "Gestion de grupo post-movimiento"
# Cuando hay cambio_tecnico: MANTENER al miembro en el grupo, actualizar
# tecnico_nombres y recalcular titulos de todos los miembros.
# ===========================================================================
BUG1_TARGET = """            if cambio_tecnico:
                # Técnico movido a otro calendario: quitar del grupo y reformular
                remaining_ids = [eid for eid in grupo['event_ids'] if eid != event_id]

                if len(remaining_ids) <= 1:
                    # Disolver grupo
                    db.eliminar_grupo(grupo['grupo_id'])
                    # Limpiar título del último evento restante
                    if remaining_ids:
                        last_ev = db.resolve_event(remaining_ids[0])
                        if last_ev:
                            ot_limpia = utils.get_ot_base_from_event(last_ev)
                            db.actualizar_evento_individual(
                                remaining_ids[0], last_ev['calendar_id'],
                                {"evento": ot_limpia},
                                sync_status='PENDING', pending_sync=1, origin='group_dissolve'
                            )
                            gid_last = last_ev.get('google_event_id') or remaining_ids[0]
                            db.enqueue_sync(gid_last, last_ev['calendar_id'], last_ev['tecnico_nombre'], "UPDATE")
                            db.log_trace(remaining_ids[0], "mutation_created", {
                                "type": "UPDATE", "origin": "group_dissolve_title", "nuevo_titulo": ot_limpia
                            }, calendar_id=last_ev['calendar_id'], tag="OUTBOUND_MUTATION")
                else:
                    # Reformular títulos de los restantes
                    all_tecnicos = db.obtener_tecnicos()
                    ini_map = {t['nombre']: t.get('iniciales', '') for t in all_tecnicos}
                    remaining_tec_nombres = [
                        grupo['tecnico_nombres'][grupo['event_ids'].index(eid)]
                        for eid in remaining_ids
                        if eid in grupo['event_ids']
                    ]
                    first_remaining = db.resolve_event(remaining_ids[0])
                    ot_base = utils.get_ot_base_from_event(first_remaining) if first_remaining else ""
                    nuevo_titulo_grupo = utils.format_group_summary(
                        ot_base, [ini_map.get(n, '') for n in remaining_tec_nombres]
                    )
                    for rid in remaining_ids:
                        rev = db.resolve_event(rid)
                        if not rev:
                            continue
                        db.actualizar_evento_individual(
                            rid, rev['calendar_id'],
                            {"evento": nuevo_titulo_grupo},
                            sync_status='PENDING', pending_sync=1, origin='group_dissolve'
                        )
                        gid_r = rev.get('google_event_id') or rid
                        db.enqueue_sync(gid_r, rev['calendar_id'], rev['tecnico_nombre'], "UPDATE")
                        db.log_trace(rid, "mutation_created", {
                            "type": "UPDATE", "origin": "group_dissolve_title", "nuevo_titulo": nuevo_titulo_grupo
                        }, calendar_id=rev['calendar_id'], tag="OUTBOUND_MUTATION")

                    db.crear_o_actualizar_grupo({
                        **grupo,
                        "event_ids": remaining_ids,
                        "tecnico_nombres": remaining_tec_nombres
                    })"""

BUG1_REPLACEMENT = """            if cambio_tecnico:
                # [FASE 6 - BUG 1 FIX] Tecnico movido a otro calendario: MANTENER en el grupo.
                # Se actualiza tecnico_nombres del miembro y se recalculan los titulos de todos.
                all_tecnicos = db.obtener_tecnicos()
                ini_map = {t['nombre']: t.get('iniciales', '') for t in all_tecnicos}

                new_tec_nombres = []
                for rid in grupo['event_ids']:
                    rid_resolved = db.resolve_event(rid)
                    if rid == event_id or (rid_resolved and rid_resolved.get('google_event_id') == event_id):
                        new_tec_nombres.append(tec_nombre)
                    else:
                        if rid_resolved:
                            new_tec_nombres.append(
                                rid_resolved.get("tecnico_nombre") or rid_resolved.get("tecnico") or ""
                            )
                        else:
                            new_tec_nombres.append("")

                ot_base = utils.get_ot_base_from_event(ev_actual_db)
                nuevo_titulo_grupo = utils.format_group_summary(
                    ot_base,
                    [ini_map.get(n, '') for n in new_tec_nombres],
                )

                for rid in grupo['event_ids']:
                    rev = db.resolve_event(rid)
                    if not rev:
                        continue
                    is_reasigned_member = (rid == event_id or rev.get('google_event_id') == event_id)
                    db.actualizar_evento_individual(
                        rid,
                        target_cal if is_reasigned_member else rev['calendar_id'],
                        {"evento": nuevo_titulo_grupo},
                        sync_status=sync_status_val if is_reasigned_member else 'PENDING',
                        pending_sync=1,
                        origin='group_reassign_rename'
                    )
                    if not is_reasigned_member:
                        gid_r = rev.get('google_event_id') or rid
                        db.enqueue_sync(gid_r, rev['calendar_id'], rev['tecnico_nombre'], "UPDATE")
                        db.log_trace(rid, "mutation_created", {
                            "type": "UPDATE", "origin": "group_reassign_title",
                            "nuevo_titulo": nuevo_titulo_grupo
                        }, calendar_id=rev['calendar_id'], tag="OUTBOUND_MUTATION")

                db.crear_o_actualizar_grupo({
                    **grupo,
                    "tecnico_nombres": new_tec_nombres
                })"""

if BUG1_TARGET in code:
    code = code.replace(BUG1_TARGET, BUG1_REPLACEMENT, 1)
    changes += 1
    print("✅ Bug 1 aplicado: reasignacion mantiene miembro en grupo")
else:
    print("❌ Bug 1 NO encontrado — verificar target manualmente")

# ===========================================================================
# BUG 2 FIX — mover_grupo, reemplazar dict estatico por db.resolve_event
# Ademas agregar guard para nueva_fecha=None
# ===========================================================================
BUG2_TARGET = """        eventos_db = db.obtener_eventos_dict()
        map_id_evento = {e["id"]: e for e in eventos_db}
        
        tecs_db = db.obtener_tecnicos()
        map_nombre_correo = {t['nombre']: t['correo'] for t in tecs_db}
        map_correo_nombre = {t['correo']: t['nombre'] for t in tecs_db}

        nueva_f = datetime.date.fromisoformat(params.nueva_fecha)
        tz_suffix = "-03:00"

        for i, eid in enumerate(grupo['event_ids']):
            ev_actual_db = map_id_evento.get(eid)
            if not ev_actual_db:
                continue"""

BUG2_REPLACEMENT = """        tecs_db = db.obtener_tecnicos()
        map_nombre_correo = {t['nombre']: t['correo'] for t in tecs_db}
        map_correo_nombre = {t['correo']: t['nombre'] for t in tecs_db}

        # [FASE 6 - BUG 2 FIX] Guard para nueva_fecha=None (puede ocurrir con solo cambio de tecnico)
        if not params.nueva_fecha:
            # Usar la fecha actual del evento lider para no crashear fromisoformat
            params.nueva_fecha = ev_interno.get("inicio", "")[:10]

        nueva_f = datetime.date.fromisoformat(params.nueva_fecha)
        tz_suffix = "-03:00"

        # [FASE 6 - BUG 2 FIX] Usar db.resolve_event en lugar de dict estatico para tolerar
        # discrepancias entre google_event_id e id local en event_ids del grupo.
        for i, eid in enumerate(grupo['event_ids']):
            ev_actual_db = db.resolve_event(eid)
            if not ev_actual_db:
                print(f"[WARN] mover_grupo: no se pudo resolver eid={eid} — saltando")
                continue"""

if BUG2_TARGET in code:
    code = code.replace(BUG2_TARGET, BUG2_REPLACEMENT, 1)
    changes += 1
    print("✅ Bug 2 aplicado: lookup robusto con resolve_event + guard nueva_fecha")
else:
    print("❌ Bug 2 NO encontrado — verificar target manualmente")

# ===========================================================================
# Guardar si hubo cambios
# ===========================================================================
if changes > 0:
    with open("api_server.py", "w", encoding="utf-8") as f:
        f.write(code)
    print(f"\n✅ api_server.py actualizado ({changes} cambios aplicados)")
else:
    print("\n⚠️ No se aplicó ningún cambio")
