#!/usr/bin/env python3
"""
Script para ejecutar la aplicación FarmaPlus Backend
"""

import uvicorn
import sys
import os

# Agregar el directorio raíz al path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def main():
    """Ejecutar la aplicación FastAPI"""
    print("🚀 Iniciando FarmaPlus Backend API...")
    print("📚 Documentación disponible en: http://localhost:8000/api/v1/docs")
    print("🔧 Para parar la aplicación: Ctrl+C")
    print("-" * 50)
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

if __name__ == "__main__":
    main() 