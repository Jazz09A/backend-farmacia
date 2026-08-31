# `migrations/archive/` — Scripts archivados

Esta carpeta contiene scripts históricos de migración/manual que **NO son
parte del esquema versionado por Alembic** y **no se cargan en el arranque
de la app** (`alembic/env.py` solo importa `app.models`).

## Estado

| Estado | Ubicación |
|--------|-----------|
| **Source of truth** | `alembic/versions/` (gestionado por Alembic) |
| Scripts legacy/históricos | Esta carpeta (`migrations/archive/`) |

Los scripts archivados pueden seguir referenciando modelos o tablas que
fueron eliminados del backend (ej. `CreditPayment`, `available_credit`).
Esto **no rompe el build** porque Alembic no los carga. Si necesitas
ejecutar alguno manualmente, hazlo bajo tu propio riesgo y contra una BD
de respaldo.

## Pre-deploy checklist

Si vas a desplegar contra una BD existente que fue migrada con estos
scripts manuales (no con Alembic), ejecuta primero:

```bash
alembic stamp head
```

Esto marca la BD como "al día" con el último revision de Alembic, evitando
que intente reaplicar migraciones.

## Para eliminar definitivamente

Estos scripts deben revisarse uno a uno antes de borrarse (ver R15 en el
AUDIT_REPORT.md). Mantenerlos aquí es seguro y conserva trazabilidad.