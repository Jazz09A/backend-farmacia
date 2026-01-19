from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
from decimal import Decimal

from app.schemas.quote import (
    QuoteCreate,
    QuoteCreatedResponse,
    QuoteVerifyRequest,
    QuoteVerifyResponse,
    QuoteVerifyItemResult,
    QuoteVerifyTotals,
    QuoteListItem,
    QuoteListResponse,
    Pagination,
    QuoteDetailResponse,
    QuoteDetailItem,
    QuoteTotals,
    QuoteHistoryEvent,
    QuoteStatus,
    CartValidationRequest,
    CartValidationResponse,
    CartValidationItemResult,
    CartValidationTotals,
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
        
        logger.debug(
            "Determinando estado de cotización",
            extra={
                "saldo": str(saldo),
                "fec_venc": fec_venc.isoformat() if isinstance(fec_venc, datetime) else str(fec_venc),
                "now": now.isoformat(),
            },
        )
        
        if fec_venc and fec_venc < now and saldo > 0:
            return "expired"
        
        if saldo == 0:
            return "converted"  # Asumimos que saldo=0 significa convertida a pedido
        
        return "pending"

    def _generate_doc_num_safe(self, cursor) -> str:
        """
        Genera un doc_num único de forma segura usando bloqueo pesimista.
        Obtiene el último doc_num numérico, lo incrementa y lo formatea.
        
        Returns:
            Nuevo doc_num formateado con la convención de Profit (10 dígitos con ceros a la izquierda)
        """
        # Obtener el último doc_num con bloqueo para evitar concurrencia
        query_last = """
        SELECT TOP 1 doc_num
        FROM dbo.saCotizacionCliente WITH (UPDLOCK, HOLDLOCK)
        WHERE ISNUMERIC(doc_num) = 1
        ORDER BY CAST(doc_num AS BIGINT) DESC
        """
        cursor.execute(query_last)
        last_row = cursor.fetchone()
        
        if last_row and last_row.get('doc_num'):
            last_num_str = str(last_row.get('doc_num')).strip()
            try:
                # Convertir a entero, incrementar y formatear
                last_num = int(last_num_str)
                new_num = last_num + 1
            except (ValueError, TypeError):
                # Si no se puede convertir, empezar desde 1
                new_num = 1
        else:
            # Primera cotización, empezar desde 1
            new_num = 1
        
        # Formatear a 10 caracteres con ceros a la izquierda (Profit maneja char(10) y rellena con espacios)
        return str(new_num).zfill(10)

    def create_quote(
        self,
        user_id: int,
        payload: QuoteCreate,
        source_system: str,
        user_email: Optional[str] = None,
    ) -> QuoteCreatedResponse:
        """
        Inserta cotización en Profit Plus (saCotizacionCliente y saCotizacionClienteReng)
        siguiendo el flujo transaccional del script SQL.
        
        Proceso:
        1. Genera doc_num de forma segura con bloqueo
        2. Obtiene datos del cliente (dirección de entrega)
        3. Obtiene datos de artículos (descripción, tipo de impuesto)
        4. Inserta cabecera con totales en 0
        5. Inserta renglones calculando impuestos
        6. Actualiza totales en la cabecera
        7. Confirma o revierte la transacción
        """
        from app.services.source_system_service import source_system_service
        
        now = get_ve_now()
        if payload.valid_until:
            expires_at_dt = datetime.fromisoformat(payload.valid_until)
            # Asegurar que la fecha sea aware (con timezone)
            if expires_at_dt.tzinfo is None:
                # Si es naive, asumir que está en hora de Venezuela
                expires_at_dt = expires_at_dt.replace(tzinfo=VENEZUELA_TZ)
        else:
            expires_at_dt = now + timedelta(days=30)
        
        # Validar que fec_venc no sea anterior a la fecha actual
        # La restricción CHECK requiere que fec_venc >= fec_emis
        if expires_at_dt < now:
            logger.warning(f"Fecha de vencimiento {expires_at_dt} es anterior a la fecha actual. Usando fecha actual + 30 días.")
            expires_at_dt = now + timedelta(days=30)
        
        currency_code = (payload.currency or "VES").strip()
        
        # Obtener código de cliente: del payload o del usuario autenticado
        co_cli = None
        if payload.customer and payload.customer.code:
            co_cli = payload.customer.code.strip()
        elif user_email:
            # Obtener código de cliente del usuario autenticado
            customer_data = self._get_customer_code_by_email(user_email)
            if customer_data:
                co_cli = customer_data
            else:
                raise ValueError(f"No se encontró código de cliente para el usuario con email {user_email}")
        else:
            raise ValueError("Customer code (co_cli) es requerido. Proporciónelo en el payload o asegúrese de que el usuario esté autenticado.")
        
        logger.info(f"Usando código de cliente: {co_cli}")

        # Valores por defecto según el script
        co_ven = "003"  # Código de vendedor para E-Commerce (configurar aquí el código deseado)
        descrip_cotizacion = payload.notes or "Cotización desde E-Commerce"
        co_us_in = "SA"  # Usuario del sistema
        co_alma = "001"  # Almacén principal (ajustar según configuración)
        tasa = Decimal('1.00')  # Tasa de cambio (1.00 para misma moneda, ajustar si es necesario)
        porc_imp_default = Decimal('16.00')  # 16% IVA por defecto

        try:
            with source_system_service.connection() as conn:
                cursor = conn.cursor()
                
                # Limpiar cualquier transacción pendiente de la conexión reutilizada
                try:
                    cursor.execute("IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION")
                except Exception:
                    pass  # Ignorar si no hay transacción pendiente
                
                # Iniciar transacción explícita (manejada por pymssql)
                cursor.execute("BEGIN TRANSACTION")
            
            # PASO 1: Generar doc_num de forma segura
            doc_num = self._generate_doc_num_safe(cursor)
            logger.info(f"Generado doc_num: {doc_num} para cotización de cliente {co_cli}")
            
            # PASO 1.5: Validar código de vendedor
            # Validar que el código de vendedor existe en la base de datos
            query_vendedor = """
            SELECT co_ven
            FROM dbo.saVendedor
            WHERE co_ven = %s
            """
            cursor.execute(query_vendedor, (co_ven,))
            vendedor_row = cursor.fetchone()
            
            if not vendedor_row:
                raise ValueError(f"Código de vendedor '{co_ven}' no existe en la base de datos. Verifique el código configurado.")
            
            logger.info(f"Vendedor validado: {co_ven}")
            
            # PASO 2: Obtener datos del cliente y validar dirección de entrega
            query_cliente = """
            SELECT 
                RTRIM(co_cli) AS co_cli,
                RTRIM(cli_des) AS cli_des,
                RTRIM(email) AS email,
                RTRIM(email_alterno) AS email_alterno,
                RTRIM(telefonos) AS telefonos,
                RTRIM(direc1) AS direc1,
                RTRIM(dir_ent2) AS dir_ent2,
                RTRIM(direc2) AS direc2
            FROM dbo.saCliente
            WHERE co_cli = %s
            """
            cursor.execute(query_cliente, (co_cli,))
            cliente_row = cursor.fetchone()
            
            # Validar que el cliente existe
            if not cliente_row:
                # Si el cliente no existe y se proporcionó en el payload, intentar obtenerlo del usuario autenticado
                if payload.customer and payload.customer.code and user_email:
                    logger.warning(
                        f"Cliente con código '{co_cli}' no existe. Intentando obtener código del usuario autenticado (email: {user_email})"
                    )
                    # Intentar obtener el código de cliente del usuario autenticado
                    customer_code_from_email = self._get_customer_code_by_email(user_email)
                    if customer_code_from_email and customer_code_from_email != co_cli:
                        logger.info(
                            f"Usando código de cliente del usuario autenticado: {customer_code_from_email} "
                            f"(en lugar del proporcionado: {co_cli})"
                        )
                        co_cli = customer_code_from_email
                        # Reintentar la consulta con el nuevo código
                        cursor.execute(query_cliente, (co_cli,))
                        cliente_row = cursor.fetchone()
                
                # Si aún no existe, lanzar error descriptivo
                if not cliente_row:
                    error_msg = (
                        f"Cliente con código '{co_cli}' no existe en la base de datos Profit Plus. "
                    )
                    if user_email:
                        customer_code_from_email = self._get_customer_code_by_email(user_email)
                        if customer_code_from_email:
                            error_msg += (
                                f"El código de cliente asociado a tu email ({user_email}) es '{customer_code_from_email}'. "
                                f"Por favor, usa ese código o no envíes el campo 'customer.code' para que se use automáticamente."
                            )
                        else:
                            error_msg += (
                                f"No se encontró un código de cliente asociado a tu email ({user_email}) en Profit Plus. "
                                f"Contacta al administrador para verificar tu cuenta."
                            )
                    else:
                        error_msg += "Verifica el código de cliente o asegúrate de estar autenticado."
                    
                    logger.error(f"Error validando cliente: {error_msg}")
                    raise ValueError(error_msg)
            
            # Obtener datos del cliente desde la BD (para logging y validación)
            cliente_email_bd = (cliente_row.get('email') or cliente_row.get('email_alterno') or '').strip()
            cliente_name_bd = (cliente_row.get('cli_des') or '').strip()
            cliente_phone_bd = (cliente_row.get('telefonos') or '').strip()
            
            # Log de datos obtenidos de la BD (si no se proporcionaron en el payload)
            if payload.customer:
                if not payload.customer.email and cliente_email_bd:
                    logger.info(f"Email del cliente obtenido desde BD: {cliente_email_bd}")
                if not payload.customer.name and cliente_name_bd:
                    logger.info(f"Nombre del cliente obtenido desde BD: {cliente_name_bd}")
                if not payload.customer.phone and cliente_phone_bd:
                    logger.info(f"Teléfono del cliente obtenido desde BD: {cliente_phone_bd}")
            
            # Obtener todas las direcciones del cliente
            direc1 = (cliente_row.get('direc1') or '').strip() if cliente_row.get('direc1') else None
            dir_ent2 = (cliente_row.get('dir_ent2') or '').strip() if cliente_row.get('dir_ent2') else None
            direc2 = (cliente_row.get('direc2') or '').strip() if cliente_row.get('direc2') else None
            
            # Validar dirección si se proporciona
            direccion_entrega = None
            if payload.direc:
                direc_provided = payload.direc.strip()
                # Verificar que la dirección proporcionada existe en las direcciones del cliente
                direcciones_validas = []
                if direc1:
                    direcciones_validas.append(direc1)
                if dir_ent2:
                    direcciones_validas.append(dir_ent2)
                if direc2:
                    direcciones_validas.append(direc2)
                
                # Validar que la dirección proporcionada coincida con alguna de las direcciones del cliente
                direccion_encontrada = False
                for direc_valida in direcciones_validas:
                    if direc_provided == direc_valida:
                        direccion_entrega = direc_provided
                        direccion_encontrada = True
                        logger.info(f"Dirección validada para cliente {co_cli}: {direc_provided}")
                        break
                
                if not direccion_encontrada:
                    raise ValueError(
                        f"La dirección proporcionada '{direc_provided}' no coincide con ninguna dirección registrada "
                        f"para el cliente '{co_cli}'. Direcciones disponibles: {', '.join(direcciones_validas) if direcciones_validas else 'Ninguna'}"
                    )
            else:
                # Si no se proporciona dirección, usar la principal (direc1) por defecto
                direccion_entrega = direc1
                if not direccion_entrega:
                    logger.warning(f"No se encontró dirección principal (direc1) para cliente {co_cli}, usando NULL")
                else:
                    logger.info(f"Usando dirección principal por defecto para cliente {co_cli}: {direccion_entrega}")
            
            # PASO 2.5: Validar y obtener código de transporte
            co_tran = None
            if payload.delivery and payload.delivery.co_tran:
                co_tran = payload.delivery.co_tran.strip()
                
                # Validar que el código de transporte existe
                query_transporte = """
                SELECT co_tran, des_tran
                FROM dbo.saTransporte
                WHERE co_tran = %s
                """
                cursor.execute(query_transporte, (co_tran,))
                transporte_row = cursor.fetchone()
                
                if not transporte_row:
                    raise ValueError(f"Código de transporte '{co_tran}' no válido. Debe ser uno de: 001, 002, 003, 004, 005, 006, 007")
                
                logger.info(f"Transporte validado: {co_tran} - {transporte_row.get('des_tran')}")
            else:
                # Si no se proporciona, usar el default "001" (ENTREGA DIRECTA)
                co_tran = "001"
                logger.info(f"Usando transporte por defecto: {co_tran} (ENTREGA DIRECTA)")
            
            # PASO 2.6: Validar y obtener código de condición de pago
            co_cond = None
            payment_terms_input = payload.payment_terms or "CON"
            co_cond = payment_terms_input.strip()
            
            # Validar que el código de condición de pago existe
            query_condicion = """
            SELECT co_cond, cond_des
            FROM dbo.saCondicionPago
            WHERE co_cond = %s
            """
            cursor.execute(query_condicion, (co_cond,))
            condicion_row = cursor.fetchone()
            
            if not condicion_row:
                raise ValueError(
                    f"Código de condición de pago '{co_cond}' no válido. "
                    f"Debe ser uno de: CON, 3D, 5D, 7D, 10D, 12D, 14D, 15D, 16D, 20D, 21D, 30D, 360D"
                )
            
            logger.info(f"Condición de pago validada: {co_cond} - {condicion_row.get('cond_des')}")
            
            # PASO 3: Obtener datos de artículos (descripción, tipo de impuesto, unidad de medida y PRECIO)
            co_arts = [item.product_code.strip() for item in payload.items if item.product_code]
            if not co_arts:
                raise ValueError("No se proporcionaron artículos para la cotización")
            
            placeholders = ",".join(["%s"] * len(co_arts))
            query_articulos = f"""
            SELECT 
                a.co_art,
                a.art_des,
                ISNULL(a.tipo_imp, '1') AS tipo_imp,
                ISNULL(au.co_uni, 'UND') AS co_uni,
                ISNULL(precio.monto, 0) AS precio_base
            FROM dbo.saArticulo a
            LEFT JOIN dbo.saArtUnidad au ON a.co_art = au.co_art AND au.uni_principal = 1
            OUTER APPLY (
                SELECT TOP 1 ap.monto
                FROM dbo.saArtPrecio ap
                WHERE ap.co_art = a.co_art AND RTRIM(ap.co_precio) = '01'
                ORDER BY ap.desde DESC
            ) precio
            WHERE a.co_art IN ({placeholders})
            """
            cursor.execute(query_articulos, tuple(co_arts))
            articulos_data = cursor.fetchall()
            articulos_map = {
                (row.get('co_art') or '').strip(): {
                    'art_des': row.get('art_des'),
                    'tipo_imp': row.get('tipo_imp', '1'),
                    'co_uni': (row.get('co_uni') or 'UND').strip(),
                    'precio_base': Decimal(str(row.get('precio_base') or 0))
                }
                for row in articulos_data
            }
            
            # Validar que todos los artículos existen
            missing_arts = [art for art in co_arts if art not in articulos_map]
            if missing_arts:
                raise ValueError(f"Artículos no encontrados: {', '.join(missing_arts)}")
            
            # Validar que todas las unidades de medida existen en saUnidad
            co_unis = [art_data.get('co_uni', 'UND') for art_data in articulos_map.values()]
            co_unis_unique = list(set(co_unis))
            if co_unis_unique:
                placeholders_uni = ",".join(["%s"] * len(co_unis_unique))
                query_unidades = f"""
                SELECT co_uni
                FROM dbo.saUnidad
                WHERE co_uni IN ({placeholders_uni})
                """
                cursor.execute(query_unidades, tuple(co_unis_unique))
                unidades_data = cursor.fetchall()
                unidades_validas = {row.get('co_uni', '').strip() for row in unidades_data}
                
                unidades_invalidas = [uni for uni in co_unis_unique if uni not in unidades_validas]
                if unidades_invalidas:
                    logger.warning(f"Unidades de medida no encontradas: {unidades_invalidas}. Usando 'UND' como default.")
                    # Reemplazar unidades inválidas con 'UND'
                    for art_data in articulos_map.values():
                        if art_data.get('co_uni') in unidades_invalidas:
                            art_data['co_uni'] = 'UND'
            
            # PASO 4: Insertar cabecera con totales en 0 (se actualizarán después)
            # Asegurar que todos los valores char respeten sus límites
            co_cli_value = co_cli[:16] if len(co_cli) > 16 else co_cli.ljust(16) if len(co_cli) < 16 else co_cli
            co_tran_value = co_tran[:6] if len(co_tran) > 6 else co_tran.ljust(6) if len(co_tran) < 6 else co_tran
            co_ven_value = co_ven[:6] if len(co_ven) > 6 else co_ven.ljust(6) if len(co_ven) < 6 else co_ven
            currency_code_value = currency_code[:6] if len(currency_code) > 6 else currency_code.ljust(6) if len(currency_code) < 6 else currency_code
            co_cond_value = co_cond[:6] if len(co_cond) > 6 else co_cond.ljust(6) if len(co_cond) < 6 else co_cond
            co_us_in_value = co_us_in[:6] if len(co_us_in) > 6 else co_us_in.ljust(6) if len(co_us_in) < 6 else co_us_in
            co_us_mo_value = co_us_in_value  # Usuario de modificación igual al de inserción inicialmente
            
            # Valores por defecto para campos obligatorios
            monto_desc_glob = Decimal('0.00')
            monto_reca = Decimal('0.00')
            monto_imp2 = Decimal('0.00')
            monto_imp3 = Decimal('0.00')
            otros1 = Decimal('0.00')
            otros2 = Decimal('0.00')
            otros3 = Decimal('0.00')
            contrib = 0  # No es contribuyente
            impresa = 0  # No impresa
            
            # Convertir fecha aware a naive para SQL Server (smalldatetime no maneja timezone)
            expires_at_naive = expires_at_dt.replace(tzinfo=None) if expires_at_dt.tzinfo else expires_at_dt
            
            insert_header = """
            INSERT INTO dbo.saCotizacionCliente
                (doc_num, descrip, co_cli, co_tran, co_ven, co_mone, co_cond, tasa, fec_emis, fec_reg, fec_venc, 
                 anulado, status, ven_ter, monto_desc_glob, monto_reca, total_bruto, monto_imp, monto_imp2, monto_imp3,
                 otros1, otros2, otros3, total_neto, saldo, dir_ent, contrib, impresa, co_us_in, fe_us_in, 
                 co_us_mo, fe_us_mo, validador, rowguid)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, GETDATE(), GETDATE(), %s, 0, '0', 0, %s, %s, 0, 0, %s, %s, 
                 %s, %s, %s, 0, 0, %s, %s, %s, %s, GETDATE(), %s, GETDATE(), DEFAULT, NEWID())
            """
            cursor.execute(
                insert_header,
                (
                    doc_num,
                    descrip_cotizacion[:60] if descrip_cotizacion else "Cotización desde E-Commerce",
                    co_cli_value,
                    co_tran_value,  # Código de transporte validado
                    co_ven_value,
                    currency_code_value,
                    co_cond_value,  # Código de condición de pago validado
                    tasa,
                    expires_at_naive,  # Fecha sin timezone para SQL Server
                    monto_desc_glob,
                    monto_reca,
                    monto_imp2,
                    monto_imp3,
                    otros1,
                    otros2,
                    otros3,
                    direccion_entrega,
                    contrib,
                    impresa,
                    co_us_in_value,
                    co_us_mo_value,
                ),
            )
            
            # PASO 5: Insertar renglones y calcular totales
            total_bruto = Decimal('0.00')
            total_impuestos = Decimal('0.00')
            total_descuentos = Decimal('0.00')  # Acumulador de descuentos
            reng_num = 1
            
            # Lista para guardar descuentos aplicados (se incrementarán después del COMMIT)
            discounts_to_increment = []
            
            # Valores por defecto para campos obligatorios de renglones
            porc_imp2 = Decimal('0.00')
            porc_imp3 = Decimal('0.00')
            monto_imp2 = Decimal('0.00')
            monto_imp3 = Decimal('0.00')
            pendiente = Decimal('0.00')
            pendiente2 = Decimal('0.00')
            total_dev = Decimal('0.00')
            monto_dev = Decimal('0.00')
            otros = Decimal('0.00')
            lote_asignado = 0  # No asignado
            monto_desc_glob_reng = Decimal('0.00')
            monto_reca_glob_reng = Decimal('0.00')
            otros1_glob_reng = Decimal('0.00')
            otros2_glob_reng = Decimal('0.00')
            otros3_glob_reng = Decimal('0.00')
            monto_imp_afec_glob_reng = Decimal('0.00')
            monto_imp2_afec_glob_reng = Decimal('0.00')
            monto_imp3_afec_glob_reng = Decimal('0.00')
            
            insert_reng = """
            INSERT INTO dbo.saCotizacionClienteReng
                (reng_num, doc_num, co_art, des_art, co_alma, total_art, stotal_art, co_uni, prec_vta,
                 porc_imp, porc_imp2, porc_imp3, monto_imp, monto_imp2, monto_imp3, monto_desc, reng_neto,
                 tipo_imp, pendiente, pendiente2, total_dev, monto_dev, otros, lote_asignado,
                 monto_desc_glob, monto_reca_glob, otros1_glob, otros2_glob, otros3_glob,
                 monto_imp_afec_glob, monto_imp2_afec_glob, monto_imp3_afec_glob,
                 co_us_in, fe_us_in, co_us_mo, fe_us_mo, rowguid)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                 %s, %s, %s, %s, %s, %s, %s, %s, %s, GETDATE(), %s, GETDATE(), NEWID())
            """
            
            # PASO 5: Procesar items de la cotización
            for idx, item in enumerate(payload.items, 1):
                co_art = item.product_code.strip()
                cantidad = Decimal(str(item.quantity))
                
                # Obtener datos del artículo desde la BD
                art_data = articulos_map.get(co_art)
                if not art_data:
                    raise ValueError(f"Artículo no encontrado: {co_art}")
                
                # Usar precio de la BD (ignorar el del payload)
                precio_unit = art_data.get('precio_base', Decimal('0.00'))
                if precio_unit <= 0:
                    raise ValueError(f"Artículo sin precio configurado: {co_art} (lista '01')")
                
                des_art = art_data.get('art_des') or ''
                tipo_imp = art_data.get('tipo_imp', '1')
                co_uni = art_data.get('co_uni', 'UND')
                
                # Calcular descuento desde saDescArticulo si no se proporciona en el payload
                monto_desc = Decimal(str(item.discount_amount or "0.00"))
                
                if monto_desc == 0:
                    try:
                        discount_info = source_system_service.get_article_discount(
                            article_code=co_art,
                            quantity=cantidad,
                            existing_cursor=cursor
                        )
                        
                        if discount_info and discount_info.get('disponibles', 0) > 0:
                            discount_percentage = discount_info['discount_percentage']
                            subtotal_bruto_temp = (cantidad * precio_unit)
                            monto_desc = (subtotal_bruto_temp * discount_percentage / Decimal('100')).quantize(Decimal('0.01'))
                            
                            # Guardar descuento para incrementar después del COMMIT
                            field_to_increment = discount_info.get('field_to_increment', 'campo1')
                            discounts_to_increment.append({
                                'co_desc': discount_info['co_desc'],
                                'quantity_used': int(cantidad),
                                'field_name': field_to_increment,
                                'co_art': co_art,
                                'disponibles_antes': discount_info.get('disponibles', 0)
                            })
                            logger.info(
                                f"Descuento aplicado | articulo={co_art} | "
                                f"descuento={discount_percentage}% | monto={monto_desc}"
                            )
                    except ConnectionError as conn_err:
                        logger.error(f"Error de conexión obteniendo descuento | articulo={co_art} | {conn_err}")
                        raise ValueError("No se puede crear cotización: error de conexión con BD") from conn_err
                    except Exception as e:
                        logger.warning(f"No se pudo obtener descuento | articulo={co_art} | {e}")
                        monto_desc = Decimal('0.00')
                
                # Cálculos
                subtotal_bruto = (cantidad * precio_unit)
                subtotal_neto = subtotal_bruto - monto_desc
                
                tax_amount_decimal = Decimal(str(item.tax_amount or '0.00'))
                if tax_amount_decimal > 0 and subtotal_neto > 0:
                    monto_imp = tax_amount_decimal
                    porc_imp = (monto_imp / subtotal_neto * 100).quantize(Decimal('0.01'))
                else:
                    porc_imp = porc_imp_default
                    monto_imp = (subtotal_neto * porc_imp / 100).quantize(Decimal('0.01')) if subtotal_neto > 0 else Decimal('0.00')
                
                reng_neto = subtotal_neto + monto_imp
                stotal_art = Decimal('0.00')
                
                # Formatear campos char
                co_art_value = co_art[:30].ljust(30) if len(co_art) < 30 else co_art[:30]
                co_uni_value = co_uni[:6].ljust(6) if len(co_uni) < 6 else co_uni[:6]
                
                # Insertar renglón
                cursor.execute(
                    insert_reng,
                    (
                        reng_num,
                        doc_num,
                        co_art_value,
                        des_art[:120] if des_art else None,
                        co_alma,
                        cantidad,
                        stotal_art,
                        co_uni_value,
                        precio_unit,
                        porc_imp,
                        porc_imp2,
                        porc_imp3,
                        monto_imp,
                        monto_imp2,
                        monto_imp3,
                        monto_desc,
                        reng_neto,
                        tipo_imp,
                        pendiente,
                        pendiente2,
                        total_dev,
                        monto_dev,
                        otros,
                        lote_asignado,
                        monto_desc_glob_reng,
                        monto_reca_glob_reng,
                        otros1_glob_reng,
                        otros2_glob_reng,
                        otros3_glob_reng,
                        monto_imp_afec_glob_reng,
                        monto_imp2_afec_glob_reng,
                        monto_imp3_afec_glob_reng,
                        co_us_in_value,
                        co_us_mo_value,
                    ),
                )
                
                # Acumular totales
                total_bruto += subtotal_bruto
                total_descuentos += monto_desc
                total_impuestos += monto_imp
                reng_num += 1
            # PASO 6: Actualizar cabecera con totales calculados
            total_neto = total_bruto - total_descuentos + total_impuestos
            
            update_totals = """
            UPDATE dbo.saCotizacionCliente
            SET
                total_bruto = %s,
                monto_desc_glob = %s,
                monto_imp = %s,
                total_neto = %s,
                saldo = %s
            WHERE doc_num = %s
            """
            cursor.execute(
                update_totals,
                (total_bruto, total_descuentos, total_impuestos, total_neto, total_neto, doc_num)
            )
            
            # Confirmar transacción
            conn.commit()
            
            # Obtener datos de items para email
            quote_items_for_email = []
            try:
                email_cursor = conn.cursor()
                quote_items_query = """
                SELECT 
                    r.reng_num,
                    RTRIM(r.co_art) AS co_art,
                    ISNULL(a.art_des, r.des_art) AS art_des,
                    r.total_art AS quantity,
                    r.prec_vta AS unit_price,
                    r.monto_desc AS discount_amount,
                    r.monto_imp AS tax_amount
                FROM dbo.saCotizacionClienteReng r WITH (NOLOCK)
                LEFT JOIN dbo.saArticulo a WITH (NOLOCK) ON RTRIM(r.co_art) = RTRIM(a.co_art)
                WHERE r.doc_num = %s
                ORDER BY r.reng_num
                """
                email_cursor.execute(quote_items_query, (doc_num,))
                quote_items_data = email_cursor.fetchall()
                
                for row in quote_items_data:
                    co_art = (row.get('co_art') or '').strip()
                    if co_art:
                        art_des = (row.get('art_des') or '').strip()
                        unit_price_raw = row.get('unit_price', 0) or 0
                        quantity = row.get('quantity', 0) or 0
                        
                        quote_items_for_email.append({
                            'co_art': co_art,
                            'name': art_des if art_des else co_art,
                            'unit_price': f"{float(unit_price_raw):.2f}" if unit_price_raw else '0.00',
                            'quantity': f"{float(quantity):.2f}" if quantity else '0.00',
                            'discount_amount': f"{float(row.get('discount_amount', 0) or 0):.2f}",
                            'tax_amount': f"{float(row.get('tax_amount', 0) or 0):.2f}",
                        })
                
                email_cursor.close()
            except Exception as e:
                logger.warning(f"Error obteniendo items para email | doc_num={doc_num} | {e}")
                quote_items_for_email = []
            
            cursor.close()
            
            # Incrementar contadores de descuentos (después del commit, en transacciones separadas)
            if discounts_to_increment:
                for discount_info in discounts_to_increment:
                    try:
                        source_system_service.increment_discount_usage(
                            co_desc=discount_info['co_desc'],
                            quantity_used=discount_info['quantity_used'],
                            field_name=discount_info['field_name'],
                            existing_cursor=None
                        )
                    except Exception as inc_error:
                        # No fallar la cotización si falla el incremento (ya está creada)
                        logger.error(
                            f"Error incrementando descuento {discount_info['co_desc']} para {discount_info['co_art']}: {inc_error}",
                            exc_info=True
                        )
                        logger.warning(
                            f"La cotización fue creada pero el contador de descuento no se actualizó. "
                            f"Descuento: {discount_info['co_desc']}, Artículo: {discount_info['co_art']}"
                        )
            
            logger.info(
                f"Cotización creada exitosamente: doc_num={doc_num}, "
                f"co_cli={co_cli}, total_bruto={total_bruto}, total_neto={total_neto}"
            )
            
            quote_id = f"COT-{doc_num}"
            
            # El email se enviará desde el endpoint async
            # Por ahora, email_sent_at será None y se actualizará en el endpoint si el email se envía exitosamente
            return QuoteCreatedResponse(
                quote_id=quote_id,
                profit_plus_id=doc_num,
                status="pending",
                currency=currency_code,
                total_net=str(total_bruto.quantize(Decimal('0.01'))),
                total_tax=str(total_impuestos.quantize(Decimal('0.01'))),
                total_gross=str(total_neto.quantize(Decimal('0.01'))),
                expires_at=expires_at_dt.isoformat(),
                email_sent_at=None,  # Se actualizará en el endpoint después de enviar el email
                items_data=quote_items_for_email if quote_items_for_email else None,  # Datos de items para el email
            )
            
        except Exception as e:
            # Revertir transacción en caso de error
            try:
                if conn:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
            except Exception as rollback_error:
                logger.error(f"Error al hacer rollback: {rollback_error}")
            
            # Log con contexto útil para debugging
            logger.error(
                f"Error creando cotización | user_id={user_id} | "
                f"items={len(payload.items) if payload and payload.items else 0} | "
                f"tipo_error={type(e).__name__} | error={e}",
                exc_info=True
            )
                raise
        except Exception as e:
            # Log con contexto útil para debugging (capturar excepciones fuera del with)
            logger.error(
                f"Error creando cotización | user_id={user_id} | "
                f"items={len(payload.items) if payload and payload.items else 0} | "
                f"tipo_error={type(e).__name__} | error={e}",
                exc_info=True
            )
            raise

    def verify_quote_payload(
        self,
        verify_req: QuoteVerifyRequest,
    ) -> QuoteVerifyResponse:
        """
        Verifica artículos, obtiene datos básicos y calcula totales simples.
        """
        from app.services.source_system_service import source_system_service
        if not verify_req.items:
            return QuoteVerifyResponse(
                valido=False,
                co_cli=verify_req.co_cli,
                items_verificados=[],
                totales=QuoteVerifyTotals(bruto="0.00", impuestos="0.00", neto="0.00"),
            )

        # Obtener detalles de artículos en bloque
        co_arts = [it.co_art for it in verify_req.items]
        placeholders = ",".join(["%s"] * len(co_arts))
        query_art = f"""
            SELECT a.co_art, a.art_des
            FROM dbo.saArticulo a WITH (NOLOCK)
            WHERE a.co_art IN ({placeholders})
        """
        # Usar context manager para manejo seguro de conexiones
        with source_system_service.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query_art, tuple(co_arts))
            rows = cursor.fetchall()
            cursor.close()
            art_map = {r.get("co_art"): r.get("art_des") for r in rows} if rows else {}

        # Calcular totales (estimados) con IVA 16% sobre precio 0.00 al no tener pricing aquí
        items_out: List[QuoteVerifyItemResult] = []
        bruto = Decimal('0.00')
        impuestos_total = Decimal('0.00')
        for it in verify_req.items:
            precio_unitario = Decimal('0.00')
            subtotal = (precio_unitario * Decimal(str(it.cantidad)))
            impuesto = (subtotal * Decimal('0.16')).quantize(Decimal('0.01')) if subtotal > 0 else Decimal('0.00')
            bruto += subtotal
            impuestos_total += impuesto

            items_out.append(
                QuoteVerifyItemResult(
                    co_art=it.co_art,
                    cantidad=it.cantidad,
                    precio_unitario=str(precio_unitario.quantize(Decimal('0.01'))),
                    subtotal=str(subtotal.quantize(Decimal('0.01'))),
                    impuestos=str(impuesto),
                    stock_ok=True,
                    nombre_articulo=art_map.get(it.co_art),
                )
            )

        neto = bruto + impuestos_total
        expires_at = (get_ve_now() + timedelta(days=30)).isoformat()
        return QuoteVerifyResponse(
            valido=True,
            co_cli=verify_req.co_cli,
            items_verificados=items_out,
            totales=QuoteVerifyTotals(
                bruto=str(bruto.quantize(Decimal('0.01'))),
                impuestos=str(impuestos_total.quantize(Decimal('0.01'))),
                neto=str(neto.quantize(Decimal('0.01'))),
            ),
            expires_at=expires_at,
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
                logger.warning(f"Usuario {user_id} no encontrado")
                return QuoteListResponse(
                    results=[],
                    pagination=Pagination(page=page, page_size=page_size, total_pages=0, total_items=0)
                )
            # Obtener código de cliente en DEMOA
            customer_code = self._get_customer_code_by_email(user.email)
            if not customer_code:
                
                return QuoteListResponse(
                    results=[],
                    pagination=Pagination(page=page, page_size=page_size, total_pages=0, total_items=0)
                )
            
            # Usar context manager para manejo seguro de conexiones
            offset = (page - 1) * page_size
            
            with source_system_service.connection() as conn:
                cursor = conn.cursor()
                
                # Contar total de cotizaciones (con NOLOCK para evitar bloqueos)
                count_query = """
                SELECT COUNT(DISTINCT c.doc_num) as total
                FROM dbo.saCotizacionCliente c WITH (NOLOCK)
                WHERE c.co_cli = %s AND c.saldo > 0
                """
                cursor.execute(count_query, (customer_code,))
                total_count = cursor.fetchone().get('total', 0)
                
                # Obtener cotizaciones con paginación y conteo de items (con NOLOCK)
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
                FROM dbo.saCotizacionCliente c WITH (NOLOCK)
                LEFT JOIN dbo.saMoneda m WITH (NOLOCK) ON c.co_mone = m.co_mone
                LEFT JOIN (
                    SELECT doc_num, COUNT(*) as items_count
                    FROM dbo.saCotizacionClienteReng WITH (NOLOCK)
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
            
            # Transformar a QuoteListItem
            results = []
            for quote in quotes_data:
                logger.debug(
                    "Procesando cotización para listado",
                    extra={
                        "saldo": str(quote.get('saldo', 0)),
                        "expires_at": quote.get('expires_at').isoformat()
                        if isinstance(quote.get('expires_at'), datetime)
                        else str(quote.get('expires_at')),
                        "profit_plus_id": str(quote.get('profit_plus_id')),
                    },
                )
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
                    email_sent_at=created_at or "",
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
            logger.error(
                f"Error listando cotizaciones | user_id={user_id} | "
                f"tipo_error={type(e).__name__} | error={e}"
            )
            import traceback
            traceback.print_exc()
            response = QuoteListResponse(
                results=[],
                pagination=Pagination(page=page, page_size=page_size, total_pages=0, total_items=0)
            )
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
            # Usar context manager para manejo seguro de conexiones
            # Query con NOLOCK para evitar bloqueos entre lecturas concurrentes
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
            FROM dbo.saCotizacionCliente c WITH (NOLOCK)
            LEFT JOIN dbo.saMoneda m WITH (NOLOCK) ON c.co_mone = m.co_mone
            LEFT JOIN dbo.saCotizacionClienteReng r WITH (NOLOCK) ON c.doc_num = r.doc_num
            LEFT JOIN dbo.saArticulo a WITH (NOLOCK) ON r.co_art = a.co_art
            WHERE c.doc_num = %s
              AND c.co_cli = %s
              AND c.anulado = 0
            ORDER BY r.reng_num
            """
            
            with source_system_service.connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (profit_plus_id, customer_code))
                all_data = cursor.fetchall()
                cursor.close()
                
                if not all_data:
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
            logger.error(
                f"Error obteniendo detalle de cotización | quote_id={quote_id} | "
                f"user_id={user_id} | tipo_error={type(e).__name__} | error={e}"
            )
            import traceback
            traceback.print_exc()
            return None

    def cancel_quote(
        self,
        user_id: int,
        quote_id: str,
        source_system: str,
    ) -> bool:
        """
        Anula una cotización (soft delete) actualizando el campo anulado = 1.
        No elimina físicamente los registros para mantener integridad contable.
        
        Args:
            user_id: ID del usuario en la BD local
            quote_id: ID de la cotización (formato COT-XXXXX o solo el código)
            source_system: Sistema fuente (profit_plus)
            
        Returns:
            bool: True si se anuló exitosamente, False si no se encontró o ya estaba anulada
        """
        try:
            # Extraer profit_plus_id del quote_id
            profit_plus_id = quote_id.replace("COT-", "") if quote_id.startswith("COT-") else quote_id
            profit_plus_id = profit_plus_id.strip()
            
            # Obtener email del usuario
            from app.models.user import User
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.warning(f"Usuario {user_id} no encontrado")
                return False
            
            # Obtener código de cliente
            customer_code = self._get_customer_code_by_email(user.email)
            if not customer_code:
                logger.warning(f"Cliente no encontrado en DEMOA para email {user.email}")
                return False
            customer_code = customer_code.strip() if customer_code else None
            
            # Verificar que la cotización existe y pertenece al cliente
            try:
                with source_system_service.connection() as conn:
                    cursor = conn.cursor()
                    
                    # Limpiar cualquier transacción pendiente de la conexión reutilizada
                    try:
                        cursor.execute("IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION")
                    except Exception:
                        pass  # Ignorar si no hay transacción pendiente
                    
                    # Iniciar transacción (manejada por pymssql)
                    cursor.execute("BEGIN TRANSACTION")
                
                # Verificar que la cotización existe y pertenece al cliente
                check_query = """
                SELECT doc_num, anulado, co_cli
                FROM dbo.saCotizacionCliente
                WHERE doc_num = %s AND RTRIM(co_cli) = %s
                """
                cursor.execute(check_query, (profit_plus_id, customer_code))
                quote_data = cursor.fetchone()
                
                if not quote_data:
                    # cursor.execute("ROLLBACK TRANSACTION")
                    conn.rollback()
                    logger.warning(f"Cotización {profit_plus_id} no encontrada para cliente {customer_code}")
                    return False
                
                # Verificar si ya está anulada
                if quote_data.get('anulado', 0) == 1:
                    # cursor.execute("ROLLBACK TRANSACTION")
                    conn.rollback()
                    logger.info(f"Cotización {profit_plus_id} ya está anulada")
                    return False
                
                # Anular la cotización (soft delete)
                update_query = """
                UPDATE dbo.saCotizacionCliente
                SET anulado = 1,
                    co_us_mo = %s,
                    fe_us_mo = GETDATE()
                WHERE doc_num = %s
                """
                co_us_mo = "SA"  # Usuario del sistema
                cursor.execute(update_query, (co_us_mo, profit_plus_id))
                
                # Confirmar transacción
                conn.commit()
                
                    logger.info(f"Cotización {profit_plus_id} anulada exitosamente por usuario {user_id}")
                    cursor.close()
                    return True
                    
            except Exception as e:
                logger.error(f"Error anulando cotización {profit_plus_id}: {str(e)}", exc_info=True)
                raise
                
        except Exception as e:
            logger.error(
                f"Error cancelando cotización | quote_id={quote_id} | "
                f"user_id={user_id} | tipo_error={type(e).__name__} | error={e}"
            )
            return False

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

    def validate_cart(
        self,
        cart_request: CartValidationRequest,
        user_email: str,
        price_code: str = "01",
        warehouse_code: str = "001",
    ) -> CartValidationResponse:
        """
        Valida un carrito de compras enviado por el frontend.
        
        Principio: Desconfianza absoluta. Solo se confía en co_art y cantidad.
        Todos los demás datos (precio, descripción, impuestos, disponibilidad)
        se obtienen y calculan desde la base de datos.
        
        Args:
            cart_request: Request con lista de items (solo co_art y cantidad)
            user_email: Email del usuario autenticado (para obtener co_cli si es necesario)
            price_code: Código de lista de precios (default: "01")
            warehouse_code: Código de almacén para verificar stock (default: "001")
            
        Returns:
            CartValidationResponse con datos autoritativos calculados por el backend
        """
        if not cart_request.items:
            return CartValidationResponse(
                valido=False,
                items_verificados=[],
                totales=CartValidationTotals(bruto="0.00", impuestos="0.00", neto="0.00"),
            )

        # 1. Extraer códigos de artículos para consulta masiva
        co_arts = [item.co_art for item in cart_request.items]
        if not co_arts:
            return CartValidationResponse(
                valido=False,
                items_verificados=[],
                totales=CartValidationTotals(bruto="0.00", impuestos="0.00", neto="0.00"),
            )

        # 2. Consulta masiva a la base de datos (evita problema N+1)
        # Limpiar códigos de artículo (eliminar espacios)
        co_arts_clean = [co_art.strip() if co_art else "" for co_art in co_arts]
        co_arts_clean = [co_art for co_art in co_arts_clean if co_art]  # Eliminar vacíos
        
        if not co_arts_clean:
            return CartValidationResponse(
                valido=False,
                items_verificados=[],
                totales=CartValidationTotals(bruto="0.00", impuestos="0.00", neto="0.00"),
            )
        
        # Construir placeholders para la consulta IN
        placeholders = ",".join(["%s"] * len(co_arts_clean))
        
        # Query masiva con NOLOCK para evitar bloqueos entre lecturas concurrentes
        query = f"""
            SELECT
                RTRIM(a.co_art) AS co_art,
                a.art_des,
                a.anulado,
                ISNULL(stock_data.stock, 0) AS stock,
                ISNULL(precio_data.price, 0) AS precio_base
            FROM dbo.saArticulo AS a WITH (NOLOCK)
            -- Stock del almacén principal
            OUTER APPLY (
                SELECT 
                    SUM(sa.stock) AS stock
                FROM dbo.saStockAlmacen sa WITH (NOLOCK)
                WHERE sa.co_art = a.co_art 
                    AND RTRIM(sa.co_alma) = %s
                    AND sa.tipo = 'ACT'  -- Solo stock actual
            ) stock_data
            -- Precio: Obtener el precio más reciente de la lista de precios
            OUTER APPLY (
                SELECT TOP 1 
                    ap.monto AS price
                FROM dbo.saArtPrecio ap WITH (NOLOCK)
                WHERE ap.co_art = a.co_art 
                    AND RTRIM(ap.co_precio) = %s
                ORDER BY ap.desde DESC  -- Precio más reciente (fecha más actual)
            ) precio_data
            WHERE RTRIM(a.co_art) IN ({placeholders})
        """
        
        # Usar context manager para manejo seguro de conexiones
        with source_system_service.connection() as conn:
            cursor = conn.cursor()
            
            # Parámetros: warehouse_code, price_code, luego los co_arts limpios
            params = [warehouse_code, price_code] + co_arts_clean
            cursor.execute(query, tuple(params))
            db_results = cursor.fetchall()
            cursor.close()
            
            # Crear mapa de resultados por co_art (usando RTRIM para normalizar)
            article_map = {}
            for row in db_results:
                co_art = (row.get("co_art") or "").strip()
                if co_art:
                    article_map[co_art] = {
                        "art_des": row.get("art_des"),
                        "anulado": row.get("anulado", 1),
                        "stock": Decimal(str(row.get("stock", 0) or 0)),
                        "precio_base": Decimal(str(row.get("precio_base", 0) or 0)),
                    }

        # 3. Obtener código de cliente para consultar descuentos
        co_cli = None
        if user_email:
            customer_data = self._get_customer_code_by_email(user_email)
            if customer_data:
                co_cli = customer_data.strip()

        # 4. Procesar y validar cada item
        items_verificados: List[CartValidationItemResult] = []
        total_bruto = Decimal('0.00')
        total_impuestos = Decimal('0.00')
        total_descuentos = Decimal('0.00')
        all_valid = True

        for item in cart_request.items:
            # Limpiar código de artículo (eliminar espacios)
            co_art = (item.co_art or "").strip()
            cantidad = Decimal(str(item.cantidad))
            
            # Obtener datos del artículo desde el mapa (usando código limpio)
            article_data = article_map.get(co_art)
            
            # Validaciones
            error_msg = None
            precio_unitario = Decimal('0.00')
            subtotal = Decimal('0.00')
            impuestos = Decimal('0.00')
            descuento = Decimal('0.00')
            stock_ok = False
            descripcion = None
            
            if not article_data:
                # Artículo no existe
                error_msg = "El artículo no existe o no está disponible."
                all_valid = False
            else:
                descripcion = article_data.get("art_des")
                
                # Validar que el artículo esté activo
                if article_data.get("anulado", 1) != 0:
                    error_msg = "El artículo está anulado o no está disponible."
                    all_valid = False
                else:
                    # Validar stock
                    stock_disponible = article_data.get("stock", Decimal('0.00'))
                    if stock_disponible < cantidad:
                        error_msg = f"Stock insuficiente. Disponible: {stock_disponible}, Solicitado: {cantidad}."
                        all_valid = False
                        stock_ok = False
                    else:
                        stock_ok = True
                    
                    # Calcular precio real (ignorar cualquier precio del frontend)
                    precio_unitario = article_data.get("precio_base", Decimal('0.00'))
                    
                    # Calcular subtotal bruto (antes de descuentos)
                    subtotal_bruto = (precio_unitario * cantidad).quantize(Decimal('0.01'))
                    
                    # Consultar descuento desde saDescArticulo
                    descuento_info_dict = None
                    try:
                        discount_info = source_system_service.get_article_discount(
                            article_code=co_art,
                            quantity=cantidad
                        )
                        
                        if discount_info and discount_info.get('disponibles', 0) > 0:
                            discount_percentage = discount_info['discount_percentage']
                            # Calcular monto de descuento
                            descuento = (subtotal_bruto * discount_percentage / Decimal('100')).quantize(Decimal('0.01'))
                            
                            # Preparar información del descuento para la respuesta
                            descuento_info_dict = {
                                "co_desc": discount_info.get('co_desc', ''),
                                "porcentaje": float(discount_percentage),
                                "disponibles": discount_info.get('disponibles', 0),
                                "limite_total": discount_info.get('limite_total', 0)
                            }
                    except ConnectionError as conn_err:
                        # Error de conexión - marcar item como inválido
                        logger.error(f"Error de conexión al validar descuento para {co_art}: {conn_err}")
                        error_msg = "Error de conexión con la base de datos"
                        all_valid = False
                        descuento = Decimal('0.00')
                    except Exception as e:
                        logger.warning(f"Error obteniendo descuento para artículo {co_art}: {e}")
                        # Continuar sin descuento si hay error (no es de conexión)
                        descuento = Decimal('0.00')
                    
                    # Calcular subtotal después de descuento
                    subtotal = (subtotal_bruto - descuento).quantize(Decimal('0.01'))
                    
                    # Calcular impuestos usando 16% fijo (IVA estándar) sobre el subtotal después de descuento
                    tasa_impuesto = Decimal('16.00')  # 16% IVA
                    if subtotal > 0:
                        impuestos = (subtotal * tasa_impuesto / Decimal('100')).quantize(Decimal('0.01'))
                    else:
                        impuestos = Decimal('0.00')
                    
                    # Acumular totales solo si el artículo es válido
                    total_bruto += subtotal_bruto
                    total_descuentos += descuento
                    total_impuestos += impuestos

            # Construir resultado del item
            items_verificados.append(
                CartValidationItemResult(
                    co_art=co_art,
                    descripcion=descripcion,
                    cantidad=float(cantidad),
                    precio_unitario_real=str(precio_unitario.quantize(Decimal('0.01'))),
                    subtotal=str(subtotal.quantize(Decimal('0.01'))),
                    impuestos=str(impuestos.quantize(Decimal('0.01'))),
                    descuento=str(descuento.quantize(Decimal('0.01'))),
                    descuento_info=descuento_info_dict,
                    stock_ok=stock_ok,
                    error=error_msg,
                )
            )

        # 5. Calcular totales finales (bruto - descuentos + impuestos)
        total_neto = (total_bruto - total_descuentos + total_impuestos).quantize(Decimal('0.01'))
        
        return CartValidationResponse(
            valido=all_valid,
            items_verificados=items_verificados,
            totales=CartValidationTotals(
                bruto=str(total_bruto.quantize(Decimal('0.01'))),
                impuestos=str(total_impuestos.quantize(Decimal('0.01'))),
                descuentos=str(total_descuentos.quantize(Decimal('0.01'))),
                neto=str(total_neto),
            ),
        )


