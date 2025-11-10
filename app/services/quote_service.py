from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
from decimal import Decimal

from app.schemas.quote import (
    QuoteCreate,
    QuoteCreatedResponse,
    QuoteListItem,
    QuoteListResponse,
    Pagination,
    QuoteDetailResponse,
    QuoteDetailItem,
    QuoteTotals,
    QuoteHistoryEvent,
    QuoteStatus,
)
from app.utils.timezone import get_ve_now, VENEZUELA_TZ
from app.services.source_system_service import source_system_service
from app.config.logging_config import get_logger

logger = get_logger(__name__)


class QuoteService:
    """
    Service layer for Quotes that integrates with Profit Plus.
    Consults saCliente (encabezado) and saClienteReng (renglones) tables in DEMOA.
    """

    def __init__(self, db: Session):
        self.db = db
    
    def _get_customer_code_by_email(self, email: str) -> Optional[str]:
        """
        Obtiene el código de cliente (co_cli) en DEMOA por email.
        
        Args:
            email: Email del usuario
            
        Returns:
            Código de cliente (co_cli) o None si no se encuentra
        """
        try:
            customer = source_system_service.get_customer_by_email(email)
            if customer:
                return customer.get('customer_code')
            return None
        except Exception as e:
            logger.error(f"Error obteniendo código de cliente por email {email}: {e}")
            return None
    
    def _determine_status(self, saldo: Decimal, fec_venc: Optional[datetime]) -> str:
        """
        Determina el estado de una cotización basado en sus campos.
        
        Args:
            saldo: Saldo pendiente
            fec_venc: Fecha de vencimiento
            
        Returns:
            Estado: pending, converted, expired
        """
        now = get_ve_now()
    
        # Convertir fec_venc a aware si es naive
        if fec_venc:
            # Si fec_venc es naive (sin timezone), asumimos que está en hora de Venezuela
            if fec_venc.tzinfo is None:
                fec_venc = fec_venc.replace(tzinfo=VENEZUELA_TZ)
        
        print(f"saldo: {saldo}")
        print(f"fec_venc: {fec_venc}")
        print(f"now: {now}")
        
        if fec_venc and fec_venc < now and saldo > 0:
            return "expired"
        
        if saldo == 0:
            return "converted"  # Asumimos que saldo=0 significa convertida a pedido
        
        return "pending"

    def create_quote(
        self,
        user_id: int,
        payload: QuoteCreate,
        source_system: str,
    ) -> QuoteCreatedResponse:
        now = get_ve_now()
        quote_id = f"COT-{now.year}-{now.month}-{now.day}-{now.hour}-{now.minute}-{now.second}"
        profit_plus_id = now.strftime("%Y%m%d%H%M%S")
        expires_at = (
            payload.valid_until
            if payload.valid_until
            else (now + timedelta(days=30)).isoformat()
        )
        # TODO: Insert into Profit Plus and send email
        return QuoteCreatedResponse(
            quote_id=quote_id,
            profit_plus_id=profit_plus_id,
            status="pending",
            currency=payload.currency or "VES",
            total_net="0.00",
            total_tax="0.00",
            total_gross="0.00",
            expires_at=expires_at,
            email_sent_at=now.isoformat(),
        )

    def list_user_quotes(
        self,
        user_id: int,
        source_system: str,
        status_filter: Optional[str],
        date_range: Optional[Tuple[Optional[str], Optional[str]]],
        page: int,
        page_size: int,
    ) -> QuoteListResponse:
        """
        Lista cotizaciones del usuario desde Profit Plus.
        
        Args:
            user_id: ID del usuario en la BD local
            source_system: Sistema fuente (profit_plus)
            status_filter: Filtro por estado (pending, accepted, expired, cancelled, converted)
            date_range: Tupla con (from_date, to_date) en formato ISO
            page: Número de página
            page_size: Tamaño de página
            
        Returns:
            QuoteListResponse con cotizaciones paginadas
        """
        try:
            # Obtener email del usuario desde la BD local
            from app.models.user import User
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                print(f"Usuario {user_id} no encontrado")
                logger.warning(f"Usuario {user_id} no encontrado")
                return QuoteListResponse(
                    results=[],
                    pagination=Pagination(page=page, page_size=page_size, total_pages=0, total_items=0)
                )
            
            # Obtener código de cliente en DEMOA
            customer_code = self._get_customer_code_by_email(user.email)
            if not customer_code:
                print(f"Cliente no encontrado en DEMOA para email {user.email}")
                return QuoteListResponse(
                    results=[],
                    pagination=Pagination(page=page, page_size=page_size, total_pages=0, total_items=0)
                )
            
            # Verificar si la tabla existe primero
            conn = source_system_service.get_connection()
            cursor = conn.cursor()
            
            # Query simplificada sin filtros adicionales por ahora
            # Solo filtramos por cliente y saldo > 0
            offset = (page - 1) * page_size
            
            # Contar total de cotizaciones
            count_query = """
            SELECT COUNT(DISTINCT c.doc_num) as total
            FROM dbo.saCotizacionCliente c
            WHERE c.co_cli = %s AND c.saldo > 0
            """
            cursor.execute(count_query, (customer_code,))
            total_count = cursor.fetchone().get('total', 0)
            
            # Obtener cotizaciones con paginación y conteo de items
            # Query exacta que funciona en la base de datos
            query = """
            SELECT 
                c.co_cli AS Codigo_Cliente,
                c.doc_num AS profit_plus_id,
                c.fec_emis AS created_at,
                c.fec_emis AS emission_date,
                c.fec_venc AS expires_at,
                c.total_neto AS total_neto,
                c.saldo AS saldo,
                c.co_mone AS codigo_moneda,
                ISNULL(m.mone_des, 'Bolívares') AS currency_name,
                ISNULL(item_counts.items_count, 0) AS items_count
            FROM dbo.saCotizacionCliente c
            LEFT JOIN dbo.saMoneda m ON c.co_mone = m.co_mone
            LEFT JOIN (
                SELECT doc_num, COUNT(*) as items_count
                FROM dbo.saCotizacionClienteReng
                GROUP BY doc_num
            ) item_counts ON c.doc_num = item_counts.doc_num
            WHERE c.co_cli = %s 
            AND c.saldo > 0 
            ORDER BY c.fec_emis DESC
            OFFSET %s ROWS
            FETCH NEXT %s ROWS ONLY
            """
            
            cursor.execute(query, (customer_code, offset, page_size))
            quotes_data = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            # Transformar a QuoteListItem
            results = []
            for quote in quotes_data:
                print(quote.get('saldo', 0))
                print(quote.get('expires_at'))
                status = self._determine_status(
                    Decimal(str(quote.get('saldo', 0))),
                    quote.get('expires_at')
                )
                
                # Formatear fechas
                created_at = quote.get('created_at')
                expires_at = quote.get('expires_at')
                if created_at:
                    if isinstance(created_at, datetime):
                        created_at = created_at.isoformat()
                if expires_at:
                    if isinstance(expires_at, datetime):
                        expires_at = expires_at.isoformat()
                
                # Generar quote_id en formato COT-YYYY-XXXXX
                profit_plus_id = str(quote.get('profit_plus_id', ''))
                quote_id = f"COT-{profit_plus_id}" if profit_plus_id else "COT-UNKNOWN"
                
                results.append(QuoteListItem(
                    quote_id=quote_id,
                    profit_plus_id=profit_plus_id,
                    status=status,
                    created_at=created_at or "",
                    expires_at=expires_at or "",
                    total_gross=str(quote.get('total_neto', 0)),
                    currency=quote.get('currency_name', 'VES'),
                    items_count=quote.get('items_count', 0),
                    email_sent_at=created_at or "",  # Asumimos que se envió al crear
                ))
            
            total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 0
            
            return QuoteListResponse(
                results=results,
                pagination=Pagination(
                    page=page,
                    page_size=page_size,
                    total_pages=total_pages,
                    total_items=total_count,
                ),
            )
            
        except Exception as e:
            logger.error(f"Error listando cotizaciones para usuario {user_id}: {e}")
            import traceback
            traceback.print_exc()
            response = QuoteListResponse(
                results=[],
                pagination=Pagination(page=page, page_size=page_size, total_pages=0, total_items=0)
            )
            return response
            print(f"Error listando cotizaciones para usuario {user_id}: {e}")
            print(traceback.format_exc())
            return response

    def get_quote_detail(
        self,
        user_id: int,
        quote_id: str,
        source_system: str,
    ) -> Optional[QuoteDetailResponse]:
        """
        Obtiene el detalle completo de una cotización desde Profit Plus.
        
        Args:
            user_id: ID del usuario en la BD local
            quote_id: ID de la cotización (formato COT-XXXXX o solo el código)
            source_system: Sistema fuente (profit_plus)
            
        Returns:
            QuoteDetailResponse con todos los detalles o None si no se encuentra
        """
        try:
            # Extraer profit_plus_id del quote_id (puede venir como COT-XXXXX o solo XXXXX)
            # Eliminar espacios en blanco al inicio y al final
            profit_plus_id = quote_id.replace("COT-", "") if quote_id.startswith("COT-") else quote_id
            profit_plus_id = profit_plus_id.strip()
            
            # Obtener email del usuario
            from app.models.user import User
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.warning(f"Usuario {user_id} no encontrado")
                return None
            
            # Obtener código de cliente y eliminar espacios en blanco
            customer_code = self._get_customer_code_by_email(user.email)
            if not customer_code:
                logger.warning(f"Cliente no encontrado en DEMOA para email {user.email}")
                return None
            customer_code = customer_code.strip() if customer_code else None
            
            # Consulta para obtener los detalles de las cotizaciones
            # Utiliza saCotizacionCliente (encabezado) y saCotizacionClienteReng (renglones)
            conn = source_system_service.get_connection()
            cursor = conn.cursor()
            
            # Query exacta proporcionada para obtener detalles de cotización
            query = """
            SELECT 
                c.doc_num AS profit_plus_id,
                c.fec_emis AS created_at,
                c.fec_emis AS emission_date,
                c.fec_venc AS expires_at,
                c.total_neto AS total_neto,
                c.saldo AS saldo,
                c.co_mone AS codigo_moneda,
                ISNULL(m.mone_des, 'Bolívares') AS currency_name,
                c.co_ven AS codigo_vendedor,
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
            LEFT JOIN dbo.saMoneda m ON c.co_mone = m.co_mone
            LEFT JOIN dbo.saCotizacionClienteReng r ON c.doc_num = r.doc_num
            LEFT JOIN dbo.saArticulo a ON r.co_art = a.co_art
            WHERE c.doc_num = %s
              AND c.co_cli = %s
              AND c.anulado = 0
            ORDER BY r.reng_num
            """
            
            # Ejecutar consulta pasando doc_num (profit_plus_id) y código del cliente
            # Los espacios ya fueron eliminados anteriormente
            cursor.execute(query, (profit_plus_id, customer_code))
            all_data = cursor.fetchall()
            
            if not all_data:
                cursor.close()
                conn.close()
                logger.warning(f"Cotización {profit_plus_id} no encontrada para cliente {customer_code}")
                return None
            
            # El primer registro contiene la información del encabezado
            first_row = all_data[0]
            header = {
                'profit_plus_id': first_row.get('profit_plus_id'),
                'created_at': first_row.get('created_at'),
                'emission_date': first_row.get('emission_date'),
                'expires_at': first_row.get('expires_at'),
                'total_neto': first_row.get('total_neto'),
                'saldo': first_row.get('saldo'),
                'codigo_moneda': first_row.get('codigo_moneda'),
                'currency_name': first_row.get('currency_name'),
                'codigo_vendedor': first_row.get('codigo_vendedor'),
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
            
            # Determinar estado
            status = self._determine_status(
                Decimal(str(header.get('saldo', 0))),
                header.get('expires_at')
            )
            
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
            logger.error(f"Error obteniendo detalle de cotización {quote_id} para usuario {user_id}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_statuses(self) -> List[QuoteStatus]:
        return [
            QuoteStatus(
                code="pending",
                label="Pendiente",
                description="Cotización activa con saldo > 0.",
            ),
            QuoteStatus(
                code="accepted",
                label="Aceptada",
                description="La cotización fue confirmada manualmente por el cliente.",
            ),
            QuoteStatus(
                code="converted",
                label="Convertida a pedido",
                description="Cotización convertida a orden en Profit Plus.",
            ),
            QuoteStatus(
                code="expired",
                label="Vencida",
                description="Fecha de vencimiento menor a hoy y saldo > 0.",
            ),
            QuoteStatus(
                code="cancelled",
                label="Anulada",
                description="Cotización cancelada (no disponible sin columna anulado).",
            ),
        ]


