import os, re

# 1. Patch right-panel.js
text = open('webapp/right-panel.js', encoding='utf-8').read()

old_complex = r'''        const hasGuests = ev\.extended_props\?\.private\?\.has_guests === "true";\s+const isComplex = isMulti \|\| hasGuests;'''
new_complex = '''        const hasGuests = ev.extended_props?.private?.has_guests === "true";
        const isComplex = hasGuests;'''

if re.search(old_complex, text):
    text = re.sub(old_complex, new_complex, text)
    open('webapp/right-panel.js', 'w', encoding='utf-8').write(text)
    print("Patched isComplex in right-panel.js")
else:
    print("Could not find isComplex in right-panel.js")

# 2. Patch index.html version bump
html = open('webapp/index.html', encoding='utf-8').read()
html = html.replace('v=2.9', 'v=2.10')
open('webapp/index.html', 'w', encoding='utf-8').write(html)
print("Bumped version to 2.10 in index.html")
