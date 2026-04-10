# 🛡️ Guía de Seguridad y Credenciales - Akrimet Planner

Para proteger el acceso a tus calendarios y hojas de cálculo, hemos implementado un sistema de **Carga Híbrida** de credenciales. Esto permite que la aplicación funcione de forma segura sin exponer archivos sensibles en Git.

## 1. Protección de Archivos Locales
Los archivos `credentials.json` (secreto de la app) y `token.json` (acceso de usuario) ya están incluidos en el `.gitignore`.
- **NUNCA** los fuerces a Git con `git add -f`.
- Si necesitas mover el proyecto, copia estos archivos manualmente o usa Variables de Entorno.

---

## 2. Configuración mediante Variables de Entorno (Recomendado)
Para máxima seguridad, puedes dejar de usar archivos físicos y usar las Variables de Entorno de Windows. El código las buscará automáticamente antes que a los archivos.

### Pasos para configurar (PowerShell):

#### A. Guardar Credenciales (credentials.json)
Copia el contenido del archivo y ejecútalo en PowerShell:
```powershell
$content = Get-Content -Raw "C:\Ruta\A\Tu\credentials.json"
[System.Environment]::SetEnvironmentVariable("GOOGLE_CREDENTIALS_JSON", $content, "User")
```

#### B. Guardar Token de Sesión (token.json)
Copia el contenido del archivo generado tras el login:
```powershell
$content = Get-Content -Raw "C:\Ruta\A\Tu\token.json"
[System.Environment]::SetEnvironmentVariable("GOOGLE_TOKEN_JSON", $content, "User")
```

> [!TIP]
> Una vez configuradas las variables, puedes borrar los archivos físicos de la carpeta del proyecto. La aplicación seguirá funcionando.

---

## 3. Limpieza de Git (Si ya se subieron archivos)
Si detectas que tus secretos están en el historial de un repositorio remoto:

1. **Eliminar del índice actual (Ya realizado):**
   ```bash
   git rm --cached credentials.json token.json
   git commit -m "chore: securizar secretos y mover a gitignore"
   git push
   ```

2. **Rotar Secretos (CUIDADO):**
   Si el repositorio era **PÚBLICO**, debes entrar a [Google Cloud Console](https://console.cloud.google.com/), ir a "APIs y servicios" > "Credenciales" y **generar un nuevo Client Secret**. El anterior queda invalidado inmediatamente.

---

## 4. Estructura de Base de Datos
La base de datos SQLite `planificacion.db` también está ignorada por Git para evitar conflictos de datos y proteger la información operativa de tus técnicos.
