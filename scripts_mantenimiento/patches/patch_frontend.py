import os, re

text = open('webapp/right-panel.js', encoding='utf-8').read()

old_block = r'''        // Edit event - Solo bloquear edici.n \(no eliminar\) para eventos multi-d.a
        const btnEditEv = document\.getElementById\('btn-edit-event'\);
        if \(btnEditEv\) \{
            btnEditEv\.classList\.toggle\('hidden', isMulti\);
        \}'''

new_block = '''        // Edit event - Eventos multidía ahora se pueden editar
        const btnEditEv = document.getElementById('btn-edit-event');
        if (btnEditEv) {
            btnEditEv.classList.remove('hidden');
        }'''

if re.search(old_block, text):
    text = re.sub(old_block, new_block, text)
    open('webapp/right-panel.js', 'w', encoding='utf-8').write(text)
    print("Patched right-panel.js successfully!")
else:
    print("Could not find the target string in right-panel.js!")
