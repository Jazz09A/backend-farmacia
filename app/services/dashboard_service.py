from datetime import timedelta

# from app.schemas.order import PaymentStatusEnum
# from app.schemas.order import UpdatePaymentStatus
from decimal import Decimal

# Order schemas eliminados - Order no se usa con Profit Plus
# from app.schemas.order import OrderStatus
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

# Order models eliminados - Order no se usa con Profit Plus
# from app.models.order import Order
# from app.models.order_discount import OrderDiscount
from app.config.logging_config import get_logger
from app.models.user import User
from app.schemas.dashboard import (
    DashboardData,
    DashboardStats,
    DiscountBreakdown,
    OrderStatusSummary,
    RecentOrder,
)
from app.services.source_system_service import source_system_service
from app.utils.timezone import VENEZUELA_TZ, get_ve_now

# OrderDiscount schemas eliminados - Order no se usa con Profit Plus
# from app.schemas.order_discount import OrderDiscountSummary, OrderDiscountResponse

orders_logger = get_logger("orders")


def _map_quote_status_to_dashboard_status(status: str, anulado: int) -> str:
    """
    Mapea el estado de una cotización de Profit Plus al estado del dashboard.
    
    Args:
        status: Estado de la cotización ('0', '1', '2')
        anulado: Flag de anulado (0 o 1)
        
    Returns:
        Estado del dashboard: 'pending', 'confirmed', 'processing', 'cancelled'
    """
    # Si está anulado, siempre es cancelled
    if anulado == 1:
        return 'cancelled'
    
    # Mapear según el status
    if status == '0':
        return 'pending'  # Pendiente/Abierta
    elif status == '1':
        return 'confirmed'  # Procesada/Cerrada
    elif status == '2':
        return 'processing'  # Parcialmente Procesada
    else:
        # Estado desconocido, tratar como pending
        return 'pending'


# _calculate_order_discount_info eliminado - Order no se usa con Profit Plus

def get_dashboard_data(db: Session, days_filter: int = 7) -> DashboardData:
    """
    Retrieves and computes all data required for the admin dashboard.
    Now queries directly from Profit Plus source system (saCotizacionCliente and saCliente).
    """
    perf_logger = get_logger("performance")
    error_logger = get_logger("errors")
    
    perf_logger.info(
        "Dashboard data calculation started",
        extra={
            'days_filter': days_filter, 
            'event': 'dashboard_calculation_started',
            'user_email': 'admin@farmaplus.com'  # Dashboard es accedido por admin
        }
    )
    
    try:
        # 1. Calculate date range for filtering
        end_date = get_ve_now()
        start_date = end_date - timedelta(days=days_filter)
        
        # Format dates for SQL Server (use datetime objects for proper comparison)
        # SQL Server will handle datetime comparisons correctly
        start_datetime = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_datetime = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        error_logger.info(
            f"Dashboard: Date range calculated - Start: {start_datetime.isoformat()}, End: {end_datetime.isoformat()}, Days: {days_filter}"
        )
        
        # Get connection to source system
        try:
            conn = source_system_service.get_connection()
            cursor = conn.cursor()
            error_logger.info("Dashboard: Connection to source system established")
        except Exception as conn_error:
            error_logger.error(
                f"Failed to connect to source system: {conn_error!s}",
                exc_info=True
            )
            raise
        
        # 2. Basic Stats - Usando consultas optimizadas
        # 2.1 Total revenue
        revenue_query = """
        SELECT 
            ISNULL(SUM(total_neto), 0) AS total_revenue
        FROM dbo.saFacturaVenta
        WHERE fec_emis >= %s
          AND fec_emis <= %s
          AND anulado = 0
        """
        try:
            error_logger.info(f"Dashboard: Executing revenue query with dates: {start_datetime} to {end_datetime}")
            cursor.execute(revenue_query, (start_datetime, end_datetime))
            revenue_result = cursor.fetchone()
            if revenue_result is None:
                error_logger.warning("Dashboard: Revenue query returned None")
                total_revenue = Decimal('0.00')
            else:
                total_revenue = Decimal(str(revenue_result.get('total_revenue', 0) or 0))
            error_logger.info(f"Dashboard: Total revenue = {total_revenue}")
        except Exception as query_error:
            error_logger.error(f"Dashboard: Error executing revenue query: {query_error!s}", exc_info=True)
            raise
        
        # 2.2 Total orders
        orders_query = """
        SELECT COUNT(DISTINCT doc_num) AS total_orders
        FROM dbo.saCotizacionCliente
        WHERE fec_emis >= %s
          AND fec_emis <= %s
          AND anulado = 0
          AND status IN ('0', '1', '2')
        """
        cursor.execute(orders_query, (start_datetime, end_datetime))
        orders_result = cursor.fetchone()
        total_orders = orders_result.get('total_orders', 0) or 0
        error_logger.info(f"Dashboard: Total orders = {total_orders}")
        
        # 2.3 New customers
        new_customers_query = """
        SELECT COUNT(DISTINCT co_cli) AS new_customers
        FROM dbo.saCliente
        WHERE fecha_reg >= %s
          AND fecha_reg <= %s
        """
        cursor.execute(new_customers_query, (start_datetime, end_datetime))
        new_customers_result = cursor.fetchone()
        new_customers = new_customers_result.get('new_customers', 0) or 0
        error_logger.info(f"Dashboard: New customers = {new_customers}")
        
        # 2.4 Conversion rate (optimizada con subconsultas para evitar JOIN costoso)
        # Calcular por separado para mejor rendimiento
        conversion_rate = Decimal('0.00')
        try:
            # Contar facturas en el período
            invoices_count_query = """
            SELECT COUNT(DISTINCT doc_num) AS invoice_count
            FROM dbo.saFacturaVenta
            WHERE fec_emis >= %s
              AND fec_emis <= %s
              AND anulado = 0
            """
            cursor.execute(invoices_count_query, (start_datetime, end_datetime))
            invoices_result = cursor.fetchone()
            invoice_count = invoices_result.get('invoice_count', 0) or 0 if invoices_result else 0
            
            # Usar total_orders ya calculado arriba
            if total_orders > 0:
                conversion_rate = Decimal(str(invoice_count)) / Decimal(str(total_orders)) * 100
            error_logger.info(f"Dashboard: Conversion rate = {conversion_rate}% (Invoices: {invoice_count}, Orders: {total_orders})")
        except Exception as conv_error:
            error_logger.warning(f"Dashboard: Error calculating conversion rate: {conv_error!s}")
            conversion_rate = Decimal('0.00')
        
        # 2.5 Discount statistics (optimizadas)
        # Total discounts given
        total_discounts_query = """
        SELECT 
            ISNULL(SUM(r.monto_desc), 0) AS total_discounts_given
        FROM dbo.saCotizacionCliente c
        INNER JOIN dbo.saCotizacionClienteReng r ON c.doc_num = r.doc_num
        WHERE c.fec_emis >= %s
          AND c.fec_emis <= %s
          AND c.anulado = 0
          AND r.monto_desc > 0
        """
        cursor.execute(total_discounts_query, (start_datetime, end_datetime))
        discounts_result = cursor.fetchone()
        total_discounts_given = Decimal(str(discounts_result.get('total_discounts_given', 0) or 0))
        
        # Orders with discounts
        orders_with_discounts_query = """
        SELECT 
            COUNT(DISTINCT c.doc_num) AS orders_with_discounts
        FROM dbo.saCotizacionCliente c
        INNER JOIN dbo.saCotizacionClienteReng r ON c.doc_num = r.doc_num
        WHERE c.fec_emis >= %s
          AND c.fec_emis <= %s
          AND c.anulado = 0
          AND r.monto_desc > 0
        """
        cursor.execute(orders_with_discounts_query, (start_datetime, end_datetime))
        orders_discounts_result = cursor.fetchone()
        orders_with_discounts = orders_discounts_result.get('orders_with_discounts', 0) or 0
        
        # Discount usage percentage (calculado en Python usando valores ya obtenidos)
        if total_orders > 0:
            discount_usage_percentage = float(orders_with_discounts) / float(total_orders) * 100.0
        else:
            discount_usage_percentage = 0.0
        
        # Average discount per order
        avg_discount_query = """
        SELECT 
            CASE 
                WHEN COUNT(DISTINCT c.doc_num) > 0 
                THEN ISNULL(SUM(r.monto_desc), 0) / 
                     CAST(COUNT(DISTINCT c.doc_num) AS DECIMAL(10, 2))
                ELSE 0.00
            END AS average_discount_per_order
        FROM dbo.saCotizacionCliente c
        INNER JOIN dbo.saCotizacionClienteReng r ON c.doc_num = r.doc_num
        WHERE c.fec_emis >= %s
          AND c.fec_emis <= %s
          AND c.anulado = 0
          AND r.monto_desc > 0
        """
        cursor.execute(avg_discount_query, (start_datetime, end_datetime))
        avg_discount_result = cursor.fetchone()
        average_discount_per_order = Decimal(str(avg_discount_result.get('average_discount_per_order', 0) or 0))
        
        # 2.6 Discount breakdown
        # Quantity discounts
        quantity_discounts_query = """
        SELECT 
            COUNT(DISTINCT co_desc) AS quantity_discounts
        FROM dbo.saDescArticulo
        WHERE (fecha_ini IS NULL OR fecha_ini <= GETDATE())
          AND (fecha_fin IS NULL OR fecha_fin >= GETDATE())
          AND (hasta1 > 0 OR hasta2 > 0 OR hasta3 > 0 OR hasta4 > 0 OR hasta5 > 0)
        """
        cursor.execute(quantity_discounts_query)
        quantity_discounts_result = cursor.fetchone()
        quantity_discounts = quantity_discounts_result.get('quantity_discounts', 0) or 0
        
        # Flash discounts (no identificados directamente)
        flash_discounts = 0
        
        # Coupon discounts (no identificados directamente)
        coupon_discounts = 0   
        
        # Promotional discounts
        promotional_discounts_query = """
        SELECT 
            COUNT(DISTINCT co_desc) AS promotional_discounts
        FROM dbo.saDescArticulo
        WHERE (fecha_ini IS NULL OR fecha_ini <= GETDATE())
          AND (fecha_fin IS NULL OR fecha_fin >= GETDATE())
        """
        cursor.execute(promotional_discounts_query)
        promotional_discounts_result = cursor.fetchone()
        promotional_discounts = promotional_discounts_result.get('promotional_discounts', 0) or 0
        
        # Total amount by type (simplificado - usar total_discounts_given ya calculado)
        # Esta consulta con múltiples JOINs es muy costosa, usar el valor ya calculado
        total_amount_by_type = {
            'promotional': total_discounts_given
        }
        # Si se necesita más detalle, se puede calcular después de forma asíncrona
        
        discount_breakdown = DiscountBreakdown(
            quantity_discounts=quantity_discounts,
            flash_discounts=flash_discounts,
            coupon_discounts=coupon_discounts,
            promotional_discounts=promotional_discounts,
            total_amount_by_type=total_amount_by_type
        )
        
        stats = DashboardStats(
            total_revenue=total_revenue,
            total_orders=total_orders,
            new_customers=new_customers,
            conversion_rate=conversion_rate,
            total_discounts_given=total_discounts_given,
            orders_with_discounts=orders_with_discounts,
            discount_usage_percentage=discount_usage_percentage,
            average_discount_per_order=average_discount_per_order,
        )
        
        # 5. Order Status Summary (optimizado - consultas separadas más rápidas)
        status_counts = {
            'pending': 0,
            'confirmed': 0,
            'processing': 0,
            'shipped': 0,
            'delivered': 0,
            'cancelled': 0
        }
        
        try:
            # 5.1 Cotizaciones (más rápido sin UNION ALL)
            quotes_status_query = """
            SELECT 
                CASE 
                    WHEN anulado = 1 THEN 'cancelled'
                    WHEN status = '0' THEN 'pending'
                    WHEN status = '1' THEN 'confirmed'
                    WHEN status = '2' THEN 'processing'
                    ELSE 'pending'
                END AS status_type,
                COUNT(DISTINCT doc_num) AS count
            FROM dbo.saCotizacionCliente
            WHERE fec_emis >= %s
              AND fec_emis <= %s
            GROUP BY 
                CASE 
                    WHEN anulado = 1 THEN 'cancelled'
                    WHEN status = '0' THEN 'pending'
                    WHEN status = '1' THEN 'confirmed'
                    WHEN status = '2' THEN 'processing'
                    ELSE 'pending'
                END
            """
            cursor.execute(quotes_status_query, (start_datetime, end_datetime))
            quotes_status_results = cursor.fetchall()
            for row in quotes_status_results:
                status_type = row.get('status_type', '').strip()
                count = row.get('count', 0) or 0
                if status_type in status_counts:
                    status_counts[status_type] = (status_counts.get(status_type, 0) or 0) + count
            
            # 5.2 Notas de Despacho (shipped) - solo si hay datos recientes
            try:
                dispatch_shipped_query = """
                SELECT COUNT(DISTINCT doc_num) AS count
                FROM dbo.saNotaDespachoVenta
                WHERE fec_emis >= %s
                  AND fec_emis <= %s
                  AND status = '1'
                  AND anulado = 0
                """
                cursor.execute(dispatch_shipped_query, (start_datetime, end_datetime))
                shipped_result = cursor.fetchone()
                if shipped_result:
                    status_counts['shipped'] = (status_counts.get('shipped', 0) or 0) + (shipped_result.get('count', 0) or 0)
                
                dispatch_cancelled_query = """
                SELECT COUNT(DISTINCT doc_num) AS count
                FROM dbo.saNotaDespachoVenta
                WHERE fec_emis >= %s
                  AND fec_emis <= %s
                  AND anulado = 1
                """
                cursor.execute(dispatch_cancelled_query, (start_datetime, end_datetime))
                dispatch_cancelled_result = cursor.fetchone()
                if dispatch_cancelled_result:
                    status_counts['cancelled'] = (status_counts.get('cancelled', 0) or 0) + (dispatch_cancelled_result.get('count', 0) or 0)
            except Exception as dispatch_error:
                error_logger.warning(f"Dashboard: Error querying dispatch notes: {dispatch_error!s}")
            
            # 5.3 Notas de Entrega (delivered) - solo si hay datos recientes
            try:
                delivery_delivered_query = """
                SELECT COUNT(DISTINCT doc_num) AS count
                FROM dbo.saNotaEntregaVenta
                WHERE fec_emis >= %s
                  AND fec_emis <= %s
                  AND status = '2'
                  AND anulado = 0
                """
                cursor.execute(delivery_delivered_query, (start_datetime, end_datetime))
                delivered_result = cursor.fetchone()
                if delivered_result:
                    status_counts['delivered'] = (status_counts.get('delivered', 0) or 0) + (delivered_result.get('count', 0) or 0)
                
                delivery_cancelled_query = """
                SELECT COUNT(DISTINCT doc_num) AS count
                FROM dbo.saNotaEntregaVenta
                WHERE fec_emis >= %s
                  AND fec_emis <= %s
                  AND anulado = 1
                """
                cursor.execute(delivery_cancelled_query, (start_datetime, end_datetime))
                delivery_cancelled_result = cursor.fetchone()
                if delivery_cancelled_result:
                    status_counts['cancelled'] = (status_counts.get('cancelled', 0) or 0) + (delivery_cancelled_result.get('count', 0) or 0)
            except Exception as delivery_error:
                error_logger.warning(f"Dashboard: Error querying delivery notes: {delivery_error!s}")
                
        except Exception as status_error:
            error_logger.warning(f"Dashboard: Error calculating status summary: {status_error!s}")
        
        order_status_summary = OrderStatusSummary(
            pending=status_counts['pending'],
            confirmed=status_counts['confirmed'],
            processing=status_counts['processing'],
            shipped=status_counts['shipped'],
            delivered=status_counts['delivered'],
            cancelled=status_counts['cancelled'],
        )
        
        # 6. Recent Orders (optimizada)
        recent_orders_query = """
        SELECT TOP 5
            c.doc_num AS id,
            ISNULL(cl.cli_des, 'Cliente Desconocido') AS customer_name,
            CONVERT(VARCHAR(10), c.fec_emis, 120) AS date,
            c.total_neto AS total,
            CASE 
                WHEN c.anulado = 1 THEN 'cancelled'
                WHEN c.status = '0' THEN 'pending'
                WHEN c.status = '1' THEN 'confirmed'
                WHEN c.status = '2' THEN 'processing'
                ELSE 'pending'
            END AS status
        FROM dbo.saCotizacionCliente c
        LEFT JOIN dbo.saCliente cl ON RTRIM(c.co_cli) = RTRIM(cl.co_cli)
        WHERE c.fec_emis >= %s
          AND c.fec_emis <= %s
        ORDER BY c.fec_emis DESC
        """
        cursor.execute(recent_orders_query, (start_datetime, end_datetime))
        recent_quotes = cursor.fetchall()
        
        recent_orders = []
        for quote in recent_quotes:
            quote_id = str(quote.get('id', ''))
            customer_name = quote.get('customer_name', 'Cliente Desconocido') or 'Cliente Desconocido'
            date_str = quote.get('date', '') or start_datetime.strftime("%Y-%m-%d")
            total = Decimal(str(quote.get('total', 0) or 0))
            dashboard_status = quote.get('status', 'pending') or 'pending'
            
            recent_orders.append(
                RecentOrder(
                    id=quote_id,
                    customer_name=customer_name.strip(),
                    date=date_str,
                    total=total,
                    status=dashboard_status,
                )
            )
        
        cursor.close()
        conn.close()
        
        error_logger.info(
            f"Dashboard: Final results - Revenue: {total_revenue}, Orders: {total_orders}, "
            f"Customers: {new_customers}, Conversion: {conversion_rate}, "
            f"Discounts: {total_discounts_given}, Orders with discounts: {orders_with_discounts}"
        )
        
        perf_logger.info(
            "Dashboard data calculated successfully from source system",
            extra={
                'days_filter': days_filter,
                'total_revenue': float(total_revenue),
                'total_orders': total_orders,
                'new_customers': new_customers,
                'conversion_rate': float(conversion_rate),
                'status_counts': status_counts,
                'recent_orders_count': len(recent_orders),
                'event': 'dashboard_calculation_completed',
                'user_email': 'admin@farmaplus.com'
            }
        )
        
        return DashboardData(
            stats=stats,
            order_status_summary=order_status_summary,
            recent_orders=recent_orders,
            discount_breakdown=discount_breakdown,
        )
        
    except Exception as e:
        error_logger.error(
            f"Error calculating dashboard data from source system: {e!s}",
            extra={
                'days_filter': days_filter,
                'event': 'dashboard_calculation_error',
                'user_email': 'admin@farmaplus.com',
                'error_type': type(e).__name__,
                'error_message': str(e)
            },
            exc_info=True
        )
        # In development, raise to see the error
        # In production, return empty data
        import os
        if os.getenv("ENVIRONMENT", "development") == "development":
            raise HTTPException(
                status_code=500,
                detail=f"Error calculating dashboard data: {e!s}. Check logs for details."
            )
        # Return empty/default data on error for production
        return DashboardData(
            stats=DashboardStats(
                total_revenue=Decimal('0.00'),
                total_orders=0,
                new_customers=0,
                conversion_rate=Decimal('0.00'),
                total_discounts_given=Decimal('0.00'),
                orders_with_discounts=0,
                discount_usage_percentage=0.0,
                average_discount_per_order=Decimal('0.00'),
            ),
            order_status_summary=OrderStatusSummary(
                pending=0,
                confirmed=0,
                processing=0,
                shipped=0,
                delivered=0,
                cancelled=0,
            ),
            recent_orders=[],
            discount_breakdown=DiscountBreakdown(),
        ) 
    
def get_all_quotes_paginated(
    page: int = 1,
    page_size: int = 20,
    db: Session = None
):
    """
    Obtiene todas las cotizaciones desde el sistema fuente con paginación.
    Ordenadas por fecha de emisión descendente (más reciente primero).
    
    Args:
        page: Número de página (empezando en 1)
        page_size: Tamaño de página
        db: Session de base de datos (no se usa, pero se mantiene para compatibilidad)
        
    Returns:
        Dict con results (lista de cotizaciones) y pagination (info de paginación)
    """
    from datetime import datetime

    from app.schemas.quote import Pagination, QuoteListItem, QuoteListResponse
    
    logger = get_logger("dashboard")
    
    try:
        # Validar parámetros
        page = max(1, page)
        page_size = max(1, min(100, page_size))  # Limitar entre 1 y 100
        offset = (page - 1) * page_size
        
        # Conectar al sistema fuente
        conn = source_system_service.get_connection()
        cursor = conn.cursor()
        
        # Contar total de cotizaciones (no anuladas)
        count_query = """
        SELECT COUNT(DISTINCT doc_num) AS total
        FROM dbo.saCotizacionCliente
        WHERE anulado = 0
        """
        cursor.execute(count_query)
        total_count = cursor.fetchone().get('total', 0) or 0
        
        # Calcular total de páginas
        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 0
        
        # Obtener cotizaciones con paginación, ordenadas por fecha descendente
        query = """
        SELECT 
            c.doc_num AS profit_plus_id,
            c.co_cli AS customer_code,
            ISNULL(cl.cli_des, 'Cliente Desconocido') AS customer_name,
            c.fec_emis AS emission_date,
            c.fec_venc AS expiration_date,
            c.total_neto AS total_neto,
            c.saldo AS balance,
            c.status,
            c.anulado,
            c.co_mone AS currency_code,
            ISNULL(m.mone_des, 'Bolívares') AS currency_name,
            ISNULL(item_counts.items_count, 0) AS items_count
        FROM dbo.saCotizacionCliente c
        LEFT JOIN dbo.saCliente cl ON RTRIM(c.co_cli) = RTRIM(cl.co_cli)
        LEFT JOIN dbo.saMoneda m ON c.co_mone = m.co_mone
        LEFT JOIN (
            SELECT doc_num, COUNT(*) as items_count
            FROM dbo.saCotizacionClienteReng
            GROUP BY doc_num
        ) item_counts ON c.doc_num = item_counts.doc_num
        WHERE c.anulado = 0
        ORDER BY c.fec_emis DESC
        OFFSET %s ROWS
        FETCH NEXT %s ROWS ONLY
        """
        
        cursor.execute(query, (offset, page_size))
        quotes_data = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # Transformar a QuoteListItem
        results = []
        for quote in quotes_data:
            profit_plus_id = str(quote.get('profit_plus_id', ''))
            quote_id = f"COT-{profit_plus_id}" if profit_plus_id else "COT-UNKNOWN"
            
            # Determinar status basado en balance y fecha de expiración
            balance = Decimal(str(quote.get('balance', 0) or 0))
            expiration_date = quote.get('expiration_date')
            
            # Mapear status de Profit Plus a status del schema
            str(quote.get('status', '0')).strip()
            anulado = quote.get('anulado', 0)
            
            if anulado == 1:
                status = "cancelled"
            elif balance == 0:
                status = "converted"  # Convertida a factura
            elif expiration_date:
                if isinstance(expiration_date, datetime):
                    # Convertir fecha naive a aware usando zona horaria de Venezuela
                    # Las fechas de SQL Server vienen como naive, asumimos que están en hora de Venezuela
                    if expiration_date.tzinfo is None:
                        expiration_date_aware = expiration_date.replace(tzinfo=VENEZUELA_TZ)
                    else:
                        expiration_date_aware = expiration_date
                    
                    if expiration_date_aware < get_ve_now():
                        status = "expired"
                    else:
                        status = "pending"
                else:
                    status = "pending"
            else:
                status = "pending"
            
            # Formatear fechas
            emission_date = quote.get('emission_date')
            if emission_date:
                if isinstance(emission_date, datetime):
                    emission_date_str = emission_date.isoformat()
                else:
                    emission_date_str = str(emission_date)
            else:
                emission_date_str = ""
            
            expiration_date_str = None
            if expiration_date:
                if isinstance(expiration_date, datetime):
                    expiration_date_str = expiration_date.isoformat()
                else:
                    expiration_date_str = str(expiration_date)
            
            results.append(QuoteListItem(
                quote_id=quote_id,
                profit_plus_id=profit_plus_id,
                status=status,
                created_at=emission_date_str,
                expires_at=expiration_date_str,
                total_gross=str(quote.get('total_neto', 0) or 0),
                currency=quote.get('currency_name', 'VES'),
                items_count=quote.get('items_count', 0) or 0,
                email_sent_at=emission_date_str,
            ))
        
        return QuoteListResponse(
            results=results,
            pagination=Pagination(
                page=page,
                page_size=page_size,
                total_pages=total_pages,
                total_items=total_count
            )
        )
        
    except Exception as e:
        logger.error(
            f"Error obteniendo cotizaciones paginadas: {e!s}",
            exc_info=True
        )
        # Retornar respuesta vacía en caso de error
        return QuoteListResponse(
            results=[],
            pagination=Pagination(
                page=page,
                page_size=page_size,
                total_pages=0,
                total_items=0
            )
        )


def get_quote_detail_for_admin(
    quote_id: str,
    db: Session = None
):
    """
    Obtiene el detalle completo de una cotización desde Profit Plus para administradores.
    No requiere validar que la cotización pertenezca a un usuario específico.
    
    Args:
        quote_id: ID de la cotización (formato COT-XXXXX o solo el código)
        db: Session de base de datos (no se usa, pero se mantiene para compatibilidad)
        
    Returns:
        QuoteDetailResponse con todos los detalles o None si no se encuentra
    """
    from datetime import datetime

    from app.schemas.quote import (
        QuoteDetailItem,
        QuoteDetailResponse,
        QuoteHistoryEvent,
        QuoteTotals,
    )
    
    logger = get_logger("dashboard")
    
    try:
        # Extraer profit_plus_id del quote_id (puede venir como COT-XXXXX o solo XXXXX)
        profit_plus_id = quote_id.replace("COT-", "") if quote_id.startswith("COT-") else quote_id
        profit_plus_id = profit_plus_id.strip()
        
        # Conectar al sistema fuente
        conn = source_system_service.get_connection()
        cursor = conn.cursor()
        
        # Query para obtener detalles de cotización (sin filtrar por cliente)
        query = """
        SELECT 
            c.doc_num AS profit_plus_id,
            c.co_cli AS customer_code,
            ISNULL(cl.cli_des, 'Cliente Desconocido') AS customer_name,
            c.fec_emis AS created_at,
            c.fec_emis AS emission_date,
            c.fec_venc AS expires_at,
            c.total_neto AS total_neto,
            c.saldo AS saldo,
            c.co_mone AS codigo_moneda,
            ISNULL(m.mone_des, 'Bolívares') AS currency_name,
            c.co_ven AS codigo_vendedor,
            c.status,
            c.anulado,
            r.reng_num AS line_number,
            r.co_art AS product_code,
            ISNULL(a.art_des, r.des_art) AS product_name,
            r.total_art AS quantity,
            r.prec_vta AS unit_price,
            r.monto_desc AS discount_amount,
            r.monto_imp AS tax_amount,
            r.reng_neto AS line_total,
            r.des_art AS description
        FROM dbo.saCotizacionCliente c
        LEFT JOIN dbo.saCliente cl ON RTRIM(c.co_cli) = RTRIM(cl.co_cli)
        LEFT JOIN dbo.saMoneda m ON c.co_mone = m.co_mone
        LEFT JOIN dbo.saCotizacionClienteReng r ON c.doc_num = r.doc_num
        LEFT JOIN dbo.saArticulo a ON r.co_art = a.co_art
        WHERE c.doc_num = %s
          AND c.anulado = 0
        ORDER BY r.reng_num
        """
        
        cursor.execute(query, (profit_plus_id,))
        all_data = cursor.fetchall()
        
        if not all_data:
            cursor.close()
            conn.close()
            logger.warning(f"Cotización {profit_plus_id} no encontrada")
            return None
        
        # El primer registro contiene la información del encabezado
        first_row = all_data[0]
        header = {
            'profit_plus_id': first_row.get('profit_plus_id'),
            'customer_code': first_row.get('customer_code'),
            'customer_name': first_row.get('customer_name'),
            'created_at': first_row.get('created_at'),
            'emission_date': first_row.get('emission_date'),
            'expires_at': first_row.get('expires_at'),
            'total_neto': first_row.get('total_neto'),
            'saldo': first_row.get('saldo'),
            'codigo_moneda': first_row.get('codigo_moneda'),
            'currency_name': first_row.get('currency_name'),
            'codigo_vendedor': first_row.get('codigo_vendedor'),
            'status': first_row.get('status'),
            'anulado': first_row.get('anulado'),
        }
        
        # Todos los registros contienen los items (puede haber múltiples renglones)
        items_data = []
        for row in all_data:
            if row.get('product_code'):  # Solo agregar si tiene artículo
                items_data.append({
                    'line_number': row.get('line_number'),
                    'product_code': row.get('product_code'),
                    'product_name': row.get('product_name'),
                    'quantity': row.get('quantity'),
                    'unit_price': row.get('unit_price'),
                    'discount_amount': row.get('discount_amount'),
                    'tax_amount': row.get('tax_amount'),
                    'line_total': row.get('line_total'),
                    'description': row.get('description'),
                })
        
        cursor.close()
        conn.close()
        
        # Transformar items
        items = []
        total_discount = Decimal('0.00')
        total_tax = Decimal('0.00')
        
        for item in items_data:
            discount = Decimal(str(item.get('discount_amount', 0) or 0))
            tax = Decimal(str(item.get('tax_amount', 0) or 0))
            total_discount += discount
            total_tax += tax
            
            items.append(QuoteDetailItem(
                line_number=item.get('line_number', 0),
                product_code=str(item.get('product_code', '')),
                product_name=item.get('product_name') or item.get('description', '') or '',
                quantity=str(item.get('quantity', 0) or 0),
                unit_price=str(item.get('unit_price', 0) or 0),
                discount_amount=str(discount),
                tax_amount=str(tax),
                line_total=str(item.get('line_total', 0) or 0),
            ))
        
        # Calcular totales
        total_neto = Decimal(str(header.get('total_neto', 0)))
        totals = QuoteTotals(
            total_net=str(total_neto),
            total_tax=str(total_tax),
            total_discount=str(total_discount),
            total_gross=str(total_neto + total_tax - total_discount),
        )
        
        # Determinar estado basado en status, anulado, saldo y fecha de expiración
        str(header.get('status', '0')).strip()
        anulado = header.get('anulado', 0)
        balance = Decimal(str(header.get('saldo', 0) or 0))
        expiration_date = header.get('expires_at')
        
        if anulado == 1:
            status = "cancelled"
        elif balance == 0:
            status = "converted"  # Convertida a factura
        elif expiration_date:
            if isinstance(expiration_date, datetime):
                # Convertir fecha naive a aware usando zona horaria de Venezuela
                if expiration_date.tzinfo is None:
                    expiration_date_aware = expiration_date.replace(tzinfo=VENEZUELA_TZ)
                else:
                    expiration_date_aware = expiration_date
                
                if expiration_date_aware < get_ve_now():
                    status = "expired"
                else:
                    status = "pending"
            else:
                status = "pending"
        else:
            status = "pending"
        
        # Formatear fechas
        created_at = header.get('created_at')
        expires_at = header.get('expires_at')
        if created_at and isinstance(created_at, datetime):
            created_at = created_at.isoformat()
        if expires_at and isinstance(expires_at, datetime):
            expires_at = expires_at.isoformat()
        
        # Historial básico
        history: list[QuoteHistoryEvent] = [
            QuoteHistoryEvent(
                timestamp=created_at or "",
                event="created",
                detail="Cotización registrada en Profit Plus",
            ),
        ]
        
        return QuoteDetailResponse(
            quote_id=quote_id,
            profit_plus_id=str(header.get('profit_plus_id', profit_plus_id) or profit_plus_id),
            status=status,
            created_at=created_at or "",
            expires_at=expires_at or "",
            currency=header.get('currency_name', 'VES'),
            payment_terms="CONTADO",  # TODO: Obtener de tabla si existe
            delivery={"mode": "pickup"},  # TODO: Obtener de datos reales
            totals=totals,
            items=items,
            history=history,
        )
        
    except Exception as e:
        logger.error(
            f"Error obteniendo detalle de cotización {quote_id} para admin: {e}",
            exc_info=True
        )
        return None


# Funciones de Order eliminadas - Order no se usa con Profit Plus
# get_order_by_id, update_order_status, get_orders_by_status, get_orders_by_user, 
# get_orders_by_date, get_all_orders eliminadas

def get_all_customers(db: Session) -> list[User]:
    customers_without_admin_users = []
    customers = db.query(User).all()
    for customer in customers:
        if customer.role != 'admin' and customer.role != 'super_admin':
            customers_without_admin_users.append(customer)
    if not customers_without_admin_users:
        return []
    return customers_without_admin_users

# update_payment_status eliminado - Order no se usa con Profit Plus