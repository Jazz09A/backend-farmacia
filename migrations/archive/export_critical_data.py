"""
Exportar datos críticos antes de la migración a USD
Este script exporta productos, órdenes y pagos de crédito a CSV para backup
"""
import csv
import os
from datetime import datetime
from pathlib import Path

# Configurar path para imports
import sys
sys.path.append(str(Path(__file__).parent.parent))

from app.config.database import SessionLocal
from app.models.product import Product
from app.models.order import Order, OrderItem
from app.models.user import User

def export_products():
    """Exportar todos los productos con precios en ambas monedas"""
    db = SessionLocal()
    try:
        products = db.query(Product).all()
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"backup/products_pre_migration_{timestamp}.csv"
        
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'name', 'brand', 'category', 
                'price_ves', 'price_ref', 'stock', 'in_stock'
            ])
            
            for p in products:
                writer.writerow([
                    p.id, 
                    p.name, 
                    p.brand or '', 
                    p.category or '',
                    p.price_ves, 
                    p.price_ref, 
                    p.stock, 
                    p.in_stock
                ])
        
        print(f"✅ {len(products)} productos exportados: {filename}")
        return len(products)
    finally:
        db.close()

def export_orders():
    """Exportar todas las órdenes con montos en ambas monedas"""
    db = SessionLocal()
    try:
        orders = db.query(Order).all()
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"backup/orders_pre_migration_{timestamp}.csv"
        
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'order_number', 'user_id', 'status',
                'total', 'total_ref', 'subtotal', 'subtotal_ref',
                'shipping_cost', 'shipping_cost_ref', 'taxes', 'taxes_ref',
                'currency', 'exchange_rate', 'is_credit_order', 
                'credit_remaining', 'created_at'
            ])
            
            for o in orders:
                writer.writerow([
                    o.id,
                    o.order_number,
                    o.user_id,
                    o.status,
                    o.total,
                    o.total_ref,
                    o.subtotal,
                    o.subtotal_ref,
                    o.shipping_cost,
                    o.shipping_cost_ref,
                    o.taxes,
                    o.taxes_ref,
                    o.currency,
                    o.exchange_rate,
                    o.is_credit_order,
                    o.credit_remaining if o.is_credit_order else 0,
                    o.created_at
                ])
        
        print(f"✅ {len(orders)} órdenes exportadas: {filename}")
        return len(orders)
    finally:
        db.close()

def export_order_items():
    """Exportar items de órdenes con precios en ambas monedas"""
    db = SessionLocal()
    try:
        items = db.query(OrderItem).all()
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"backup/order_items_pre_migration_{timestamp}.csv"
        
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'order_id', 'product_id', 'product_name',
                'quantity', 'unit_price', 'unit_price_ref',
                'total_price', 'total_price_ref'
            ])
            
            for item in items:
                writer.writerow([
                    item.id,
                    item.order_id,
                    item.product_id,
                    item.product_name,
                    item.quantity,
                    item.unit_price,
                    item.unit_price_ref,
                    item.total_price,
                    item.total_price_ref
                ])
        
        print(f"✅ {len(items)} items de órdenes exportados: {filename}")
        return len(items)
    finally:
        db.close()

def export_credit_payments():
    """Exportar pagos de crédito si existen"""
    db = SessionLocal()
    try:
        # Verificar si la tabla existe
        try:
            from app.models.credit_payment import CreditPayment
            payments = db.query(CreditPayment).all()
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"backup/credit_payments_pre_migration_{timestamp}.csv"
            
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'id', 'order_id', 'user_id', 'amount', 'amount_ves',
                    'currency', 'exchange_rate_used', 'status', 'created_at'
                ])
                
                for p in payments:
                    writer.writerow([
                        p.id,
                        p.order_id,
                        p.user_id,
                        p.amount,
                        p.amount_ves if hasattr(p, 'amount_ves') else None,
                        p.currency if hasattr(p, 'currency') else None,
                        p.exchange_rate_used,
                        p.status,
                        p.created_at
                    ])
            
            print(f"✅ {len(payments)} pagos de crédito exportados: {filename}")
            return len(payments)
        except ImportError:
            print("⚠️  Tabla credit_payments no existe aún")
            return 0
    finally:
        db.close()

def verify_exports():
    """Verificar que los exports se crearon correctamente"""
    backup_dir = Path("backup")
    csv_files = list(backup_dir.glob("*.csv"))
    
    print(f"\n📊 Archivos de backup creados:")
    for file in csv_files:
        size_kb = file.stat().st_size / 1024
        print(f"   - {file.name} ({size_kb:.2f} KB)")
    
    return len(csv_files)

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🔒 EXPORTANDO DATOS CRÍTICOS PRE-MIGRACIÓN")
    print("="*60 + "\n")
    
    # Crear directorio backup si no existe
    os.makedirs('backup', exist_ok=True)
    
    try:
        # Exportar todas las tablas críticas
        products_count = export_products()
        orders_count = export_orders()
        items_count = export_order_items()
        payments_count = export_credit_payments()
        
        # Verificar exports
        files_count = verify_exports()
        
        print("\n" + "="*60)
        print("✅ BACKUP COMPLETADO EXITOSAMENTE")
        print("="*60)
        print(f"\nResumen:")
        print(f"  - Productos exportados: {products_count}")
        print(f"  - Órdenes exportadas: {orders_count}")
        print(f"  - Items exportados: {items_count}")
        print(f"  - Pagos exportados: {payments_count}")
        print(f"  - Archivos CSV creados: {files_count}")
        print(f"\n✅ Los datos están seguros en el directorio 'backup/'")
        
    except Exception as e:
        print(f"\n❌ ERROR durante el backup: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

