import sys

def patch_frontend():
    with open('webapp/right-panel.js', 'r', encoding='utf-8') as f:
        content = f.read()

    old_code = "if (!r.ok) throw new Error(await r.text());"
    new_code = '''if (!r.ok) {
                        const errText = await r.text();
                        try {
                            const errJson = JSON.parse(errText);
                            throw new Error(errJson.detail || errText);
                        } catch(e) {
                            if(e.message === errJson?.detail || e.message === errText) throw e;
                            throw new Error(errText);
                        }
                    }'''

    if old_code in content:
        content = content.replace(old_code, new_code)
        with open('webapp/right-panel.js', 'w', encoding='utf-8') as f:
            f.write(content)
        print("Patched right-panel.js")
    else:
        print("Could not find exact string.")

patch_frontend()
