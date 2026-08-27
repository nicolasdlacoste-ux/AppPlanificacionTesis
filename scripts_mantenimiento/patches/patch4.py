import os
text=open('webapp/right-panel.js', encoding='utf-8').read()
old = "            const isConsecutivo = document.getElementById('p-cons')?.checked || document.getElementById('p-viaje')?.checked;"
new = "            const pCons = document.getElementById('p-cons');\n            const pViaje = document.getElementById('p-viaje');\n            const isConsecutivo = (pCons && pCons.checked) || (pViaje && pViaje.checked);"
text = text.replace(old, new)
open('webapp/right-panel.js', 'w', encoding='utf-8').write(text)

