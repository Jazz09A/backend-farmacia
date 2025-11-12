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
        
        print(f"saldo: {saldo}")
        print(f"fec_venc: {fec_venc}")
        print(f"now: {now}")
        
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
            Nuevo doc_num formateado como string de 20 caracteres
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
        
        # Formatear a 20 caracteres con ceros a la izquierda
        return str(new_num).zfill(20)

    def create_quote(
        self,
        user_id: int,
        payload: QuoteCreate,
        source_system: str,
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
        co_cli = payload.customer.code.strip() if payload.customer and payload.customer.code else None
        if not co_cli:
            raise ValueError("Customer code (co_cli) es requerido para crear la cotización")

        # Valores por defecto según el script
        co_ven = "003"  # Código de vendedor para E-Commerce (configurar aquí el código deseado)
        descrip_cotizacion = payload.notes or "Cotización desde E-Commerce"
        co_us_in = "SA"  # Usuario del sistema
        co_alma = "001"  # Almacén principal (ajustar según configuración)
        tasa = Decimal('1.00')  # Tasa de cambio (1.00 para misma moneda, ajustar si es necesario)
        porc_imp_default = Decimal('16.00')  # 16% IVA por defecto

        conn = source_system_service.get_connection()
        cursor = conn.cursor()
        
        try:
            # Iniciar transacción explícita
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
            
            # PASO 2: Obtener dirección de entrega desde la ficha del cliente
            query_cliente = """
            SELECT direc1
            FROM dbo.saCliente
            WHERE co_cli = %s
            """
            cursor.execute(query_cliente, (co_cli,))
            cliente_row = cursor.fetchone()
            
            # Validar que el cliente existe
            if not cliente_row:
                raise ValueError(f"Cliente con código '{co_cli}' no existe en la base de datos. Verifique el código de cliente.")
            
            direccion_entrega = cliente_row.get('direc1') if cliente_row else None
            
            if not direccion_entrega:
                logger.warning(f"No se encontró dirección de entrega para cliente {co_cli}, usando NULL")
            
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
            
            # PASO 3: Obtener datos de artículos (descripción, tipo de impuesto y unidad de medida)
            co_arts = [item.product_code.strip() for item in payload.items if item.product_code]
            if not co_arts:
                raise ValueError("No se proporcionaron artículos para la cotización")
            
            placeholders = ",".join(["%s"] * len(co_arts))
            query_articulos = f"""
            SELECT 
                a.co_art,
                a.art_des,
                ISNULL(a.tipo_imp, '1') AS tipo_imp,
                ISNULL(au.co_uni, 'UND') AS co_uni
            FROM dbo.saArticulo a
            LEFT JOIN dbo.saArtUnidad au ON a.co_art = au.co_art AND au.uni_principal = 1
            WHERE a.co_art IN ({placeholders})
            """
            cursor.execute(query_articulos, tuple(co_arts))
            articulos_data = cursor.fetchall()
            articulos_map = {
                (row.get('co_art') or '').strip(): {
                    'art_des': row.get('art_des'),
                    'tipo_imp': row.get('tipo_imp', '1'),
                    'co_uni': (row.get('co_uni') or 'UND').strip()
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
            reng_num = 1
            
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
            
            for item in payload.items:
                co_art = item.product_code.strip()
                cantidad = Decimal(str(item.quantity))
                precio_unit = Decimal(str(item.unit_price))
                monto_desc = Decimal(str(item.discount_amount or "0.00"))
                
                # Obtener datos del artículo
                art_data = articulos_map.get(co_art)
                if not art_data:
                    raise ValueError(f"Artículo {co_art} no encontrado en la base de datos")
                
                des_art = art_data.get('art_des') or item.product_name or ''
                tipo_imp = art_data.get('tipo_imp', '1')
                co_uni = art_data.get('co_uni', 'UND')  # Obtener unidad de medida del artículo
                
                # Calcular impuestos
                # Usar el porcentaje del payload si viene, sino usar el default
                if item.tax_amount:
                    # Si viene monto de impuesto, calcular el porcentaje
                    subtotal_bruto = (cantidad * precio_unit) - monto_desc
                    if subtotal_bruto > 0:
                        monto_imp = Decimal(str(item.tax_amount))
                        porc_imp = (monto_imp / subtotal_bruto * 100).quantize(Decimal('0.01'))
                    else:
                        monto_imp = Decimal('0.00')
                        porc_imp = Decimal('0.00')
                else:
                    # Calcular impuesto usando porcentaje por defecto
                    subtotal_bruto = (cantidad * precio_unit) - monto_desc
                    porc_imp = porc_imp_default
                    monto_imp = (subtotal_bruto * porc_imp / 100).quantize(Decimal('0.01'))
                
                # Calcular reng_neto (cantidad * precio + impuesto - descuento)
                reng_neto = (cantidad * precio_unit) + monto_imp - monto_desc
                
                # stotal_art es igual a total_art (cantidad) según el usuario
                stotal_art = Decimal('0.00')
                
                # Asegurar que co_art y co_uni respeten sus límites
                co_art_value = co_art[:30] if len(co_art) > 30 else co_art.ljust(30) if len(co_art) < 30 else co_art
                co_uni_value = co_uni[:6] if len(co_uni) > 6 else co_uni.ljust(6) if len(co_uni) < 6 else co_uni
                
                # Insertar renglón
                cursor.execute(
                    insert_reng,
                    (
                        reng_num,
                        doc_num,
                        co_art_value,
                        des_art[:120] if des_art else None,  # Limitar longitud a 120
                        co_alma,
                        cantidad,
                        stotal_art,  # stotal_art = total_art
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
                total_bruto += (cantidad * precio_unit) - monto_desc
                total_impuestos += monto_imp
                
                reng_num += 1
            
            # PASO 6: Actualizar cabecera con totales calculados
            total_neto = total_bruto + total_impuestos
            
            update_totals = """
            UPDATE dbo.saCotizacionCliente
            SET
                total_bruto = %s,
                monto_imp = %s,
                total_neto = %s,
                saldo = %s
            WHERE doc_num = %s
            """
            cursor.execute(
                update_totals,
                (total_bruto, total_impuestos, total_neto, total_neto, doc_num)
            )
            
            # Confirmar transacción
            cursor.execute("COMMIT TRANSACTION")
            conn.commit()
            
            logger.info(
                f"Cotización creada exitosamente: doc_num={doc_num}, "
                f"co_cli={co_cli}, total_bruto={total_bruto}, total_neto={total_neto}"
            )
            
            quote_id = f"COT-{doc_num}"
            return QuoteCreatedResponse(
                quote_id=quote_id,
                profit_plus_id=doc_num,
                status="pending",
                currency=currency_code,
                total_net=str(total_bruto.quantize(Decimal('0.01'))),
                total_tax=str(total_impuestos.quantize(Decimal('0.01'))),
                total_gross=str(total_neto.quantize(Decimal('0.01'))),
                expires_at=expires_at_dt.isoformat(),
                email_sent_at=now.isoformat(),
            )
            
        except Exception as e:
            # Revertir transacción en caso de error
            try:
                cursor.execute("ROLLBACK TRANSACTION")
                conn.rollback()
            except Exception as rollback_error:
                logger.error(f"Error al hacer rollback: {rollback_error}")
            
            logger.error(f"Error creando cotización: {str(e)}", exc_info=True)
            raise
        finally:
            cursor.close()
            conn.close()

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
            FROM dbo.saArticulo a
            WHERE a.co_art IN ({placeholders})
        """
        conn = source_system_service.get_connection()
        cursor = conn.cursor()
        cursor.execute(query_art, tuple(co_arts))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
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
        conn = source_system_service.get_connection()
        cursor = conn.cursor()
        
        try:
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
            
            # Query masiva: artículos, stock, precio (usando OUTER APPLY como en el catálogo)
            query = f"""
                SELECT
                    RTRIM(a.co_art) AS co_art,
                    a.art_des,
                    a.anulado,
                    ISNULL(stock_data.stock, 0) AS stock,
                    ISNULL(precio_data.price, 0) AS precio_base
                FROM dbo.saArticulo AS a
                -- Stock del almacén principal
                OUTER APPLY (
                    SELECT 
                        SUM(sa.stock) AS stock
                    FROM dbo.saStockAlmacen sa
                    WHERE sa.co_art = a.co_art 
                        AND RTRIM(sa.co_alma) = %s
                ) stock_data
                -- Precio: Obtener el precio más reciente de la lista de precios
                OUTER APPLY (
                    SELECT TOP 1 
                        ap.monto AS price
                    FROM dbo.saArtPrecio ap
                    WHERE ap.co_art = a.co_art 
                        AND RTRIM(ap.co_precio) = %s
                    ORDER BY ap.desde DESC  -- Precio más reciente (fecha más actual)
                ) precio_data
                WHERE RTRIM(a.co_art) IN ({placeholders})
            """
            
            # Parámetros: warehouse_code, price_code, luego los co_arts limpios
            params = [warehouse_code, price_code] + co_arts_clean
            cursor.execute(query, tuple(params))
            db_results = cursor.fetchall()
            
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
            
        finally:
            cursor.close()
            conn.close()

        # 3. Procesar y validar cada item
        items_verificados: List[CartValidationItemResult] = []
        total_bruto = Decimal('0.00')
        total_impuestos = Decimal('0.00')
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
                    
                    # Calcular subtotal
                    subtotal = (precio_unitario * cantidad).quantize(Decimal('0.01'))
                    
                    # Calcular impuestos usando 16% fijo (IVA estándar)
                    tasa_impuesto = Decimal('16.00')  # 16% IVA
                    if subtotal > 0:
                        impuestos = (subtotal * tasa_impuesto / Decimal('100')).quantize(Decimal('0.01'))
                    else:
                        impuestos = Decimal('0.00')
                    
                    # Acumular totales solo si el artículo es válido
                    total_bruto += subtotal
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
                    stock_ok=stock_ok,
                    error=error_msg,
                )
            )

        # 4. Calcular totales finales
        total_neto = (total_bruto + total_impuestos).quantize(Decimal('0.01'))
        
        return CartValidationResponse(
            valido=all_valid,
            items_verificados=items_verificados,
            totales=CartValidationTotals(
                bruto=str(total_bruto.quantize(Decimal('0.01'))),
                impuestos=str(total_impuestos.quantize(Decimal('0.01'))),
                neto=str(total_neto),
            ),
        )


