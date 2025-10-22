import os
import sqlite3
from datetime import datetime

BACKUP_PREFIX = 'db.sqlite3.backup_pre_migration_'
CURRENT_DB = 'db.sqlite3'


def find_backup_db():
    files = [f for f in os.listdir('.') if f.startswith(BACKUP_PREFIX)]
    if not files:
        return None
    files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    return files[0]


def list_tables(conn):
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    return [r[0] for r in cur.fetchall()]


def table_count(conn, table):
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT COUNT(1) FROM {table}")
        return cur.fetchone()[0]
    except Exception:
        return None


def main():
    backup = find_backup_db()
    if not backup:
        print("❌ No se encontró DB de backup (db.sqlite3.backup_pre_migration_*)")
        return 1

    print("="*80)
    print("🔎 Comparación de Backup vs Base Actual")
    print("="*80)
    print(f"📦 Backup: {backup}")
    print(f"🗄️ Actual: {CURRENT_DB}\n")

    bconn = sqlite3.connect(backup)
    cconn = sqlite3.connect(CURRENT_DB)

    try:
        b_tables = set(list_tables(bconn))
        c_tables = set(list_tables(cconn))

        common = sorted(b_tables & c_tables)
        only_backup = sorted(b_tables - c_tables)
        only_current = sorted(c_tables - b_tables)

        print("📋 Tablas en común (conteos backup -> actual):")
        missing_candidates = []
        for t in common:
            bcnt = table_count(bconn, t)
            ccnt = table_count(cconn, t)
            print(f" - {t:30} {bcnt:6}  ->  {ccnt:6}")
            if (bcnt or 0) > 0 and (ccnt or 0) == 0:
                missing_candidates.append(t)

        print("\n📦 Solo en backup:")
        for t in only_backup:
            print(f" - {t}")

        print("\n🗄️ Solo en actual:")
        for t in only_current:
            print(f" - {t}")

        if missing_candidates:
            print("\n⚠️ Tablas con datos en backup y vacías en actual (posibles a importar):")
            for t in missing_candidates:
                print(f" - {t}")
        else:
            print("\n✅ No hay tablas con datos faltantes obvios (según conteos)")
        return 0
    finally:
        bconn.close()
        cconn.close()


if __name__ == '__main__':
    raise SystemExit(main())
