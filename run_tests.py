#!/usr/bin/env python3
"""
Script para ejecutar tests de FarmaPlus Backend
"""

import subprocess
import sys
import os

def run_command(command):
    """Ejecutar comando y mostrar resultado"""
    print(f"🔄 Ejecutando: {command}")
    print("-" * 50)
    
    result = subprocess.run(command, shell=True, capture_output=False)
    
    if result.returncode == 0:
        print(f"✅ Comando exitoso: {command}")
    else:
        print(f"❌ Comando falló: {command}")
    
    print("-" * 50)
    return result.returncode

def main():
    """Función principal"""
    if len(sys.argv) < 2:
        print("""
🧪 TESTING FARMAPLUS BACKEND

Uso: python run_tests.py [opción]

Opciones disponibles:
  all         - Ejecutar todos los tests
  unit        - Ejecutar solo tests unitarios
  integration - Ejecutar solo tests de integración
  auth        - Ejecutar solo tests de autenticación
  models      - Ejecutar solo tests de modelos
  services    - Ejecutar solo tests de servicios
  endpoints   - Ejecutar solo tests de endpoints
  coverage    - Ejecutar tests con coverage
  verbose     - Ejecutar tests con output detallado
  fast        - Ejecutar tests rápidos (sin los marcados como 'slow')
  new         - ✨ Ejecutar solo tests de nuevas funcionalidades
  categories  - ✨ Ejecutar tests de categorías y marcas  
  promotions  - ✨ Ejecutar tests de sistema de promociones
  inventory   - ✨ Ejecutar tests de sistema de inventario

Ejemplos:
  python run_tests.py all
  python run_tests.py auth
  python run_tests.py coverage
        """)
        return
    
    option = sys.argv[1].lower()
    
    # Configurar PYTHONPATH
    os.environ['PYTHONPATH'] = os.getcwd()
    
    # Comandos disponibles
    commands = {
        'all': 'pytest app/tests/ -v',
        'unit': 'pytest app/tests/ -v -m "unit"',
        'integration': 'pytest app/tests/ -v -m "integration"',
        'auth': 'pytest app/tests/test_endpoints.py::TestAuthEndpoints -v',
        'models': 'pytest app/tests/test_models.py -v',
        'services': 'pytest app/tests/test_services.py -v',
        'endpoints': 'pytest app/tests/test_endpoints.py -v',
        'coverage': 'pytest app/tests/ --cov=app --cov-report=html --cov-report=term-missing -v',
        'verbose': 'pytest app/tests/ -v -s --tb=long',
        'fast': 'pytest app/tests/ -v -m "not slow"',
        'new': 'pytest app/tests/test_category_models.py app/tests/test_promotion_models.py app/tests/test_inventory_models.py app/tests/test_category_endpoints.py app/tests/test_schemas.py app/tests/test_new_features_integration.py -v',
        'categories': 'pytest app/tests/test_category_models.py app/tests/test_category_endpoints.py -v',
        'promotions': 'pytest app/tests/test_promotion_models.py -v',
        'inventory': 'pytest app/tests/test_inventory_models.py -v'
    }
    
    if option not in commands:
        print(f"❌ Opción '{option}' no válida")
        print("Usa 'python run_tests.py' para ver opciones disponibles")
        return
    
    print(f"🚀 Iniciando tests: {option}")
    
    # Ejecutar comando
    exit_code = run_command(commands[option])
    
    if exit_code == 0:
        print(f"🎉 ¡Tests {option} completados exitosamente!")
        
        if option == 'coverage':
            print("📊 Reporte de coverage generado en htmlcov/index.html")
    else:
        print(f"💥 Tests {option} fallaron")
        sys.exit(1)

if __name__ == "__main__":
    main() 