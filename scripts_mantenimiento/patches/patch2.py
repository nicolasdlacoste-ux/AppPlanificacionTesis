import os
text=open('webapp/right-panel.js', encoding='utf-8').read()
old = "            const cambioFechaHora = (newDate !== origDate) ||"
new = "            let origDateEnd = (currentEvent.fin || '').substring(0, 10);\n            if (currentEvent._isMultiDay && currentEvent.fin && !currentEvent.fin.includes('T')) {\n                const d = new Date(origDateEnd + 'T00:00:00');\n                d.setDate(d.getDate() - 1);\n                origDateEnd = d.toISOString().substring(0, 10);\n            }\n\n            const cambioFechaHora = (newDate !== origDate) || (newDateEnd !== origDateEnd) ||"
text = text.replace(old, new)
open('webapp/right-panel.js', 'w', encoding='utf-8').write(text)

