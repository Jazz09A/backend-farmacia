"""
Servicio para consultar facturas y pagos desde DEMOA (SourceSystem)
"""
from typing import List, Optional, Dict, Any
from decimal import Decimal
from datetime import datetime
from app.services.source_system_service import source_system_service
from app.config.logging_config import get_logger

logger = get_logger(__name__)


class DEMOAInvoiceService:
    """Servicio para consultar facturas y pagos desde DEMOA"""
    
    def __init__(self):
        # Reutilizamos la conexión del source_system_service ya que es la misma base de datos
        pass
    
    def get_customer_code_by_email(self, email: str) -> Optional[str]:
        """
        Obtiene el código de cliente en DEMOA por email
        El código se normaliza (sin espacios) antes de devolverlo.
        
        Args:
            email: Email del cliente
            
        Returns:
            Código de cliente (co_cli) normalizado o None si no se encuentra
        """
        try:
            customer = source_system_service.get_customer_by_email(email)
            if customer:
                customer_code = customer.get('customer_code')
                # Normalizar el código antes de devolverlo
                if customer_code:
                    return (customer_code or '').strip()
            return None
        except Exception as e:
            logger.error(f"Error obteniendo código de cliente por email {email}: {e}")
            return None
    
    def get_all_invoices(self, customer_code: str) -> List[Dict]:
        """
        Obtiene todas las facturas de un cliente (pagadas y pendientes)
        Consulta optimizada usando RTRIM para normalizar códigos de cliente.
        
        Args:
            customer_code: Código de cliente en DEMOA (ya normalizado sin espacios)
            
        Returns:
            Lista de facturas
        """
        try:
            # Normalizar el código de cliente
            normalized_code = (customer_code or '').strip()
            if not normalized_code:
                logger.warning("Código de cliente vacío")
                return []
            
            conn = source_system_service.get_connection()
            cursor = conn.cursor()
            
            # Consulta optimizada usando RTRIM para normalizar espacios en co_cli
            query = """
            SELECT 
                fv.doc_num AS invoice_number,
                fv.fec_emis AS emission_date,
                fv.fec_venc AS due_date,
                fv.total_neto AS total_amount,
                fv.saldo AS balance,
                (fv.total_neto - fv.saldo) AS amount_paid,
                ISNULL(m.mone_des, 'Bolívares') AS currency,
                CASE 
                    WHEN fv.saldo > 0 THEN 'pending'
                    WHEN fv.saldo = 0 THEN 'paid'
                END AS status,
                CASE 
                    WHEN fv.saldo = 0 THEN 'active'
                    WHEN fv.saldo > 0 AND fv.fec_venc < GETDATE() THEN 'requires_attention'
                    WHEN fv.saldo > 0 THEN 'processing'
                    ELSE 'active'
                END AS order_status,
                CASE WHEN fv.impresa = 1 THEN 1 ELSE 0 END AS is_printed
            FROM saFacturaVenta fv
            LEFT JOIN saMoneda m ON fv.co_mone = m.co_mone
            WHERE RTRIM(fv.co_cli) = %s
                AND fv.anulado = 0
            ORDER BY fv.fec_emis DESC
            """
            
            cursor.execute(query, (normalized_code,))
            invoices = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            return self._transform_invoices(invoices)
        except Exception as e:
            logger.error(f"Error obteniendo facturas para cliente {customer_code}: {e}", exc_info=True)
            return []
    
    def get_pending_invoices(self, customer_code: str) -> List[Dict]:
        """
        Obtiene facturas pendientes de pago
        Consulta optimizada usando RTRIM para normalizar códigos de cliente.
        
        Args:
            customer_code: Código de cliente en DEMOA (ya normalizado sin espacios)
            
        Returns:
            Lista de facturas pendientes
        """
        try:
            # Normalizar el código de cliente
            normalized_code = (customer_code or '').strip()
            if not normalized_code:
                logger.warning("Código de cliente vacío")
                return []
            
            conn = source_system_service.get_connection()
            cursor = conn.cursor()
            
            # Consulta optimizada usando RTRIM para normalizar espacios en co_cli
            query = """
            SELECT 
                fv.doc_num AS invoice_number,
                fv.fec_emis AS emission_date,
                fv.fec_venc AS due_date,
                fv.total_neto AS total_amount,
                fv.saldo AS balance,
                (fv.total_neto - fv.saldo) AS amount_paid,
                ISNULL(m.mone_des, 'Bolívares') AS currency,
                'pending' AS status,
                CASE 
                    WHEN fv.fec_venc < GETDATE() THEN 'requires_attention'
                    ELSE 'processing'
                END AS order_status,
                CASE WHEN fv.impresa = 1 THEN 1 ELSE 0 END AS is_printed
            FROM saFacturaVenta fv
            LEFT JOIN saMoneda m ON fv.co_mone = m.co_mone
            WHERE RTRIM(fv.co_cli) = %s
                AND fv.anulado = 0
                AND fv.saldo > 0
            ORDER BY fv.fec_emis DESC
            """
            
            cursor.execute(query, (normalized_code,))
            invoices = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            return self._transform_invoices(invoices)
        except Exception as e:
            logger.error(f"Error obteniendo facturas pendientes para cliente {customer_code}: {e}", exc_info=True)
            return []
    
    def get_paid_invoices(self, customer_code: str) -> List[Dict]:
        """
        Obtiene facturas pagadas
        Consulta optimizada usando RTRIM para normalizar códigos de cliente.
        
        Args:
            customer_code: Código de cliente en DEMOA (ya normalizado sin espacios)
            
        Returns:
            Lista de facturas pagadas
        """
        try:
            # Normalizar el código de cliente
            normalized_code = (customer_code or '').strip()
            if not normalized_code:
                logger.warning("Código de cliente vacío")
                return []
            
            conn = source_system_service.get_connection()
            cursor = conn.cursor()
            
            # Consulta optimizada usando RTRIM para normalizar espacios en co_cli
            query = """
            SELECT 
                fv.doc_num AS invoice_number,
                fv.fec_emis AS emission_date,
                fv.fec_venc AS due_date,
                fv.total_neto AS total_amount,
                fv.saldo AS balance,
                (fv.total_neto - fv.saldo) AS amount_paid,
                ISNULL(m.mone_des, 'Bolívares') AS currency,
                'paid' AS status,
                'active' AS order_status,
                CASE WHEN fv.impresa = 1 THEN 1 ELSE 0 END AS is_printed
            FROM saFacturaVenta fv
            LEFT JOIN saMoneda m ON fv.co_mone = m.co_mone
            WHERE RTRIM(fv.co_cli) = %s
                AND fv.anulado = 0
                AND fv.saldo = 0
            ORDER BY fv.fec_emis DESC
            """
            
            cursor.execute(query, (normalized_code,))
            invoices = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            return self._transform_invoices(invoices)
        except Exception as e:
            logger.error(f"Error obteniendo facturas pagadas para cliente {customer_code}: {e}", exc_info=True)
            return []
    
    def get_invoice_details(self, invoice_number: str, customer_code: Optional[str] = None) -> Optional[Dict]:
        """
        Obtiene detalles de una factura específica, incluyendo items
        
        Args:
            invoice_number: Número de factura
            customer_code: Código de cliente (opcional, para validación)
            
        Returns:
            Diccionario con detalles de la factura o None si no se encuentra
        """
        try:
            conn = source_system_service.get_connection()
            cursor = conn.cursor()
            
            # Primero obtener el header de la factura
            header_query = """
            SELECT 
                fv.doc_num AS invoice_number,
                fv.co_cli AS customer_code,
                fv.fec_emis AS emission_date,
                fv.fec_venc AS due_date,
                fv.total_neto AS total_amount,
                fv.saldo AS balance,
                (fv.total_neto - fv.saldo) AS amount_paid,
                ISNULL(m.mone_des, 'Bolívares') AS currency,
                CASE 
                    WHEN fv.saldo > 0 THEN 'pending'
                    WHEN fv.saldo = 0 THEN 'paid'
                END AS status,
                CASE 
                    WHEN fv.saldo = 0 THEN 'active'
                    WHEN fv.saldo > 0 AND fv.fec_venc < GETDATE() THEN 'requires_attention'
                    WHEN fv.saldo > 0 THEN 'processing'
                    ELSE 'active'
                END AS order_status,
                CASE WHEN fv.impresa = 1 THEN 1 ELSE 0 END AS is_printed
            FROM saFacturaVenta fv
            LEFT JOIN saMoneda m ON fv.co_mone = m.co_mone
            WHERE fv.doc_num = %s
                AND fv.anulado = 0
            """
            
            cursor.execute(header_query, (invoice_number,))
            header = cursor.fetchone()
            
            if not header:
                cursor.close()
                conn.close()
                return None
            
            # Validar que la factura pertenece al cliente si se proporciona customer_code
            if customer_code:
                normalized_customer_code = (customer_code or '').strip()
                header_customer_code = (header.get('customer_code') or '').strip()
                if normalized_customer_code and header_customer_code != normalized_customer_code:
                    cursor.close()
                    conn.close()
                    return None
            
            # Obtener items de la factura
            items_query = """
            SELECT 
                fvr.reng_num AS line_number,
                -- No exponemos el código; resolvemos el nombre del artículo
                ISNULL(fvr.des_art, sa.art_des) AS product_name,
                fvr.total_art AS quantity,
                fvr.prec_vta AS unit_price,
                ISNULL(fvr.monto_desc, 0) AS discount_amount,
                ISNULL(fvr.monto_imp, 0) AS tax_amount,
                fvr.reng_neto AS line_total
            FROM saFacturaVentaReng fvr
            LEFT JOIN saArticulo sa ON sa.co_art = fvr.co_art
            WHERE fvr.doc_num = %s
            ORDER BY fvr.reng_num
            """
            
            cursor.execute(items_query, (invoice_number,))
            items = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            # Transformar header
            invoice_data = self._transform_invoice_header(header)
            
            # Transformar items
            invoice_data['items'] = self._transform_invoice_items(items)
            
            return invoice_data
        except Exception as e:
            logger.error(f"Error obteniendo detalles de factura {invoice_number}: {e}")
            return None
    
    def get_payment_history(self, customer_code: str) -> List[Dict]:
        """
        Obtiene historial de pagos aplicados a facturas
        Consulta optimizada usando RTRIM para normalizar códigos de cliente.
        
        Args:
            customer_code: Código de cliente en DEMOA (ya normalizado sin espacios)
            
        Returns:
            Lista de pagos
        """
        try:
            # Normalizar el código de cliente
            normalized_code = (customer_code or '').strip()
            if not normalized_code:
                logger.warning("Código de cliente vacío")
                return []
            
            conn = source_system_service.get_connection()
            cursor = conn.cursor()
            
            # Consulta optimizada usando RTRIM para normalizar espacios en co_cli
            query = """
            SELECT 
                c.cob_num AS payment_number,
                c.fecha AS payment_date,
                c.monto AS total_payment_amount,
                cd.nro_doc AS invoice_number,
                cd.mont_cob AS amount_applied
            FROM saCobro c
            INNER JOIN saCobroDocReng cd ON c.cob_num = cd.cob_num
            INNER JOIN saFacturaVenta fv ON cd.nro_doc = fv.doc_num
            WHERE RTRIM(c.co_cli) = %s
                AND c.anulado = 0
                AND fv.anulado = 0
            ORDER BY c.fecha DESC, fv.doc_num
            """
            
            cursor.execute(query, (normalized_code,))
            payments = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            return self._transform_payments(payments)
        except Exception as e:
            logger.error(f"Error obteniendo historial de pagos para cliente {customer_code}: {e}", exc_info=True)
            return []
    
    def get_invoices_summary(self, customer_code: str) -> Dict:
        """
        Obtiene resumen de facturas del cliente
        Consulta optimizada usando RTRIM para normalizar códigos de cliente.
        
        Args:
            customer_code: Código de cliente en DEMOA (ya normalizado sin espacios)
            
        Returns:
            Diccionario con resumen de facturas
        """
        try:
            # Normalizar el código de cliente
            normalized_code = (customer_code or '').strip()
            if not normalized_code:
                logger.warning("Código de cliente vacío")
                return {
                    'total_invoices': 0,
                    'pending_invoices': 0,
                    'paid_invoices': 0,
                    'total_pending_amount': Decimal('0.00'),
                    'total_invoiced': Decimal('0.00')
                }
            
            conn = source_system_service.get_connection()
            cursor = conn.cursor()
            
            # Consulta optimizada usando RTRIM para normalizar espacios en co_cli
            query = """
            SELECT 
                COUNT(*) AS total_invoices,
                COUNT(CASE WHEN saldo > 0 THEN 1 END) AS pending_invoices,
                COUNT(CASE WHEN saldo = 0 THEN 1 END) AS paid_invoices,
                SUM(CASE WHEN saldo > 0 THEN saldo ELSE 0 END) AS total_pending_amount,
                SUM(total_neto) AS total_invoiced
            FROM saFacturaVenta
            WHERE RTRIM(co_cli) = %s
                AND anulado = 0
            """
            
            cursor.execute(query, (normalized_code,))
            summary = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            if summary:
                return {
                    'total_invoices': summary.get('total_invoices', 0) or 0,
                    'pending_invoices': summary.get('pending_invoices', 0) or 0,
                    'paid_invoices': summary.get('paid_invoices', 0) or 0,
                    'total_pending_amount': Decimal(str(summary.get('total_pending_amount', 0) or 0)),
                    'total_invoiced': Decimal(str(summary.get('total_invoiced', 0) or 0))
                }
            
            return {
                'total_invoices': 0,
                'pending_invoices': 0,
                'paid_invoices': 0,
                'total_pending_amount': Decimal('0.00'),
                'total_invoiced': Decimal('0.00')
            }
        except Exception as e:
            logger.error(f"Error obteniendo resumen de facturas para cliente {customer_code}: {e}", exc_info=True)
            return {
                'total_invoices': 0,
                'pending_invoices': 0,
                'paid_invoices': 0,
                'total_pending_amount': Decimal('0.00'),
                'total_invoiced': Decimal('0.00')
            }
    
    def _transform_invoices(self, invoices: List[Dict]) -> List[Dict]:
        """Transforma facturas de DEMOA al formato del sistema"""
        transformed = []
        for inv in invoices:
            transformed.append(self._transform_invoice_header(inv))
        return transformed
    
    def _transform_invoice_header(self, invoice: Dict) -> Dict:
        """Transforma el header de una factura"""
        return {
            'invoice_number': str(invoice.get('invoice_number', '')),
            'emission_date': invoice.get('emission_date'),
            'due_date': invoice.get('due_date'),
            'total_amount': Decimal(str(invoice.get('total_amount', 0) or 0)),
            'balance': Decimal(str(invoice.get('balance', 0) or 0)),
            'amount_paid': Decimal(str(invoice.get('amount_paid', 0) or 0)),
            'currency': invoice.get('currency', 'Bolívares'),
            'status': invoice.get('status', 'pending'),
            'order_status': invoice.get('order_status', 'active'),
            'is_printed': bool(invoice.get('is_printed', 0))
        }
    
    def _transform_invoice_items(self, items: List[Dict]) -> List[Dict]:
        """Transforma items de factura sin exponer códigos, con nombre del artículo"""
        transformed = []
        for item in items:
            transformed.append({
                'line_number': item.get('line_number', 0),
                'product_name': str(item.get('product_name') or ''),
                'product_barcode': str(item.get('product_barcode') or ''),
                'quantity': Decimal(str(item.get('quantity', 0) or 0)),
                'unit_price': Decimal(str(item.get('unit_price', 0) or 0)),
                'discount_amount': Decimal(str(item.get('discount_amount', 0) or 0)),
                'tax_amount': Decimal(str(item.get('tax_amount', 0) or 0)),
                'line_total': Decimal(str(item.get('line_total', 0) or 0))
            })
        return transformed
    
    def _transform_payments(self, payments: List[Dict]) -> List[Dict]:
        """Transforma pagos de DEMOA al formato del sistema"""
        transformed = []
        for payment in payments:
            transformed.append({
                'payment_number': str(payment.get('payment_number', '')),
                'payment_date': payment.get('payment_date'),
                'total_payment_amount': Decimal(str(payment.get('total_payment_amount', 0) or 0)),
                'invoice_number': str(payment.get('invoice_number', '')),
                'amount_applied': Decimal(str(payment.get('amount_applied', 0) or 0))
            })
        return transformed

