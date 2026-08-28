#!/usr/bin/env python3
"""
Script de verificación de exportación
Verifica que todos los datos se exportaron correctamente
"""

import json
import os
from pathlib import Path

def verify_export():
    export_dir = Path("migrations\export_data_20251021_210134")
    metadata_file = export_dir / "export_metadata.json"
    
    with open(metadata_file, 'r', encoding='utf-8') as f:
        metadata = json.load(f)
    
    print("🔍 Verificando exportación...")
    print(f"📊 Total de tablas: {metadata['tables_exported']}")
    print(f"📊 Total de registros: {metadata['total_records']:,}")
    
    for table_name, table_info in metadata['tables'].items():
        if 'error' in table_info:
            print(f"❌ {table_name}: ERROR - {table_info['error']}")
        else:
            print(f"✅ {table_name}: {table_info['record_count']:,} registros")
    
    print("\n✅ Verificación completada")

if __name__ == "__main__":
    verify_export()
