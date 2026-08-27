import os
lines=open('webapp/right-panel.js', encoding='utf-8').read().splitlines()
idx = [i for i, l in enumerate(lines) if 'const reqVehiculo =' in l][0]
lines.insert(idx+1, "            const editFechaFinEl = document.getElementById('edit-fecha-fin');")
lines.insert(idx+2, "            const newDateEnd = editFechaFinEl ? editFechaFinEl.value : '';")
open('webapp/right-panel.js', 'w', encoding='utf-8').write('\n'.join(lines))

