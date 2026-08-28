# Rotación de Secretos

Este archivo documenta las rotaciones de credenciales del proyecto
`backend-farmacia`. **Nunca escribir el valor real de la credencial aquí**;
solo se documenta qué se rotó, cuándo y por qué motivo.

## Procedimiento general

1. Crear nueva credencial en el sistema externo (Gmail, DB, etc.).
2. Actualizar la variable correspondiente en el archivo `.env` (no
   versionado).
3. Verificar que la aplicación arranca (`python -c "from app.config.settings import Settings; Settings()"`).
4. Si la credencial pudo haber sido filtrada al repositorio o al historial
   git, coordinar con el equipo la reescritura de historial con
   `git filter-repo`.
5. Documentar aquí: fecha, cuenta, motivo, hash SHA256 del commit
   posterior a la rotación.

---

## 2026-08-27 — Rotación pendiente de `SMTP_PASSWORD`

- **Cuenta:** `programatevzla@gmail.com` (Gmail App Password)
- **Estado:** Pendiente. El default hardcodeado `"crpg cagx zyyg hgys"` fue
  eliminado de `app/config/settings.py` (ahora es requerido y validado).
  Falta generar la nueva App Password en Google y reemplazar el placeholder
  en `.env`.
- **Motivo:** la credencial estaba hardcodeada en el código fuente y
  potencialmente en el historial git del repositorio. Tratar como credencial
  **comprometida**: revocar la App Password existente y generar una nueva.
- **Acción del usuario:**
  1. Ir a https://myaccount.google.com/apppasswords.
  2. Revocar la App Password asociada a "FarmaPlus" (o todas si no se
     reconoce).
  3. Crear una nueva App Password.
  4. Pegar el valor en `.env` (`SMTP_PASSWORD=...`).
  5. Validar: `uv run python -c "from email_service import email_service; ..."`
     o un envío de prueba manual.
- **SHA256 del commit de limpieza (a llenar tras commit):** _pendiente_.
