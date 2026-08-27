import os
text=open('webapp/right-panel.js', encoding='utf-8').read()
old = "            const finalTitle = groupInits ? \"\ - \\" : titulo;\n\n            for (const fdata of op.fechas) {"
new = "            const finalTitle = groupInits ? \"\ - \\" : titulo;\n\n            const pCons = document.getElementById('p-cons');\n            const pViaje = document.getElementById('p-viaje');\n            const isConsecutivo = (pCons && pCons.checked) || (pViaje && pViaje.checked);\n            let groupedFechas = op.fechas;\n            if (isConsecutivo && op.fechas.length > 1) {\n                const first = op.fechas[0];\n                const last = op.fechas[op.fechas.length - 1];\n                groupedFechas = [{\n                    date: first.date,\n                    fecha_fin: last.date,\n                    h_start: first.h_start,\n                    h_dur: first.h_dur\n                }];\n            }\n\n            for (const fdata of groupedFechas) {"
text = text.replace(old, new)
open('webapp/right-panel.js', 'w', encoding='utf-8').write(text)

