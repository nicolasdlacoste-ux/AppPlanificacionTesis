// ════════════════════════════════════════
// CONFIGURATION MENU LOGIC
// ════════════════════════════════════════

const ConfigMenu = (() => {
    let currentConfig = null;
    let unlocked = false; // Estado de desbloqueo (PIN)
    let isSaving = false;

    async function init() {
        const btnOpen = document.getElementById('btn-open-config');
        if (btnOpen) {
            btnOpen.addEventListener('click', openModal);
        }

        // Pestañas
        document.querySelectorAll('.config-tabs .tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => switchTab(e.target.dataset.tab));
        });

        // Seguridad
        const btnUnlock = document.getElementById('btn-unlock-security');
        if (btnUnlock) btnUnlock.addEventListener('click', unlockSecurity);
        
        // Servicios
        const cfgNewService = document.getElementById('cfg-new-service');
        if (cfgNewService) {
            cfgNewService.addEventListener('input', (e) => {
                const btnAdd = document.getElementById('btn-add-service');
                if (btnAdd) btnAdd.disabled = !e.target.value.trim();
            });
        }
        const btnAddService = document.getElementById('btn-add-service');
        if (btnAddService) btnAddService.addEventListener('click', addService);

        // Usuarios autorizados
        const btnAddUser = document.getElementById('btn-add-user');
        if (btnAddUser) btnAddUser.addEventListener('click', addUser);

        // Técnicos
        const btnRefreshCal = document.getElementById('btn-refresh-calendars');
        if (btnRefreshCal) btnRefreshCal.addEventListener('click', fetchCalendars);

        // Feriados
        const btnAddHoliday = document.getElementById('btn-add-holiday');
        if (btnAddHoliday) btnAddHoliday.addEventListener('click', addHoliday);
        const btnImportHolidays = document.getElementById('btn-import-holidays');
        if (btnImportHolidays) btnImportHolidays.addEventListener('click', importGoogleHolidays);

        // Guardar
        const btnSaveConfig = document.getElementById('btn-save-config');
        if (btnSaveConfig) btnSaveConfig.addEventListener('click', saveConfig);
    }

    async function openModal() {
        document.getElementById('modal-config').classList.remove('hidden');
        unlocked = false;
        resetSecurityView();
        switchTab('tab-general');
        await loadConfig();
        await fetchCalendars(); // Cargar la lista de calendarios al abrir
    }

    function switchTab(tabId) {
        document.querySelectorAll('.config-tabs .tab-btn').forEach(b => b.classList.remove('active'));
        const activeTab = document.querySelector(`.config-tabs .tab-btn[data-tab="${tabId}"]`);
        if (activeTab) activeTab.classList.add('active');
        
        document.querySelectorAll('.config-tab-content').forEach(c => c.classList.add('hidden'));
        const targetContent = document.getElementById(tabId);
        if (targetContent) targetContent.classList.remove('hidden');

        // Si cambia a pestaña de seguridad y no está desbloqueado, ocultar contenido
        if (tabId === 'tab-seguridad' && !unlocked) {
            resetSecurityView();
        }
    }

    async function loadConfig() {
        try {
            const res = await fetch('/api/config');
            currentConfig = await res.json();
            
            // Llenar General
            const elPast = document.getElementById('cfg-sync-past');
            if (elPast) elPast.value = currentConfig.sync_days_past || 30;
            const elFuture = document.getElementById('cfg-sync-future');
            if (elFuture) elFuture.value = currentConfig.sync_days_future || 180;
            
            if (!currentConfig.holidays) currentConfig.holidays = {};
            
            renderServices();
            renderUsers();
            renderHolidays();

        } catch (e) {
            console.error("Error cargando configuración", e);
            toast("Error al cargar la configuración", "error");
        }
    }

    function renderServices() {
        const container = document.getElementById('cfg-servicios-container');
        if (!container) return;
        container.innerHTML = '';
        (currentConfig.services || []).forEach(srv => {
            const chip = document.createElement('div');
            chip.className = 'patron-chip';
            chip.style.backgroundColor = 'var(--bg-hover)';
            chip.style.color = 'var(--text)';
            chip.style.border = '1px solid var(--border)';
            chip.innerHTML = `
                ${srv} 
                <i class="fa-solid fa-times" style="margin-left: 5px; cursor: ${unlocked ? 'pointer' : 'not-allowed'}; color: var(--text-muted);" ${unlocked ? `onclick="ConfigMenu.removeService('${srv}')"` : ''}></i>
            `;
            container.appendChild(chip);
        });
        
        const newServiceInput = document.getElementById('cfg-new-service');
        const btnAddService = document.getElementById('btn-add-service');
        if (newServiceInput) {
            newServiceInput.disabled = !unlocked;
            newServiceInput.placeholder = unlocked ? "Nuevo servicio..." : "Desbloquea para agregar servicios";
        }
        if (btnAddService) {
            btnAddService.style.display = unlocked ? 'inline-block' : 'none';
        }
    }

    function addService() {
        if (!unlocked) return;
        const input = document.getElementById('cfg-new-service');
        const val = input.value.trim();
        if (val && !currentConfig.services.includes(val)) {
            currentConfig.services.push(val);
            input.value = '';
            document.getElementById('btn-add-service').disabled = true;
            renderServices();
        }
    }

    function removeService(srv) {
        if (!unlocked) return;
        currentConfig.services = currentConfig.services.filter(s => s !== srv);
        renderServices();
    }

    function renderUsers() {
        const container = document.getElementById('cfg-auth-users-container');
        if (!container) return;
        container.innerHTML = '';
        (currentConfig.authorized_users || []).forEach(u => {
            const chip = document.createElement('div');
            chip.className = 'patron-chip';
            chip.style.backgroundColor = 'var(--bg-hover)';
            chip.style.color = 'var(--text)';
            chip.style.border = '1px solid var(--border)';
            chip.innerHTML = `
                ${u} 
                <i class="fa-solid fa-times" style="margin-left: 5px; cursor: pointer; color: var(--text-muted);" onclick="ConfigMenu.removeUser('${u}')"></i>
            `;
            container.appendChild(chip);
        });
    }

    function addUser() {
        const input = document.getElementById('cfg-new-user');
        const val = input.value.trim();
        if (val && !currentConfig.authorized_users.includes(val)) {
            currentConfig.authorized_users.push(val);
            input.value = '';
            renderUsers();
        }
    }

    function removeUser(user) {
        currentConfig.authorized_users = currentConfig.authorized_users.filter(u => u !== user);
        renderUsers();
    }

    async function unlockSecurity() {
        const elPin = document.getElementById('cfg-pin-input');
        const pinInput = elPin ? elPin.value : '';
        const errorMsg = document.getElementById('security-error-msg');
        
        try {
            const res = await fetch('/api/config/verify-pin', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pin: pinInput })
            });
            const data = await res.json();
            
            if (data.valid) {
                unlocked = true;
                if (errorMsg) errorMsg.style.display = 'none';
                const unlockArea = document.getElementById('security-unlock-area');
                if (unlockArea) unlockArea.classList.add('hidden');
                const contentArea = document.getElementById('security-content-area');
                if (contentArea) contentArea.classList.remove('hidden');
                renderServices(); // Re-renderizar servicios para habilitar botones de borrar
            } else {
                if (errorMsg) errorMsg.style.display = 'block';
            }
        } catch (e) {
            console.error(e);
            errorMsg.style.display = 'block';
            errorMsg.textContent = 'Error al verificar PIN';
        }
    }

    function resetSecurityView() {
        const unlockArea = document.getElementById('security-unlock-area');
        if (unlockArea) unlockArea.classList.remove('hidden');
        const contentArea = document.getElementById('security-content-area');
        if (contentArea) contentArea.classList.add('hidden');
        const pinIn = document.getElementById('cfg-pin-input');
        if (pinIn) pinIn.value = '';
        const errMsg = document.getElementById('security-error-msg');
        if (errMsg) errMsg.style.display = 'none';
        const newPin = document.getElementById('cfg-new-pin');
        if (newPin) newPin.value = '';
    }

    // ────────────────────────────────────────────────────────
    // CALENDARIOS DE GOOGLE
    // ────────────────────────────────────────────────────────

    function generateInitials(name) {
        if (!name) return "??";
        const parts = name.split(' ');
        if (parts.length >= 2) {
            return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
        }
        return name.substring(0, 2).toUpperCase();
    }

    async function fetchCalendars() {
        const tbody = document.getElementById('cfg-tecnicos-tbody');
        if (!tbody) return;
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;">Cargando calendarios de Google...</td></tr>';
        
        try {
            const res = await fetch('/api/calendars');
            if (!res.ok) throw new Error("Error al obtener calendarios");
            const calendars = await res.json();
            
            tbody.innerHTML = '';
            
            if (calendars.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);">No se encontraron calendarios compartidos con permisos de escritura.</td></tr>';
                return;
            }

            // Opciones de servicios
            const servicesOpts = (currentConfig.services || []).map(s => `<option value="${s}">${s}</option>`).join('');

            // Ordenar los calendarios según el sort_order guardado antes de renderizar
            calendars.sort((a, b) => {
                const confA = currentConfig.technicians[a.id] || { sort_order: 999 };
                const confB = currentConfig.technicians[b.id] || { sort_order: 999 };
                return (confA.sort_order || 0) - (confB.sort_order || 0);
            });

            calendars.forEach(cal => {
                const conf = currentConfig.technicians[cal.id] || {};
                const isEnabled = conf.enabled || false;
                const alias = conf.alias || cal.summary; // Default to calendar summary
                const iniciales = conf.iniciales || generateInitials(alias);
                const assignedService = conf.service || '';
                const sortOrder = conf.sort_order !== undefined ? conf.sort_order : 0;

                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td style="text-align:center;">
                        <input type="checkbox" class="tech-chk" data-id="${cal.id}" ${isEnabled ? 'checked' : ''}>
                    </td>
                    <td style="color: var(--text-muted);">${cal.id}</td>
                    <td>
                        <input type="text" class="param-input tech-alias" data-id="${cal.id}" placeholder="${cal.summary}" value="${alias}" style="width:100%; margin:0; padding:2px 5px;" ${!isEnabled ? 'disabled' : ''}>
                    </td>
                    <td>
                        <input type="text" class="param-input tech-ini" data-id="${cal.id}" value="${iniciales}" style="width:100%; margin:0; padding:2px 5px; text-transform:uppercase;" maxlength="3" ${!isEnabled ? 'disabled' : ''}>
                    </td>
                    <td>
                        <select class="param-input tech-service" data-id="${cal.id}" style="width:100%; margin:0; padding:2px 5px;" ${!isEnabled ? 'disabled' : ''}>
                            <option value="">-- Sin Servicio --</option>
                            ${servicesOpts}
                        </select>
                    </td>
                    <td>
                        <input type="number" class="param-input tech-sort" data-id="${cal.id}" value="${sortOrder}" style="width:100%; margin:0; padding:2px 5px;" ${!isEnabled ? 'disabled' : ''}>
                    </td>
                `;
                
                // Actualizar selects
                const sel = tr.querySelector('.tech-service');
                sel.value = assignedService;

                // Evento checkbox para habilitar inputs
                const chk = tr.querySelector('.tech-chk');
                chk.addEventListener('change', (e) => {
                    const disabled = !e.target.checked;
                    tr.querySelector('.tech-alias').disabled = disabled;
                    tr.querySelector('.tech-ini').disabled = disabled;
                    tr.querySelector('.tech-service').disabled = disabled;
                    tr.querySelector('.tech-sort').disabled = disabled;
                });

                tbody.appendChild(tr);
            });

        } catch (e) {
            console.error(e);
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#ff4c4c;">Fallo la carga. Verifica tu autenticación con Google.</td></tr>';
        }
    }

    // ────────────────────────────────────────────────────────
    // FERIADOS (HOLIDAYS)
    // ────────────────────────────────────────────────────────
    
    function renderHolidays() {
        const tbody = document.getElementById('cfg-holidays-tbody');
        if (!tbody) return;
        tbody.innerHTML = '';
        const holidays = currentConfig.holidays || {};
        const dates = Object.keys(holidays).sort();
        
        if (dates.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--text-muted);">No hay feriados configurados.</td></tr>';
            return;
        }

        dates.forEach(date => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${date}</td>
                <td>${holidays[date]}</td>
                <td style="text-align: center;">
                    <button class="btn-secondary btn-sm" onclick="ConfigMenu.removeHoliday('${date}')" style="padding: 2px 6px; color: #ff4c4c;">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    }

    function addHoliday() {
        const dateInput = document.getElementById('cfg-new-holiday-date');
        const nameInput = document.getElementById('cfg-new-holiday-name');
        const date = dateInput.value;
        const name = nameInput.value.trim();
        
        if (date && name) {
            if (!currentConfig.holidays) currentConfig.holidays = {};
            currentConfig.holidays[date] = name;
            dateInput.value = '';
            nameInput.value = '';
            renderHolidays();
        } else {
            toast("Debe ingresar fecha y nombre del feriado", "warning");
        }
    }

    function removeHoliday(date) {
        if (currentConfig.holidays && currentConfig.holidays[date]) {
            delete currentConfig.holidays[date];
            renderHolidays();
        }
    }

    async function importGoogleHolidays() {
        const btn = document.getElementById('btn-import-holidays');
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Importando...';
        
        try {
            const res = await fetch('/api/holidays/import_google');
            if (!res.ok) throw new Error("Error al importar feriados");
            const data = await res.json();
            
            currentConfig.holidays = data.holidays || {};
            renderHolidays();
            toast(`Se importaron ${data.imported} feriados desde Google.`, "success");
        } catch (e) {
            console.error(e);
            toast("Fallo la importación. Verificá la autenticación o conexión.", "error");
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-brands fa-google"></i> Importar de Google AR';
        }
    }

    async function saveConfig() {
        if (isSaving) return;
        
        const btn = document.getElementById('btn-save-config');
        const statusMsg = document.getElementById('config-status-msg');
        
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Guardando...';
        }
        if (statusMsg) statusMsg.textContent = '';

        try {
            // Actualizar currentConfig
            currentConfig.sync_days_past = parseInt(document.getElementById('cfg-sync-past').value) || 30;
            currentConfig.sync_days_future = parseInt(document.getElementById('cfg-sync-future').value) || 180;
            
            // Recolectar técnicos
            currentConfig.technicians = {};
            document.querySelectorAll('#cfg-tecnicos-tbody tr').forEach(tr => {
                const chk = tr.querySelector('.tech-chk');
                if (!chk) return;
                const id = chk.dataset.id;
                const alias = tr.querySelector('.tech-alias').value.trim();
                const ini = tr.querySelector('.tech-ini').value.trim();
                const service = tr.querySelector('.tech-service').value;
                const sort = parseInt(tr.querySelector('.tech-sort').value) || 0;

                currentConfig.technicians[id] = {
                    enabled: chk.checked,
                    alias: alias || tr.querySelector('.tech-alias').placeholder,
                    iniciales: ini.toUpperCase(),
                    service: service,
                    sort_order: sort
                };
            });

            const payload = {
                config: currentConfig
            };

            // Si se desbloqueó la seguridad, mandamos el PIN actual para autorizar cambios protegidos (Servicios/Seguridad)
            if (unlocked) {
                payload.pin = document.getElementById('cfg-pin-input').value;
            }

            const newPin = document.getElementById('cfg-new-pin').value;
            if (newPin) {
                currentConfig.pin = newPin; // Actualizar localmente para guardarlo
            }

            const res = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!res.ok) {
                const errData = await res.json();
                throw new Error(errData.detail || "Error al guardar configuración");
            }

            statusMsg.textContent = 'Guardado con éxito.';
            statusMsg.style.color = 'var(--success)';
            
            setTimeout(() => {
                document.getElementById('modal-config').classList.add('hidden');
                toast("Configuración guardada.", "info");
                triggerRefresh();
            }, 1000);

        } catch (e) {
            statusMsg.textContent = e.message;
            statusMsg.style.color = '#ff4c4c';
        } finally {
            isSaving = false;
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-save"></i> Guardar Cambios';
        }
    }

    function triggerRefresh() {
        if (window.App && window.App.refresh) {
            window.App.refresh();
        }
    }

    // Exponer públicamente
    return {
        init,
        removeService,
        removeUser,
        removeHoliday,
        triggerRefresh
    };
})();
