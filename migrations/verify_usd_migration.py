"""
Script de verificación post-migración a USD unificado

Este script valida que la migración se haya ejecutado correctamente:
1. Verifica estructura de tablas
2. Compara datos pre y post migración
3. Valida integridad de datos
4. Genera reporte detallado
"""

import sys
import os
from decimal import Decimal
from datetime import datetime
import csv

# Agregar el directorio raíz al path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text
from app.config.database import SessionLocal, engine
from app.models.product import Product
from app.models.order import Order, OrderItem
from app.models.credit_payment import CreditPayment


class MigrationVerifier:
    def __init__(self):
        self.db = SessionLocal()
        self.inspector = inspect(engine)
        self.errors = []
        self.warnings = []
        self.success = []
        
    def verify_all(self):
        """Ejecutar todas las verificaciones"""
        print("\n" + "="*80)
        print("🔍 VERIFICACIÓN POST-MIGRACIÓN USD")
        print("="*80 + "\n")
        
        self.verify_schema()
        self.verify_data_integrity()
        self.compare_with_backup()
        self.generate_report()
        
        return len(self.errors) == 0
    
    def verify_schema(self):
        """Verificar que las columnas correctas existan (o no existan)"""
        print("📋 Verificando estructura de tablas...\n")
        
        # ============================================================================
        # PRODUCTS
        # ============================================================================
        print("  🔍 Tabla Products:")
        products_cols = [col['name'] for col in self.inspector.get_columns('products')]
        
        # Debe TENER price
        if 'price' in products_cols:
            self.success.append("✓ Products.price existe")
            print("    ✅ price existe (USD)")
        else:
            self.errors.append("✗ Products.price NO existe")
            print("    ❌ price NO existe")
        
        # NO debe tener price_ves ni price_ref
        if 'price_ves' not in products_cols:
            self.success.append("✓ Products.price_ves eliminado")
            print("    ✅ price_ves eliminado")
        else:
            self.errors.append("✗ Products.price_ves aún existe")
            print("    ❌ price_ves aún existe")
        
        if 'price_ref' not in products_cols:
            self.success.append("✓ Products.price_ref eliminado")
            print("    ✅ price_ref eliminado")
        else:
            self.errors.append("✗ Products.price_ref aún existe")
            print("    ❌ price_ref aún existe")
        
        # ============================================================================
        # ORDERS
        # ============================================================================
        print("\n  🔍 Tabla Orders:")
        orders_cols = [col['name'] for col in self.inspector.get_columns('orders')]
        
        # Debe TENER payment_currency
        if 'payment_currency' in orders_cols:
            self.success.append("✓ Orders.payment_currency existe")
            print("    ✅ payment_currency existe")
        else:
            self.errors.append("✗ Orders.payment_currency NO existe")
            print("    ❌ payment_currency NO existe")
        
        # NO debe tener currency (renombrado a payment_currency)
        if 'currency' not in orders_cols:
            self.success.append("✓ Orders.currency eliminado")
            print("    ✅ currency eliminado")
        else:
            self.errors.append("✗ Orders.currency aún existe")
            print("    ❌ currency aún existe")
        
        # NO debe tener *_ref
        for field in ['subtotal_ref', 'shipping_cost_ref', 'taxes_ref', 'total_ref']:
            if field not in orders_cols:
                self.success.append(f"✓ Orders.{field} eliminado")
                print(f"    ✅ {field} eliminado")
            else:
                self.errors.append(f"✗ Orders.{field} aún existe")
                print(f"    ❌ {field} aún existe")
        
        # ============================================================================
        # ORDER_ITEMS
        # ============================================================================
        print("\n  🔍 Tabla OrderItems:")
        order_items_cols = [col['name'] for col in self.inspector.get_columns('order_items')]
        
        # NO debe tener *_ref
        for field in ['unit_price_ref', 'total_price_ref']:
            if field not in order_items_cols:
                self.success.append(f"✓ OrderItems.{field} eliminado")
                print(f"    ✅ {field} eliminado")
            else:
                self.errors.append(f"✗ OrderItems.{field} aún existe")
                print(f"    ❌ {field} aún existe")
        
        # ============================================================================
        # CREDIT_PAYMENTS
        # ============================================================================
        print("\n  🔍 Tabla CreditPayments:")
        credit_payments_cols = [col['name'] for col in self.inspector.get_columns('credit_payments')]
        
        # Debe TENER payment_currency
        if 'payment_currency' in credit_payments_cols:
            self.success.append("✓ CreditPayments.payment_currency existe")
            print("    ✅ payment_currency existe")
        else:
            self.errors.append("✗ CreditPayments.payment_currency NO existe")
            print("    ❌ payment_currency NO existe")
        
        # NO debe tener currency
        if 'currency' not in credit_payments_cols:
            self.success.append("✓ CreditPayments.currency eliminado")
            print("    ✅ currency eliminado")
        else:
            self.errors.append("✗ CreditPayments.currency aún existe")
            print("    ❌ currency aún existe")
        
        # NO debe tener amount_ves
        if 'amount_ves' not in credit_payments_cols:
            self.success.append("✓ CreditPayments.amount_ves eliminado")
            print("    ✅ amount_ves eliminado")
        else:
            self.errors.append("✗ CreditPayments.amount_ves aún existe")
            print("    ❌ amount_ves aún existe")
        
        print()
    
    def verify_data_integrity(self):
        """Verificar integridad de datos migrados"""
        print("🔍 Verificando integridad de datos...\n")
        
        # ============================================================================
        # PRODUCTS: Verificar precios válidos
        # ============================================================================
        print("  📦 Verificando Products:")
        products = self.db.query(Product).all()
        
        invalid_prices = []
        for product in products:
            if product.price <= 0:
                invalid_prices.append(f"{product.id} ({product.name}): ${product.price}")
        
        if not invalid_prices:
            self.success.append("✓ Todos los productos tienen precios válidos")
            print(f"    ✅ {len(products)} productos con precios válidos")
        else:
            self.errors.append(f"✗ {len(invalid_prices)} productos con precios inválidos")
            print(f"    ❌ {len(invalid_prices)} productos con precios inválidos:")
            for invalid in invalid_prices[:5]:  # Mostrar solo primeros 5
                print(f"       - {invalid}")
        
        # ============================================================================
        # ORDERS: Verificar totales y payment_currency
        # ============================================================================
        print("\n  📋 Verificando Orders:")
        orders = self.db.query(Order).all()
        
        invalid_orders = []
        null_payment_currency = []
        
        for order in orders:
            if order.total <= 0:
                invalid_orders.append(f"{order.id}: ${order.total}")
            if order.payment_currency is None:
                null_payment_currency.append(order.id)
        
        if not invalid_orders:
            self.success.append("✓ Todas las órdenes tienen totales válidos")
            print(f"    ✅ {len(orders)} órdenes con totales válidos")
        else:
            self.errors.append(f"✗ {len(invalid_orders)} órdenes con totales inválidos")
            print(f"    ❌ {len(invalid_orders)} órdenes con totales inválidos")
        
        if not null_payment_currency:
            self.success.append("✓ Todas las órdenes tienen payment_currency")
            print(f"    ✅ Todas las órdenes tienen payment_currency")
        else:
            self.errors.append(f"✗ {len(null_payment_currency)} órdenes sin payment_currency")
            print(f"    ❌ {len(null_payment_currency)} órdenes sin payment_currency")
        
        # ============================================================================
        # CREDIT_PAYMENTS: Verificar amounts y payment_currency
        # ============================================================================
        print("\n  💳 Verificando CreditPayments:")
        credit_payments = self.db.query(CreditPayment).all()
        
        invalid_payments = []
        null_payment_currency_payments = []
        
        for payment in credit_payments:
            if payment.amount <= 0:
                invalid_payments.append(f"{payment.id}: ${payment.amount}")
            if payment.payment_currency is None:
                null_payment_currency_payments.append(payment.id)
        
        if not invalid_payments:
            self.success.append("✓ Todos los pagos tienen amounts válidos")
            print(f"    ✅ {len(credit_payments)} pagos con amounts válidos")
        else:
            self.errors.append(f"✗ {len(invalid_payments)} pagos con amounts inválidos")
            print(f"    ❌ {len(invalid_payments)} pagos con amounts inválidos")
        
        if not null_payment_currency_payments:
            self.success.append("✓ Todos los pagos tienen payment_currency")
            print(f"    ✅ Todos los pagos tienen payment_currency")
        else:
            self.errors.append(f"✗ {len(null_payment_currency_payments)} pagos sin payment_currency")
            print(f"    ❌ {len(null_payment_currency_payments)} pagos sin payment_currency")
        
        print()
    
    def compare_with_backup(self):
        """Comparar con datos de backup exportados"""
        print("🔍 Comparando con backup pre-migración...\n")
        
        backup_dir = 'backup'
        if not os.path.exists(backup_dir):
            self.warnings.append("⚠ No se encontró directorio de backup")
            print("  ⚠️  No se encontró directorio de backup\n")
            return
        
        # ============================================================================
        # PRODUCTS: Comparar conteo
        # ============================================================================
        products_backup_file = os.path.join(backup_dir, 'products_backup.csv')
        if os.path.exists(products_backup_file):
            with open(products_backup_file, 'r', encoding='utf-8') as f:
                backup_count = sum(1 for line in f) - 1  # -1 para header
            
            current_count = self.db.query(Product).count()
            
            if backup_count == current_count:
                self.success.append(f"✓ Products: {current_count} registros (igual que backup)")
                print(f"  ✅ Products: {current_count} registros (igual que backup)")
            else:
                self.warnings.append(f"⚠ Products: backup={backup_count}, actual={current_count}")
                print(f"  ⚠️  Products: backup={backup_count}, actual={current_count}")
        
        # ============================================================================
        # ORDERS: Comparar conteo
        # ============================================================================
        orders_backup_file = os.path.join(backup_dir, 'orders_backup.csv')
        if os.path.exists(orders_backup_file):
            with open(orders_backup_file, 'r', encoding='utf-8') as f:
                backup_count = sum(1 for line in f) - 1
            
            current_count = self.db.query(Order).count()
            
            if backup_count == current_count:
                self.success.append(f"✓ Orders: {current_count} registros (igual que backup)")
                print(f"  ✅ Orders: {current_count} registros (igual que backup)")
            else:
                self.warnings.append(f"⚠ Orders: backup={backup_count}, actual={current_count}")
                print(f"  ⚠️  Orders: backup={backup_count}, actual={current_count}")
        
        print()
    
    def generate_report(self):
        """Generar reporte final"""
        print("="*80)
        print("📊 REPORTE DE VERIFICACIÓN")
        print("="*80 + "\n")
        
        print(f"✅ Verificaciones exitosas: {len(self.success)}")
        print(f"⚠️  Advertencias: {len(self.warnings)}")
        print(f"❌ Errores: {len(self.errors)}")
        
        if self.errors:
            print("\n" + "="*80)
            print("❌ ERRORES ENCONTRADOS:")
            print("="*80)
            for error in self.errors:
                print(f"  • {error}")
        
        if self.warnings:
            print("\n" + "="*80)
            print("⚠️  ADVERTENCIAS:")
            print("="*80)
            for warning in self.warnings:
                print(f"  • {warning}")
        
        print("\n" + "="*80)
        if not self.errors:
            print("✅ MIGRACIÓN VERIFICADA EXITOSAMENTE")
            print("="*80)
            print("\nEl sistema ahora opera completamente en USD.")
            print("Todos los datos han sido migrados correctamente.\n")
        else:
            print("❌ MIGRACIÓN CON ERRORES")
            print("="*80)
            print("\nPor favor revise los errores anteriores.")
            print("Considere restaurar el backup si es necesario.\n")
        
        # Guardar reporte
        report_file = f"backup/migration_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("REPORTE DE VERIFICACIÓN - MIGRACIÓN USD\n")
            f.write("="*80 + "\n\n")
            f.write(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"Éxitos: {len(self.success)}\n")
            f.write(f"Advertencias: {len(self.warnings)}\n")
            f.write(f"Errores: {len(self.errors)}\n\n")
            
            if self.errors:
                f.write("ERRORES:\n")
                for error in self.errors:
                    f.write(f"  • {error}\n")
                f.write("\n")
            
            if self.warnings:
                f.write("ADVERTENCIAS:\n")
                for warning in self.warnings:
                    f.write(f"  • {warning}\n")
                f.write("\n")
            
            f.write("ÉXITOS:\n")
            for success in self.success:
                f.write(f"  • {success}\n")
        
        print(f"📄 Reporte guardado en: {report_file}\n")


if __name__ == "__main__":
    verifier = MigrationVerifier()
    success = verifier.verify_all()
    
    # Exit code: 0 si todo OK, 1 si hay errores
    sys.exit(0 if success else 1)

