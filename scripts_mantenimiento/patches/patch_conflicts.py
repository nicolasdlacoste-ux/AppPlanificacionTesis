import re

app_js = open('webapp/app.js', encoding='utf-8').read()

old_vehicle = '''    function checkVehicleConflicts(vehiculoNombre, dateStr, sh, eh, evId, techNombre, grupoId = null) {
        if (!vehiculoNombre) return null;
        
        const veh = _vehiculos.find(v => v.nombre === vehiculoNombre);
        if (!veh) return null;
        
        const techInfo = _tecnicos.find(t => t.nombre === techNombre);
        const techCorreo = techInfo ? techInfo.correo : null;
        
        // Si no se pasó grupoId explícitamente, intentar obtenerlo del evento actual
        if (!grupoId && evId) {
            const evTarget = _eventos.find(e => e.google_event_id === evId && e.calendar_id === techCorreo);
            if (evTarget && evTarget.extended_props && evTarget.extended_props.private) {
                grupoId = evTarget.extended_props.private.grupo_id;
            }
        }

        // Formatear dateStr si es Date
        const getStr = d => {
            if (typeof d === 'string') return d.substring(0, 10);
            return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
        };
        const targetDate = getStr(dateStr);
        
        // Todos los eventos del mismo día (excluyendo el propio)
        const sameDayEvents = _eventos.filter(ev => {
            if (ev.google_event_id === evId) return false;
            const props = (ev.extended_props && ev.extended_props.private) || {};
            if (props.app_vehiculo !== vehiculoNombre) return false;
            const evSh = ev.inicio || "";
            const evEh = ev.fin || "";
            if (!evSh || !evEh) return false;
            return getStr(evSh) <= targetDate && getStr(evEh) >= targetDate;
        });

        // Regla NUEVA: Verificar si EL TÉCNICO tiene asignado OTRO vehículo este día
        const techEventsToday = _eventos.filter(ev => {
            if (ev.google_event_id === evId) return false;
            // [CANONICAL_MIGRATION] match by calendar_id (fallback to nombre)
            const matchesTech = (ev.calendar_id && ev.calendar_id === techCorreo) || (!ev.calendar_id && ev.tecnico_nombre === techNombre);
            if (!matchesTech) return false;
            const evSh = ev.inicio || "";
            const evEh = ev.fin || "";
            if (!evSh || !evEh) return false;
            return getStr(evSh) <= targetDate && getStr(evEh) >= targetDate;
        });
        
        for (const e of techEventsToday) {
            const eProps = (e.extended_props && e.extended_props.private) || {};
            const eVeh = eProps.app_vehiculo;
            if (eVeh && eVeh !== vehiculoNombre) {
                return `El técnico ${techNombre} ya tiene asignado el vehículo '${eVeh}' hoy. No puede usar '${vehiculoNombre}'.`;
            }
        }
        
        // Regla Capacidad: contar técnicos únicos usando el vehículo ese día.
        // IMPORTANTE: los miembros del mismo grupo SÍ cuentan como ocupantes del vehículo
        // (comparten el vehículo yendo al mismo trabajo, pero siguen ocupando asientos).
        const uniqueTechs = new Set();
        uniqueTechs.add(techCorreo || techNombre);
        sameDayEvents.forEach(e => {
            if (e.calendar_id || e.tecnico_nombre) uniqueTechs.add(e.calendar_id || e.tecnico_nombre);
        });
        
        if (uniqueTechs.size > veh.asientos) {
            // No bloqueamos ➔ solo advertimos (badge de conflicto en UI)
            return `Capacidad excedida: '${vehiculoNombre}' tiene ${veh.asientos} asiento(s), pero lo usarían ${uniqueTechs.size} técnicos: ${Array.from(uniqueTechs).join(', ')}`;
        }
        
        // Regla Solapamiento: mismos horarios, distinto trabajo (excluir mismo grupo)
        for (const ev of sameDayEvents) {
            // Si pertenecen al mismo grupo ➔ no es conflicto (mismo trabajo, mismo vehículo)
            if (grupoId) {
                const eProps = (ev.extended_props && ev.extended_props.private) || {};
                if (eProps.grupo_id === grupoId) continue;
            }
            
            const getHour = str => {
                if (str.includes('T')) {
                    const match = str.match(/T(\d+):(\d+)/);
                    if (match) return parseInt(match[1]) + parseInt(match[2])/60;
                } else if (str.includes(' ')) {
                    const match = str.split(' ')[1].split(':');
                    if (match) return parseInt(match[0]) + parseInt(match[1])/60;
                }
                return 12;
            };
            
            const evS_time = getHour(ev.inicio);
            const evE_time = getHour(ev.fin);
            
            if (Math.max(sh, evS_time) < Math.min(eh, evE_time)) {
                return `El vehículo '${vehiculoNombre}' ya está asignado a otro trabajo ("${ev.summary}") en ese horario.`;
            }
        }
        
        return null; // OK
    }'''

new_vehicle = '''    function checkVehicleConflicts(vehiculoNombre, dateStr, sh, eh, evId, techNombre, grupoId = null, dateEndStr = null) {
        if (!vehiculoNombre) return null;
        
        const veh = _vehiculos.find(v => v.nombre === vehiculoNombre);
        if (!veh) return null;
        
        const techInfo = _tecnicos.find(t => t.nombre === techNombre);
        const techCorreo = techInfo ? techInfo.correo : null;
        
        if (!grupoId && evId) {
            const evTarget = _eventos.find(e => e.google_event_id === evId && e.calendar_id === techCorreo);
            if (evTarget && evTarget.extended_props && evTarget.extended_props.private) {
                grupoId = evTarget.extended_props.private.grupo_id;
            }
        }

        const getStr = d => {
            if (typeof d === 'string') return d.substring(0, 10);
            return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
        };
        const targetDate = getStr(dateStr);
        let targetEndDate = dateEndStr ? getStr(dateEndStr) : targetDate;
        if (targetEndDate < targetDate) targetEndDate = targetDate;
        
        let curr = new Date(targetDate + "T12:00:00");
        const end = new Date(targetEndDate + "T12:00:00");
        
        while (curr <= end) {
            const currDateStr = getStr(curr);
            const conflict = _checkVehicleOnDay(vehiculoNombre, currDateStr, sh, eh, evId, techNombre, techCorreo, grupoId, veh);
            if (conflict) {
                return (targetDate !== targetEndDate ? `[${currDateStr}] ` : '') + conflict;
            }
            curr.setDate(curr.getDate() + 1);
        }
        return null;
    }

    function _checkVehicleOnDay(vehiculoNombre, targetDate, sh, eh, evId, techNombre, techCorreo, grupoId, veh) {
        const sameDayEvents = _eventos.filter(ev => {
            if (ev.google_event_id === evId) return false;
            const props = (ev.extended_props && ev.extended_props.private) || {};
            if (props.app_vehiculo !== vehiculoNombre) return false;
            const evSh = ev.inicio || "";
            const evEh = ev.fin || "";
            if (!evSh || !evEh) return false;
            return getStr(evSh) <= targetDate && getStr(evEh) >= targetDate;
        });

        const techEventsToday = _eventos.filter(ev => {
            if (ev.google_event_id === evId) return false;
            const matchesTech = (ev.calendar_id && ev.calendar_id === techCorreo) || (!ev.calendar_id && ev.tecnico_nombre === techNombre);
            if (!matchesTech) return false;
            const evSh = ev.inicio || "";
            const evEh = ev.fin || "";
            if (!evSh || !evEh) return false;
            return getStr(evSh) <= targetDate && getStr(evEh) >= targetDate;
        });
        
        for (const e of techEventsToday) {
            const eProps = (e.extended_props && e.extended_props.private) || {};
            const eVeh = eProps.app_vehiculo;
            if (eVeh && eVeh !== vehiculoNombre) {
                return `El técnico ${techNombre} ya tiene asignado el vehículo '${eVeh}'. No puede usar '${vehiculoNombre}'.`;
            }
        }
        
        const uniqueTechs = new Set();
        uniqueTechs.add(techCorreo || techNombre);
        sameDayEvents.forEach(e => {
            if (e.calendar_id || e.tecnico_nombre) uniqueTechs.add(e.calendar_id || e.tecnico_nombre);
        });
        
        if (uniqueTechs.size > veh.asientos) {
            return `Capacidad excedida: '${vehiculoNombre}' tiene ${veh.asientos} asiento(s), pero lo usarían ${uniqueTechs.size} técnicos: ${Array.from(uniqueTechs).join(', ')}`;
        }
        
        for (const ev of sameDayEvents) {
            if (grupoId) {
                const eProps = (ev.extended_props && ev.extended_props.private) || {};
                if (eProps.grupo_id === grupoId) continue;
            }
            
            const getHour = str => {
                if (str.includes('T')) {
                    const match = str.match(/T(\\d+):(\\d+)/);
                    if (match) return parseInt(match[1]) + parseInt(match[2])/60;
                } else if (str.includes(' ')) {
                    const match = str.split(' ')[1].split(':');
                    if (match) return parseInt(match[0]) + parseInt(match[1])/60;
                }
                return 12;
            };
            
            const evS_time = getHour(ev.inicio);
            const evE_time = getHour(ev.fin);
            
            if (Math.max(sh, evS_time) < Math.min(eh, evE_time)) {
                return `El vehículo '${vehiculoNombre}' ya está asignado a otro trabajo ("${ev.summary}") en ese horario.`;
            }
        }
        
        return null;
    }

    const getStr = d => {
        if (typeof d === 'string') return d.substring(0, 10);
        return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
    };

    function checkPatternConflicts(patronesArr, dateStr, dateEndStr, evId, proposedOTs) {
        if (!patronesArr || patronesArr.length === 0) return null;
        
        const targetDate = getStr(dateStr);
        let targetEndDate = dateEndStr ? getStr(dateEndStr) : targetDate;
        if (targetEndDate < targetDate) targetEndDate = targetDate;
        
        let curr = new Date(targetDate + "T12:00:00");
        const end = new Date(targetEndDate + "T12:00:00");
        
        while (curr <= end) {
            const currDateStr = getStr(curr);
            
            // Buscar todos los eventos de este día
            const sameDayEvents = _eventos.filter(ev => {
                if (ev.google_event_id === evId) return false;
                const evSh = ev.inicio || "";
                const evEh = ev.fin || "";
                if (!evSh || !evEh) return false;
                return getStr(evSh) <= currDateStr && getStr(evEh) >= currDateStr;
            });
            
            for (const pat of patronesArr) {
                const othersUsingPat = sameDayEvents.filter(e => {
                    let ep = e.extended_props?.private?.app_patrones || e.app_patrones || [];
                    if (typeof ep === 'string') { try { ep = JSON.parse(ep); } catch(x){ ep = []; } }
                    return ep.includes(pat);
                });
                
                if (othersUsingPat.length > 0) {
                    for (const other of othersUsingPat) {
                        let otherOts = other.extended_props?.private?.app_ots || other.app_ots || [];
                        if (typeof otherOts === 'string') { try { otherOts = JSON.parse(otherOts); } catch(x){ otherOts = []; } }
                        
                        const common = proposedOTs.filter(ot => otherOts.includes(ot));
                        if (common.length === 0) {
                             return (targetDate !== targetEndDate ? `[${currDateStr}] ` : '') + `El patrón '${pat}' está bloqueado por otro técnico que no comparte OT.`;
                        }
                    }
                }
            }
            
            curr.setDate(curr.getDate() + 1);
        }
        return null;
    }'''

def robust_replace(text, old, new):
    import re
    # Remove excessive indentation/newlines for comparison
    def norm(s):
        return re.sub(r'\s+', ' ', s.strip())
    
    old_norm = norm(old)
    idx_start = -1
    idx_end = -1
    
    for m in re.finditer(r'function checkVehicleConflicts.*?return null; \/\/ OK\s*}', text, re.DOTALL):
        if norm(m.group(0)) == old_norm or 'Regla Capacidad' in m.group(0):
            idx_start = m.start()
            idx_end = m.end()
            break
            
    if idx_start != -1:
        return text[:idx_start] + new + text[idx_end:]
    return text.replace(old, new)


app_js = robust_replace(app_js, old_vehicle, new_vehicle)

if 'checkPatternConflicts' in app_js:
    # Also export it
    app_js = app_js.replace('getVehiculos, checkVehicleConflicts,', 'getVehiculos, checkVehicleConflicts, checkPatternConflicts,')
    open('webapp/app.js', 'w', encoding='utf-8').write(app_js)
    print("Patched app.js")
else:
    print("Failed to patch app.js")
