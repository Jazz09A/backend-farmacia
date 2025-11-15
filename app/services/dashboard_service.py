from datetime import timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.user import User
from app.models.order import Order
from app.models.order_discount import OrderDiscount
from app.config.logging_config import get_logger
from app.schemas.dashboard import DashboardStats, OrderStatusSummary, RecentOrder, DashboardData, DiscountBreakdown
from app.schemas.order import OrderStatus  # Import from schema, not model
from fastapi import HTTPException
from app.schemas.order import PaymentStatusEnum
from app.schemas.order import UpdatePaymentStatus
from decimal import Decimal
from app.utils.timezone import get_ve_now, VENEZUELA_TZ
from app.services.source_system_service import source_system_service

from app.schemas.order_discount import OrderDiscountSummary, OrderDiscountResponse

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


def _calculate_order_discount_info(order: Order) -> dict:
    """
    Calculates discount information for an order.
    
    Args:
        order: Order with loaded discounts
        
    Returns:
        dict with discount information
    """
    if not order.discounts:
        return {
            "total_discounts": 0,
            "total_discount_amount": Decimal('0.00'),
            "discount_breakdown": [],
            "savings_percentage": 0.0,
            "original_subtotal": order.subtotal,
            "total_savings": Decimal('0.00')
        }
    
    total_discount_amount = sum(discount.discount_amount for discount in order.discounts)
    original_subtotal = order.subtotal + total_discount_amount
    savings_percentage = (total_discount_amount / original_subtotal * 100) if original_subtotal > 0 else 0.0
    
    discount_breakdown = [
        OrderDiscountResponse.model_validate(discount) for discount in order.discounts
    ]
    
    return {
        "total_discounts": len(order.discounts),
        "total_discount_amount": total_discount_amount,
        "discount_breakdown": discount_breakdown,
        "savings_percentage": round(float(savings_percentage), 2),
        "original_subtotal": original_subtotal,
        "total_savings": total_discount_amount
    }

def get_dashboard_data(db: Session, days_filter: int = 7) -> DashboardData:
    """
    Retrieves and computes all data required for the admin dashboard.
    Now queries directly from Profit Plus source system (saCotizacionCliente and saCliente).
    """
    perf_logger = get_logger("performance")
    error_logger = get_logger("errors")
    
    perf_logger.info(
        f"Dashboard data calculation started",
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
        
        # Get connection to source system
        conn = source_system_service.get_connection()
        cursor = conn.cursor()
        
        # 2. Basic Stats
        # Total revenue: SUM(total_neto) from saFacturaVenta (invoices) for non-cancelled invoices
        revenue_query = """
        SELECT 
            ISNULL(SUM(total_neto), 0) AS total_revenue
        FROM dbo.saFacturaVenta
        WHERE fec_emis >= %s
          AND fec_emis <= %s
          AND anulado = 0
        """
        cursor.execute(revenue_query, (start_datetime, end_datetime))
        revenue_result = cursor.fetchone()
        total_revenue = Decimal(str(revenue_result.get('total_revenue', 0) or 0))
        
        # Total orders: COUNT from saCotizacionCliente (quotes)
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
        
        # 3. New customers from saCliente using fecha_reg
        new_customers_query = """
        SELECT COUNT(DISTINCT co_cli) AS new_customers
        FROM dbo.saCliente
        WHERE fecha_reg >= %s
          AND fecha_reg <= %s
        """
        cursor.execute(new_customers_query, (start_datetime, end_datetime))
        new_customers_result = cursor.fetchone()
        new_customers = new_customers_result.get('new_customers', 0) or 0
        
        # Placeholder for conversion rate logic
        conversion_rate = Decimal('0.00')
        
        # 4. Discount statistics (EXTENSIBLE - prepared for future implementation)
        # TODO: When discounts are needed, query from saCotizacionClienteReng.monto_desc
        # Structure prepared but not implemented yet
        total_discounts_given = Decimal('0.00')
        orders_with_discounts = 0
        discount_usage_percentage = 0.0
        average_discount_per_order = Decimal('0.00')
        
        # Discount breakdown structure (extensible)
        discount_breakdown = DiscountBreakdown()
        # TODO: When implementing discounts, query from saCotizacionClienteReng:
        # - Group by discount type if available
        # - Calculate total_amount_by_type from monto_desc
        # - Use start_datetime and end_datetime for date filtering
        # Example query structure (not executed):
        # discount_query = """
        # SELECT 
        #     COUNT(DISTINCT c.doc_num) AS orders_with_discounts,
        #     ISNULL(SUM(r.monto_desc), 0) AS total_discounts
        # FROM dbo.saCotizacionCliente c
        # INNER JOIN dbo.saCotizacionClienteReng r ON c.doc_num = r.doc_num
        # WHERE c.fec_emis >= %s AND c.fec_emis <= %s
        #   AND c.anulado = 0
        #   AND r.monto_desc > 0
        # """
        # cursor.execute(discount_query, (start_datetime, end_datetime))
        
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
        
        # 5. Order Status Summary from saCotizacionCliente
        status_summary_query = """
        SELECT 
            status,
            anulado,
            COUNT(DISTINCT doc_num) AS count
        FROM dbo.saCotizacionCliente
        WHERE fec_emis >= %s
          AND fec_emis <= %s
        GROUP BY status, anulado
        """
        cursor.execute(status_summary_query, (start_datetime, end_datetime))
        status_results = cursor.fetchall()
        
        # Initialize status counts
        status_counts = {
            'pending': 0,
            'confirmed': 0,
            'processing': 0,
            'shipped': 0,
            'delivered': 0,
            'cancelled': 0
        }
        
        # Map Profit Plus states to dashboard states
        for row in status_results:
            status = str(row.get('status', '0')).strip()
            anulado = row.get('anulado', 0)
            count = row.get('count', 0) or 0
            
            dashboard_status = _map_quote_status_to_dashboard_status(status, anulado)
            status_counts[dashboard_status] = status_counts.get(dashboard_status, 0) + count
        
        order_status_summary = OrderStatusSummary(
            pending=status_counts['pending'],
            confirmed=status_counts['confirmed'],
            processing=status_counts['processing'],
            shipped=status_counts['shipped'],  # Always 0 for quotes
            delivered=status_counts['delivered'],  # Always 0 for quotes
            cancelled=status_counts['cancelled'],
        )
        
        # 6. Recent Orders (last 5 quotes) from saCotizacionCliente with customer info
        recent_orders_query = """
        SELECT TOP 5
            c.doc_num AS quote_id,
            ISNULL(cl.cli_des, 'Cliente Desconocido') AS customer_name,
            c.fec_emis AS emission_date,
            c.total_neto AS total,
            c.status,
            c.anulado
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
            quote_id = str(quote.get('quote_id', ''))
            customer_name = quote.get('customer_name', 'Cliente Desconocido') or 'Cliente Desconocido'
            emission_date = quote.get('emission_date')
            total = Decimal(str(quote.get('total', 0) or 0))
            status = str(quote.get('status', '0')).strip()
            anulado = quote.get('anulado', 0)
            
            # Format date
            if emission_date:
                if isinstance(emission_date, str):
                    date_str = emission_date[:10]  # Take first 10 chars (YYYY-MM-DD)
                else:
                    date_str = emission_date.strftime("%Y-%m-%d")
            else:
                date_str = start_datetime.strftime("%Y-%m-%d")
            
            # Map status
            dashboard_status = _map_quote_status_to_dashboard_status(status, anulado)
            
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
        
        perf_logger.info(
            f"Dashboard data calculated successfully from source system",
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
            f"Error calculating dashboard data from source system: {str(e)}",
            extra={
                'days_filter': days_filter,
                'event': 'dashboard_calculation_error',
                'user_email': 'admin@farmaplus.com'
            },
            exc_info=True
        )
        # Return empty/default data on error
        return DashboardData(
            stats=DashboardStats(
                total_revenue=Decimal('0.00'),
                total_orders=0,
                new_customers=0,
                conversion_rate=Decimal('0.00'),
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
    from app.schemas.quote import QuoteListItem, QuoteListResponse, Pagination
    from datetime import datetime
    
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
            status_code = str(quote.get('status', '0')).strip()
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
            f"Error obteniendo cotizaciones paginadas: {str(e)}",
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
    from app.schemas.quote import QuoteDetailResponse, QuoteDetailItem, QuoteTotals, QuoteHistoryEvent
    from datetime import datetime
    
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
        status_code = str(header.get('status', '0')).strip()
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
        history: List[QuoteHistoryEvent] = [
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


def get_order_by_id(db: Session, id: str) -> Order:
    return db.query(Order).filter(Order.id == id).first()


def update_order_status(db: Session, id: str, status: str) -> Order:
    order = db.query(Order).filter(Order.id == id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Validate status against the schema enum (English values)
    valid_statuses = [status.value for status in OrderStatus]
    if status not in valid_statuses:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid status. Valid statuses are: {valid_statuses}"
        )
    
    order.status = status
    db.commit()
    db.refresh(order)
    
    # Manually construct the response to match OrderResponse schema
    discount_info = _calculate_order_discount_info(order)
    
    response_data = order.__dict__
    response_data['items'] = order.items
    response_data['shipping_address'] = order.shipping_address
    response_data['item_count'] = len(order.items)
    # Formatear exchange_rate a 2 decimales
    if response_data.get('exchange_rate'):
        response_data['exchange_rate'] = response_data['exchange_rate'].quantize(Decimal('0.01'))
    
    if discount_info and discount_info["total_discounts"] > 0:
        response_data['discounts'] = OrderDiscountSummary(
            total_discounts=discount_info["total_discounts"],
            total_discount_amount=discount_info["total_discount_amount"],
            discount_breakdown=discount_info["discount_breakdown"],
            savings_percentage=discount_info["savings_percentage"]
        )
    else:
        response_data['discounts'] = None
        
    response_data['original_subtotal'] = discount_info.get("original_subtotal", order.subtotal)
    response_data['total_savings'] = discount_info.get("total_savings", Decimal('0.00'))
    
    from app.schemas.order import OrderResponse
    return OrderResponse.model_validate(response_data)

def get_orders_by_status(db: Session, status: str) -> List[Order]:
    orders = db.query(Order).filter(Order.status == status).all()
    if not orders:
        raise HTTPException(status_code=404, detail="No orders found")
    return orders

def get_orders_by_user(db: Session, user_id: str) -> List[Order]:
    orders = db.query(Order).filter(Order.user_id == user_id).all()
    if not orders:
        raise HTTPException(status_code=404, detail="No orders found")
    return orders

def get_orders_by_date(db: Session, date: str) -> List[Order]:
    orders = db.query(Order).filter(Order.created_at == date).all()
    if not orders:
        raise HTTPException(status_code=404, detail="No orders found")
    return orders

def get_all_orders(db: Session) -> List[Order]:
    # Use eager loading to avoid N+1 queries when accessing user, items, and shipping address data
    from sqlalchemy.orm import joinedload
    orders = db.query(Order).options(
        joinedload(Order.user),
        joinedload(Order.items),
        joinedload(Order.shipping_address)
    ).all()
    return orders

def get_all_customers(db: Session) -> List[User]:
    customers_without_admin_users = []
    customers = db.query(User).all()
    for customer in customers:
        if customer.role != 'admin' and customer.role != 'super_admin':
            customers_without_admin_users.append(customer)
    if not customers_without_admin_users:
        return []
    return customers_without_admin_users

def update_payment_status(db: Session, order_id: str, status: PaymentStatusEnum) -> Order:
    status_value = status.value if isinstance(status, PaymentStatusEnum) else status
    orders_logger.info(
        "Actualizando estado de pago desde dashboard",
        extra={
            "order_id": order_id,
            "new_status": status_value,
        },
    )
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Validar que el status sea válido para pagos
    valid_payment_statuses = [status.value for status in PaymentStatusEnum]
    if status_value not in valid_payment_statuses:
        orders_logger.warning(
            "Estado de pago inválido recibido",
            extra={
                "order_id": order_id,
                "new_status": status_value,
                "valid_statuses": valid_payment_statuses,
            },
        )
        raise HTTPException(
            status_code=400, 
            detail=f"Status de pago inválido. Valores válidos: {valid_payment_statuses}"
        )
    
    order.payment_status = status_value
    db.commit()
    db.refresh(order)
    return order

# =============================================================================
# FUNCIONES DE CRÉDITO PARA DASHBOARD
# =============================================================================

def get_credit_payments_dashboard(db: Session) -> dict:
    """Dashboard de pagos de crédito para admin"""
    from app.models.credit_payment import CreditPayment
    from app.models.order import Order
    from sqlalchemy import func
    
    
    # Pagos pendientes
    pending_payments = db.query(CreditPayment).filter(
        CreditPayment.status == "pending"
    ).count()
    
    # Pagos aprobados hoy
    today = get_ve_now().date()
    approved_today = db.query(CreditPayment).filter(
        CreditPayment.status == "approved",
        func.date(CreditPayment.approved_at) == today
    ).count()
    
    # Monto total pendiente
    total_pending_amount = db.query(func.sum(CreditPayment.amount)).filter(
        CreditPayment.status == "pending"
    ).scalar() or 0
    
    # Órdenes con pagos pendientes
    orders_with_pending = db.query(Order).filter(
        Order.is_credit_order == True,
        Order.credit_remaining > 0
    ).count()
    
    return {
        "pending_payments": pending_payments,
        "approved_today": approved_today,
        "total_pending_amount": total_pending_amount,
        "orders_with_pending": orders_with_pending
    }

def get_user_credit_dashboard(user_id: str, db: Session) -> dict:
    """Dashboard de crédito para usuario"""
    from app.models.user import User
    from app.models.order import Order
    from app.models.credit_payment import CreditPayment
    from sqlalchemy import func
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {}
    
    # Órdenes del usuario
    orders = db.query(Order).filter(
        Order.user_id == user_id,
        Order.is_credit_order == True
    ).all()
    
    # Pagos pendientes de aprobación
    pending_payments = db.query(CreditPayment).filter(
        CreditPayment.user_id == user_id,
        CreditPayment.status == "pending"
    ).all()
    
    # Pagos aprobados recientes
    recent_approved = db.query(CreditPayment).filter(
        CreditPayment.user_id == user_id,
        CreditPayment.status == "approved"
    ).order_by(CreditPayment.approved_at.desc()).limit(5).all()
    
    # Estadísticas
    total_credit_used = sum(order.credit_amount for order in orders)
    total_paid = sum(order.credit_paid_total for order in orders)
    total_remaining = sum(order.credit_remaining for order in orders)
    
    # Convert ORM payments to serializable dicts
    from app.schemas.credit import CreditPaymentResponse
    recent_approved_serialized = [
        CreditPaymentResponse.model_validate(p).model_dump()
        for p in recent_approved
    ]

    return {
        "user_credit": {
            "available_credit": user.available_credit,
            "credit_limit": user.credit_limit,
            "credit_status": user.credit_status
        },
        "orders": {
            "total_orders": len(orders),
            "total_credit_used": total_credit_used,
            "total_paid": total_paid,
            "total_remaining": total_remaining
        },
        "payments": {
            "pending_count": len(pending_payments),
            "pending_amount": sum(p.amount for p in pending_payments),
            "recent_approved": recent_approved_serialized
        }
    }

def get_payment_details(payment_id: str, db: Session) -> dict:
    """Detalles completos de un pago"""
    from app.models.credit_payment import CreditPayment
    from app.models.order import Order
    from app.models.user import User
    
    payment = db.query(CreditPayment).filter(CreditPayment.id == payment_id).first()
    if not payment:
        return None
    
    order = payment.order
    user = payment.user
    
    from app.schemas.credit import CreditPaymentResponse
    payment_serialized = CreditPaymentResponse.model_validate(payment).model_dump()

    return {
        "payment": payment_serialized,
        "order": {
            "id": order.id,
            "order_number": order.order_number,
            "total": order.total,
            "credit_remaining": order.credit_remaining,
            "credit_paid_total": order.credit_paid_total
        },
        "user": {
            "id": user.id,
            "email": user.email,
            "company_name": user.company_name
        }
    }