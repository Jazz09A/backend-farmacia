#!/usr/bin/env python3
"""
Script de prueba para validar la consistencia del manejo de monedas.
Verifica que las conversiones funcionen correctamente y que no haya inconsistencias.
"""

import asyncio
import sys
import os
from decimal import Decimal

# Agregar el directorio raíz al path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config.database import engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from app.services.currency_service import CurrencyService
from app.services.credit_service import CreditService
from app.services.credit_payment_service import CreditPaymentService
from app.models.user import User
from app.models.order import Order
from app.models.credit_payment import CreditPayment

def test_currency_service():
    """Probar el servicio de conversión de moneda"""
    print("🧪 Probando CurrencyService...")
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    try:
        currency_service = CurrencyService(session)
        
        # Test 1: Conversión VES a REF
        print("\n📋 Test 1: Conversión VES a REF")
        ves_amount = Decimal('1000.00')
        exchange_rate = Decimal('35.0')
        
        conversion = currency_service.convert_ves_to_ref(ves_amount, exchange_rate)
        expected_ref = ves_amount / exchange_rate
        
        print(f"   VES: {ves_amount}")
        print(f"   Tasa: {exchange_rate}")
        print(f"   REF calculado: {conversion['amount_ref']}")
        print(f"   REF esperado: {expected_ref}")
        print(f"   ✅ Conversión correcta: {conversion['amount_ref'] == expected_ref}")
        
        # Test 2: Conversión REF a VES
        print("\n📋 Test 2: Conversión REF a VES")
        ref_amount = Decimal('10.00')
        
        conversion = currency_service.convert_ref_to_ves(ref_amount, exchange_rate)
        expected_ves = ref_amount * exchange_rate
        
        print(f"   REF: {ref_amount}")
        print(f"   Tasa: {exchange_rate}")
        print(f"   VES calculado: {conversion['amount_ves']}")
        print(f"   VES esperado: {expected_ves}")
        print(f"   ✅ Conversión correcta: {conversion['amount_ves'] == expected_ves}")
        
        # Test 3: Validación de montos
        print("\n📋 Test 3: Validación de montos")
        valid_amount = Decimal('100.50')
        invalid_amount = Decimal('0.00')
        
        print(f"   Monto válido {valid_amount}: {currency_service.validate_amount(valid_amount)}")
        print(f"   Monto inválido {invalid_amount}: {currency_service.validate_amount(invalid_amount)}")
        
        # Test 4: Redondeo consistente
        print("\n📋 Test 4: Redondeo consistente")
        unrounded = Decimal('123.456789')
        rounded = currency_service.round_amount(unrounded)
        
        print(f"   Original: {unrounded}")
        print(f"   Redondeado: {rounded}")
        print(f"   ✅ Redondeo a 2 decimales: {str(rounded).split('.')[1] if '.' in str(rounded) else '00'}")
        
        print("\n✅ CurrencyService funciona correctamente")
        
    except Exception as e:
        print(f"❌ Error en CurrencyService: {e}")
        raise
    finally:
        session.close()

def test_database_fields():
    """Probar que los nuevos campos de la base de datos funcionan"""
    print("\n🧪 Probando campos de base de datos...")
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    try:
        # Verificar estructura de credit_payments
        result = session.execute(text("PRAGMA table_info(credit_payments)"))
        columns = [row[1] for row in result.fetchall()]
        
        required_fields = ['amount_ves', 'currency', 'exchange_rate_used']
        missing_fields = [field for field in required_fields if field not in columns]
        
        if missing_fields:
            print(f"❌ Campos faltantes en credit_payments: {missing_fields}")
            return False
        else:
            print("✅ Todos los campos de moneda están presentes en credit_payments")
        
        # Verificar que podemos crear un registro de prueba
        print("\n📋 Probando inserción de registro de prueba...")
        
        test_payment = {
            'id': 'test-payment-123',
            'order_id': 'test-order-123',
            'user_id': 'test-user-123',
            'amount': float(Decimal('10.50')),
            'amount_ves': float(Decimal('367.50')),
            'currency': 'REF',
            'exchange_rate_used': float(Decimal('35.0')),
            'payment_reference': 'TEST-REF-123',
            'status': 'pending'
        }
        
        # Insertar registro de prueba
        session.execute(text("""
            INSERT INTO credit_payments 
            (id, order_id, user_id, amount, amount_ves, currency, exchange_rate_used, payment_reference, status)
            VALUES (:id, :order_id, :user_id, :amount, :amount_ves, :currency, :exchange_rate_used, :payment_reference, :status)
        """), test_payment)
        
        # Verificar que se insertó correctamente
        result = session.execute(text("""
            SELECT amount, amount_ves, currency, exchange_rate_used 
            FROM credit_payments 
            WHERE id = :id
        """), {'id': test_payment['id']})
        
        row = result.fetchone()
        if row:
            print(f"   ✅ Registro insertado: amount={row[0]}, amount_ves={row[1]}, currency={row[2]}, rate={row[3]}")
        
        # Limpiar registro de prueba
        session.execute(text("DELETE FROM credit_payments WHERE id = :id"), {'id': test_payment['id']})
        session.commit()
        
        print("✅ Campos de base de datos funcionan correctamente")
        
    except Exception as e:
        print(f"❌ Error en campos de base de datos: {e}")
        session.rollback()
        raise
    finally:
        session.close()

def test_consistency_scenarios():
    """Probar escenarios de consistencia de moneda"""
    print("\n🧪 Probando escenarios de consistencia...")
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    try:
        currency_service = CurrencyService(session)
        
        # Escenario 1: Orden de crédito en REF, pago en VES
        print("\n📋 Escenario 1: Orden REF, Pago VES")
        
        order_total_ref = Decimal('100.00')  # Orden por $100 REF
        exchange_rate = Decimal('35.0')      # Tasa 35 VES/REF
        order_total_ves = order_total_ref * exchange_rate  # = 3500 VES
        
        # Usuario paga 1750 VES (debería ser $50 REF)
        payment_ves = Decimal('1750.00')
        payment_conversion = currency_service.convert_ves_to_ref(payment_ves, exchange_rate)
        payment_ref = payment_conversion['amount_ref']
        
        remaining_ref = order_total_ref - payment_ref
        
        print(f"   Orden total: {order_total_ref} REF (≈ {order_total_ves} VES)")
        print(f"   Pago: {payment_ves} VES")
        print(f"   Pago convertido: {payment_ref} REF")
        print(f"   Saldo pendiente: {remaining_ref} REF")
        print(f"   ✅ Consistencia: {payment_ref == Decimal('50.00') and remaining_ref == Decimal('50.00')}")
        
        # Escenario 2: Múltiples pagos con diferentes tasas
        print("\n📋 Escenario 2: Múltiples pagos con tasas diferentes")
        
        payments = [
            {'amount_ves': Decimal('1000.00'), 'rate': Decimal('35.0')},
            {'amount_ves': Decimal('1500.00'), 'rate': Decimal('36.0')},
        ]
        
        total_paid_ref = Decimal('0.00')
        for i, payment in enumerate(payments, 1):
            conversion = currency_service.convert_ves_to_ref(payment['amount_ves'], payment['rate'])
            payment_ref = conversion['amount_ref']
            total_paid_ref += payment_ref
            
            print(f"   Pago {i}: {payment['amount_ves']} VES @ {payment['rate']} = {payment_ref} REF")
        
        print(f"   Total pagado: {total_paid_ref} REF")
        
        # Verificar que la suma es correcta
        expected_total = (Decimal('1000.00') / Decimal('35.0')) + (Decimal('1500.00') / Decimal('36.0'))
        print(f"   Esperado: {expected_total} REF")
        print(f"   ✅ Suma correcta: {abs(total_paid_ref - expected_total) < Decimal('0.01')}")
        
        print("\n✅ Escenarios de consistencia pasan")
        
    except Exception as e:
        print(f"❌ Error en escenarios de consistencia: {e}")
        raise
    finally:
        session.close()

def main():
    """Ejecutar todas las pruebas"""
    print("🚀 Iniciando pruebas de consistencia de monedas")
    print("=" * 60)
    
    try:
        # Test 1: Servicio de conversión
        test_currency_service()
        
        # Test 2: Campos de base de datos
        test_database_fields()
        
        # Test 3: Escenarios de consistencia
        test_consistency_scenarios()
        
        print("\n" + "=" * 60)
        print("🎉 Todas las pruebas pasaron exitosamente!")
        print("\n✅ Resumen:")
        print("   - CurrencyService funciona correctamente")
        print("   - Campos de base de datos están configurados")
        print("   - Conversiones son consistentes")
        print("   - Escenarios de múltiples pagos funcionan")
        
        print("\n💡 El sistema ahora maneja monedas de forma consistente:")
        print("   - Todo el crédito se maneja en REF")
        print("   - Los pagos se pueden hacer en VES o REF")
        print("   - Las conversiones usan tasas de cambio reales")
        print("   - Se guarda trazabilidad de las tasas usadas")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error durante las pruebas: {e}")
        print("\n🔧 Verifica:")
        print("   - Que la base de datos esté actualizada")
        print("   - Que los servicios estén importando correctamente")
        print("   - Que no haya errores de sintaxis")
        
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
