import os
lines=open('webapp/right-panel.js', encoding='utf-8').read().splitlines()
for i, l in enumerate(lines):
    if 'const isComplex =' in l and 'currentEvent?.extended_props' in l:
        lines[i] = '        const priv = currentEvent.extended_props ? currentEvent.extended_props.private : {};'
        lines.insert(i+1, '        const isComplex = priv && priv.has_guests === \"true\";')
        lines[i+3] = '            App.toast(\"No se puede editar eventos con invitados externos. Individualice primero.\", \"warning\");'
open('webapp/right-panel.js', 'w', encoding='utf-8').write('\n'.join(lines))

