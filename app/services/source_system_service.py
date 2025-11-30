import pymssql
from typing import List, Optional, Dict, Any, Tuple
from uuid import uuid4
from decimal import Decimal
from app.config.settings import Settings
from app.config.logging_config import get_logger

settings = Settings()
class SourceSystemService:
    """Servicio para conectar y consultar la base de datos SourceSystem"""
    def __init__(self):
        self.logger = get_logger("source_system")
        # Limpiar espacios en blanco de todos los parámetros
        self.server = settings.SOURCE_SYSTEM_SERVER.strip() if settings.SOURCE_SYSTEM_SERVER else None
        self.port = settings.SOURCE_SYSTEM_PORT
        self.database = settings.SOURCE_SYSTEM_DATABASE.strip() if settings.SOURCE_SYSTEM_DATABASE else None
        # Limpiar espacios en blanco de usuario y contraseña para evitar errores de autenticación
        # NOTA: El usuario puede tener guion bajo al final si es parte del nombre real (ej: alvarobbsita_)
        self.user = settings.SOURCE_SYSTEM_USER.strip() if settings.SOURCE_SYSTEM_USER else None
        self.password = settings.SOURCE_SYSTEM_PASSWORD.strip() if settings.SOURCE_SYSTEM_PASSWORD else None
        
        # Log de configuración (sin mostrar contraseña completa)
        if self.user:
            self.logger.info(f"SourceSystem configurado - Server: {self.server}, DB: {self.database}, User: {self.user[:3]}***")
        else:
            self.logger.info(f"SourceSystem configurado - Server: {self.server}, DB: {self.database}, User: (sin autenticación)")

    def get_connection(self):
        try:
            # Validar que los parámetros básicos estén configurados
            if not self.server:
                raise ValueError("SOURCE_SYSTEM_SERVER no está configurado")
            if not self.database:
                raise ValueError("SOURCE_SYSTEM_DATABASE no está configurado")
            
            # Preparar parámetros de conexión
            # El servidor puede incluir instancia (ej: sql.bsite.net\MSSQL2016)
            server_clean = self.server.strip() if isinstance(self.server, str) else self.server
            database_clean = self.database.strip() if isinstance(self.database, str) else self.database
            self.logger.debug(
                "Parámetros de conexión depurados",
                extra={
                    "server": server_clean,
                    "database": database_clean,
                    "port": self.port,
                },
            )
            connect_kwargs = {
                "server": server_clean,
                "port": self.port,
                "database": database_clean,
                "as_dict": True,
                "login_timeout": 15,  # Segundos para establecer conexión
                "timeout": 30,        # Segundos para queries
            }
            
            # Solo agregar credenciales si están configuradas
            # Asegurar que se limpien espacios en blanco (pero mantener guiones bajos si son parte del nombre)
            if self.user and self.password:
                user_clean = self.user.strip() if isinstance(self.user, str) else self.user
                password_clean = self.password.strip() if isinstance(self.password, str) else self.password
                
                if not user_clean or not password_clean:
                    self.logger.warning("Usuario o contraseña están vacíos después de limpiar espacios")
                else:
                    connect_kwargs["user"] = user_clean
                    connect_kwargs["password"] = password_clean
                    # Log del usuario completo para debugging (solo en modo debug)
                    self.logger.debug(f"Usuario de conexión: '{user_clean}' (longitud: {len(user_clean)})")
            
            # Log de parámetros de conexión (sin contraseña)
            self.logger.info(f"Conectando a SourceSystem: {server_clean}:{self.port}/{database_clean}")
            self.logger.debug(f"Parámetros de conexión: {connect_kwargs}")
            conn = pymssql.connect(**connect_kwargs)
            self.logger.info("Conexión a SourceSystem establecida exitosamente")
            return conn
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Error conectando a SourceSystem: {error_msg}")
            
            # Proporcionar información adicional para debugging
            if "18456" in error_msg:
                self.logger.error("Error 18456: Fallo de autenticación. Verificar usuario y contraseña.")
            if "20002" in error_msg:
                self.logger.error("Error 20002: No se pudo conectar al servidor. Verificar conectividad de red.")

            raise

    def get_all_customers(
        self,
        include_inactive: bool = False,
        only_with_email: bool = True,
        limit: int = None,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            query = """
            SELECT 
                RTRIM(co_cli) AS customer_code,
                RTRIM(cli_des) AS customer_name,
                email,
                email_alterno AS alternate_email,
                rif,
                telefonos AS phones,
                direc1 AS address1,
                direc2 AS address2,
                RTRIM(tip_cli) AS tip_cli,
                inactivo AS inactive,
                juridico AS is_juridico,
                fecha_reg AS registration_date
            FROM saCliente
            WHERE 1=1
            """

            if not include_inactive:
                query += " AND inactivo = 0"
            if only_with_email:
                query += " AND (email IS NOT NULL AND email != '' OR email_alterno IS NOT NULL AND email_alterno != '')"
                
            query += " ORDER BY cli_des"

            if limit:
                query += f" OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY"

            cursor.execute(query)
            customers = cursor.fetchall()

            cursor.close()
            conn.close()

            return customers
        except Exception as e:
            self.logger.error(f"Error obteniendo clientes de SourceSystem: {str(e)}")
            raise

    def get_customer_by_code(self, customer_code: str) -> Optional[Dict[str, Any]]:
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            query = """
            SELECT 
                RTRIM(co_cli) AS customer_code,
                RTRIM(cli_des) AS customer_name,
                email,
                email_alterno AS alternate_email,
                rif,
                telefonos AS phones,
                direc1 AS address1,
                direc2 AS address2,
                RTRIM(tip_cli) AS tip_cli,
                inactivo AS inactive,
                juridico AS is_juridico,
                fecha_reg AS registration_date
            FROM saCliente
            WHERE co_cli = %s
            """
            cursor.execute(query, (customer_code,))
            customer = cursor.fetchone()
            cursor.close()
            conn.close()
            return customer
        except Exception as e:
            self.logger.error(f"Error obteniendo cliente {customer_code}: {str(e)}")
            raise

    def get_customer_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            query = """
            SELECT 
                co_cli AS customer_code,
                cli_des AS customer_name,
                email,
                email_alterno AS alternate_email,
                rif,
                telefonos AS phones,
                direc1 AS address1,
                direc2 AS address2,
                inactivo AS inactive,
                juridico AS is_juridico,
                fecha_reg AS registration_date
            FROM saCliente
            WHERE email = %s OR email_alterno = %s
            """
            cursor.execute(query, (email, email))
            customer = cursor.fetchone()
            cursor.close()
            conn.close()
            return customer
        except Exception as e:
            self.logger.error(f"Error obteniendo cliente por email {email}: {str(e)}")
            raise

    def get_profit_customer_profile(self, email: str) -> Dict[str, Any]:
        """
        Obtiene el perfil del cliente en Profit Plus a partir del email.
        Retorna código de cliente, tipo de cliente y nombre.
        """
        customer = self.get_customer_by_email(email)
        if not customer:
            raise ValueError(
                f"No se encontró un cliente en Profit Plus asociado al email {email}"
            )

        customer_code = (customer.get("customer_code") or "").strip()
        tip_cli = (customer.get("tip_cli") or "").strip()
        customer_name = (customer.get("customer_name") or "").strip()

        if not customer_code:
            raise ValueError(
                f"El cliente asociado al email {email} no tiene código (co_cli) en Profit Plus"
            )

        if not tip_cli:
            # Si el cliente no tiene tip_cli asignado, usar el tipo más común
            # 001 = SUPERMERCADOS, BODEGONES, PANADERIAS Y OTROS (cliente general)
            tip_cli = "007"
            self.logger.warning(
                f"Cliente {customer_code} ({email}) no tiene tip_cli asignado. "
                f"Usando valor por defecto: {tip_cli}"
            )

        return {
            "customer_code": customer_code,
            "tip_cli": tip_cli,
            "customer_name": customer_name,
        }

    def build_profit_user_code(self, customer_code: str) -> str:
        """
        Devuelve un código válido (char(6)) para los campos co_us_in / co_us_mo.
        Se basa en el código de cliente cuando es posible.
        """
        fallback = "API"
        if not customer_code:
            return fallback

        normalized = customer_code.strip().upper()
        if not normalized:
            return fallback

        # Limitar a 6 caracteres y rellenar con espacios si es necesario
        return normalized[:6].ljust(6)

    def generate_discount_code(self, prefix: str = "DESC") -> str:
        """
        Genera un nuevo código co_desc (char(6)) para saDescArticulo.
        Usa un prefijo y completa con dígitos incrementales.
        """
        prefix_clean = (prefix or "DESC").strip().upper()
        max_length = 6
        numeric_width = max(1, max_length - len(prefix_clean))
        if numeric_width <= 0:
            raise ValueError("El prefijo para co_desc no puede exceder 6 caracteres")

        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            like_pattern = f"{prefix_clean}%"
            query = """
                SELECT TOP 1 RTRIM(co_desc) AS co_desc
                FROM dbo.saDescArticulo
                WHERE co_desc LIKE %s
                ORDER BY co_desc DESC
            """
            cursor.execute(query, (like_pattern,))
            row = cursor.fetchone()

            if row and row.get("co_desc"):
                last_code = row["co_desc"].strip()
                numeric_part = last_code[len(prefix_clean):]
                try:
                    next_number = int(numeric_part or "0") + 1
                except ValueError:
                    next_number = 1
            else:
                next_number = 1

            new_code = f"{prefix_clean}{str(next_number).zfill(numeric_width)}"
            return new_code[:max_length]
        finally:
            cursor.close()
            conn.close()
    
    def get_customer_addresses(self, customer_code: str) -> List[Dict[str, Any]]:
        """
        Obtiene las direcciones de un cliente desde Profit Plus (saCliente).
        
        Args:
            customer_code: Código de cliente (co_cli)
            
        Returns:
            Lista de direcciones del cliente
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            query = """
            SELECT 
                co_cli AS customer_code,
                RTRIM(direc1) AS address1,
                RTRIM(dir_ent2) AS delivery_address2,
                RTRIM(direc2) AS address2,
                RTRIM(ciudad) AS city,
                RTRIM(zip) AS postal_code,
                RTRIM(telefonos) AS phones,
                RTRIM(cli_des) AS customer_name
            FROM dbo.saCliente
            WHERE RTRIM(co_cli) = %s
            """
            cursor.execute(query, (customer_code.strip(),))
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if not result:
                return []
            
            # Construir lista de direcciones disponibles
            addresses = []
            
            # Dirección principal (direc1)
            if result.get('address1'):
                addresses.append({
                    'type': 'principal',
                    'label': 'Dirección Principal',
                    'address': result.get('address1', '').strip(),
                    'city': result.get('city', '').strip() if result.get('city') else None,
                    'postal_code': result.get('postal_code', '').strip() if result.get('postal_code') else None,
                    'phones': result.get('phones', '').strip() if result.get('phones') else None,
                    'customer_name': result.get('customer_name', '').strip() if result.get('customer_name') else None,
                })
            
            # Dirección de entrega 2 (dir_ent2)
            if result.get('delivery_address2'):
                addresses.append({
                    'type': 'entrega',
                    'label': 'Dirección de Entrega',
                    'address': result.get('delivery_address2', '').strip(),
                    'city': result.get('city', '').strip() if result.get('city') else None,
                    'postal_code': result.get('postal_code', '').strip() if result.get('postal_code') else None,
                    'phones': result.get('phones', '').strip() if result.get('phones') else None,
                    'customer_name': result.get('customer_name', '').strip() if result.get('customer_name') else None,
                })
            
            # Dirección secundaria (direc2)
            if result.get('address2'):
                addresses.append({
                    'type': 'secundaria',
                    'label': 'Dirección Secundaria',
                    'address': result.get('address2', '').strip(),
                    'city': result.get('city', '').strip() if result.get('city') else None,
                    'postal_code': result.get('postal_code', '').strip() if result.get('postal_code') else None,
                    'phones': result.get('phones', '').strip() if result.get('phones') else None,
                    'customer_name': result.get('customer_name', '').strip() if result.get('customer_name') else None,
                })
            
            return addresses
        except Exception as e:
            self.logger.error(f"Error obteniendo direcciones para cliente {customer_code}: {str(e)}")
            raise
    
    # =========================================================================
    # Artículos e Imágenes (Profit Plus)
    # =========================================================================

    def get_articles_catalog(
        self,
        page: int = 1,
        limit: int = 20,
        search: Optional[str] = None,
        line_code: Optional[str] = None,
        category_code: Optional[str] = None,
        min_price: Optional[Decimal] = None,
        max_price: Optional[Decimal] = None,
        sort_by: str = "art_des",
        price_code: str = "01",
        warehouse_code: str = "001",
    ) -> Dict[str, Any]:
        """
        Obtiene un catálogo paginado de artículos desde Profit Plus utilizando
        saArticulo, saArtPrecio y saStockAlmacen.
        """
        offset = (page - 1) * limit
        filters = ["a.anulado = 0"]
        # Nota: Los parámetros deben estar en el orden correcto para los OUTER APPLY
        params: List[Any] = [warehouse_code, price_code]

        if search:
            filters.append("(a.art_des LIKE %s OR a.co_art LIKE %s)")
            search_param = f"%{search}%"
            params.extend([search_param, search_param])

        if line_code:
            filters.append("RTRIM(a.co_lin) = %s")
            params.append(line_code)

        if category_code:
            filters.append("RTRIM(a.co_cat) = %s")
            params.append(category_code)

        if min_price is not None:
            filters.append("(ap.price IS NOT NULL AND ap.price >= %s)")
            params.append(Decimal(min_price))

        if max_price is not None:
            filters.append("(ap.price IS NOT NULL AND ap.price <= %s)")
            params.append(Decimal(max_price))

        where_clause = " AND ".join(filters)

        sort_mapping = {
            "art_des": "a.art_des ASC",
            "art_des_desc": "a.art_des DESC",
            "price_asc": "ap.price ASC",
            "price_desc": "ap.price DESC",
            "stock_asc": "stock_data.stock ASC",
            "stock_desc": "stock_data.stock DESC",
        }
        order_by = sort_mapping.get(sort_by, "a.art_des ASC")

        base_query = f"""
            FROM dbo.saArticulo a
            LEFT JOIN dbo.saCatArticulo cat ON RTRIM(a.co_cat) = RTRIM(cat.co_cat)
            -- Stock: Sumar todos los stocks del mismo almacén para el mismo artículo
            OUTER APPLY (
                SELECT 
                    RTRIM(sa.co_alma) AS co_alma,
                    SUM(sa.stock) AS stock
                FROM dbo.saStockAlmacen sa
                WHERE sa.co_art = a.co_art 
                    AND RTRIM(sa.co_alma) = %s
                GROUP BY sa.co_alma
            ) stock_data
            -- Precio: Obtener el precio más reciente
            OUTER APPLY (
                SELECT TOP 1 
                    ap.monto AS price,
                    ap.co_mone AS currency
                FROM dbo.saArtPrecio ap
                WHERE ap.co_art = a.co_art 
                    AND RTRIM(ap.co_precio) = %s
                ORDER BY ap.desde DESC  -- Precio más reciente (fecha más actual)
            ) ap
            -- Imagen: Obtener la imagen principal
            OUTER APPLY (
                SELECT TOP 1 img.rowguid AS image_guid
                FROM dbo.saArtImagen img
                WHERE img.co_art = a.co_art
                ORDER BY CASE WHEN img.tip = 'PRINC' THEN 0 ELSE 1 END, img.fe_us_in DESC
            ) img
            WHERE {where_clause}
        """

        data_query = f"""
            SELECT DISTINCT
                a.co_art,
                a.art_des,
                a.co_cat AS category_code,
                cat.cat_des AS category_name,
                ap.price,
                ap.currency,
                stock_data.stock AS stock,
                stock_data.co_alma AS warehouse_code,
                img.image_guid
            {base_query}
            ORDER BY {order_by}
            OFFSET %s ROWS FETCH NEXT %s ROWS ONLY
        """

        count_query = f"""
            SELECT COUNT(DISTINCT a.co_art) AS total
            {base_query}
        """

        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(count_query, tuple(params))
            total_row = cursor.fetchone()
            total = total_row.get("total", 0) if total_row else 0

            cursor.execute(data_query, tuple(params + [offset, limit]))
            items = cursor.fetchall()
            cursor.close()
            conn.close()

            return {
                "items": items or [],
                "total": total,
                "page": page,
                "limit": limit,
            }
        except Exception:
            cursor.close()
            conn.close()
            raise

    def get_article_detail(self, article_code: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene el detalle completo de un artículo, incluyendo precios,
        stock e imágenes.
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            header_query = """
                SELECT 
                    a.co_art,
                    a.art_des,
                    a.ref,
                    a.co_lin,
                    a.co_subl,
                    a.co_cat,
                    cat.cat_des AS category_name,
                    a.tipo,
                    a.fecha_reg,
                    a.modelo
                FROM dbo.saArticulo a
                LEFT JOIN dbo.saCatArticulo cat ON RTRIM(a.co_cat) = RTRIM(cat.co_cat)
                WHERE a.co_art = %s AND a.anulado = 0
            """
            cursor.execute(header_query, (article_code,))
            header = cursor.fetchone()
            if not header:
                cursor.close()
                conn.close()
                return None

            price_query = """
                SELECT 
                    RTRIM(ap.co_precio) AS price_code,
                    tp.des_precio AS price_name,
                    ap.monto AS amount,
                    ap.co_mone AS currency,
                    ap.desde AS desde
                FROM dbo.saArtPrecio ap
                LEFT JOIN dbo.saTipoPrecio tp ON ap.co_precio = tp.co_precio
                WHERE ap.co_art = %s
                ORDER BY ap.desde DESC
            """
            cursor.execute(price_query, (article_code,))
            prices = cursor.fetchall() or []

            stock_query = """
                SELECT 
                    RTRIM(sa.co_alma) AS warehouse_code,
                    al.des_alma AS warehouse_name,
                    sa.stock AS quantity
                FROM dbo.saStockAlmacen sa
                LEFT JOIN dbo.saAlmacen al ON sa.co_alma = al.co_alma
                WHERE sa.co_art = %s
            """
            cursor.execute(stock_query, (article_code,))
            stock = cursor.fetchall() or []

            images = self.get_article_images(article_code, connection=(conn, cursor))

            cursor.close()
            conn.close()

            return {
                "header": header,
                "prices": prices,
                "stock": stock,
                "images": images,
            }
        except Exception:
            cursor.close()
            conn.close()
            raise

    def get_article_images(
        self,
        article_code: str,
        connection: Optional[Tuple[pymssql.Connection, pymssql.Cursor]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene la lista de imágenes asociadas a un artículo desde saArtImagen.
        Puede reutilizar una conexión existente para optimizar consultas.
        """
        own_connection = False
        if connection:
            conn, cursor = connection
        else:
            conn = self.get_connection()
            cursor = conn.cursor()
            own_connection = True

        try:
            query = """
                SELECT 
                    rowguid,
                    imagen_des,
                    tip,
                    co_us_in,
                    fe_us_in
                FROM dbo.saArtImagen
                WHERE co_art = %s
                ORDER BY CASE WHEN tip = 'PRINC' THEN 0 ELSE 1 END, fe_us_in DESC
            """
            cursor.execute(query, (article_code,))
            rows = cursor.fetchall() or []

            if own_connection:
                cursor.close()
                conn.close()

            return rows
        except Exception:
            if own_connection:
                cursor.close()
                conn.close()
            raise

    def _check_tip_exists(self, tip: str, article_code: str, cursor) -> bool:
        """
        Verifica si un código tip ya existe para un artículo.
        """
        check_query = """
            SELECT COUNT(*) as count
            FROM dbo.saArtImagen
            WHERE co_art = %s AND tip = %s
        """
        cursor.execute(check_query, (article_code, tip))
        result = cursor.fetchone()
        return result.get("count", 0) > 0 if result else False

    def _generate_unique_tip(self, article_code: str, cursor) -> str:
        """
        Genera un código tip único para un artículo.
        El formato es 'IMG' seguido de un número de 3 dígitos (ej: IMG001, IMG002, etc.)
        Como tip es char(6), tenemos espacio para 'IMG' + 3 dígitos.
        """
        counter = 1
        max_attempts = 999  # IMG001 a IMG999
        
        while counter <= max_attempts:
            tip = f"IMG{counter:03d}"  # Formato: IMG001, IMG002, etc.
            if not self._check_tip_exists(tip, article_code, cursor):
                return tip
            counter += 1
        
        # Si llegamos aquí, no hay códigos disponibles (muy improbable)
        raise ValueError(f"No se pudo generar un código tip único para el artículo {article_code}")

    def upload_article_image(
        self,
        article_code: str,
        image_bytes: bytes,
        description: Optional[str] = None,
        tip: Optional[str] = None,
        created_by: str = "API_USER",
    ) -> str:
        """
        Inserta una imagen en saArtImagen y devuelve el rowguid generado.
        
        Campos manejados:
        - co_art (char(30)): Código del artículo. Validado para no exceder 30 caracteres.
        - imagen_des (varchar(60)): Descripción/nombre del archivo. Truncado inteligentemente si excede 60 caracteres.
        - picture (varbinary(MAX)): Datos binarios de la imagen.
        - tip (char(6)): Código único de la imagen. Si no se proporciona, se genera automáticamente (IMG001, IMG002, etc.).
        - co_us_in (char(6)): Código de usuario que insertó. Si se recibe un email, se usa "API" por defecto.
        - fe_us_in (datetime): Fecha de inserción (GETDATE()).
        - co_sucu_in (char(6)): Código de sucursal de inserción. Usa "CCS" (existe en dbo.saSucursal).
        - co_us_mo (char(6)): Código de usuario que modificó. Igual a co_us_in para registros nuevos.
        - fe_us_mo (datetime): Fecha de modificación (GETDATE()).
        - co_sucu_mo (char(6)): Código de sucursal de modificación. Igual a co_sucu_in para registros nuevos.
        - rowguid (uniqueidentifier): Identificador único global generado automáticamente.
        
        Validaciones:
        - Valida las longitudes de los campos antes de insertar para evitar errores de truncamiento.
        - Verifica que el código tip no exista ya para el artículo si se proporciona.
        - Genera códigos tip únicos automáticamente si no se proporciona.
        """
        # Validaciones de longitud ANTES de conectar a la BD
        # co_art: char(30) - máximo 30 caracteres
        article_code_clean = (article_code or "").strip()
        if not article_code_clean:
            raise ValueError("El código del artículo (co_art) no puede estar vacío")
        if len(article_code_clean) > 30:
            raise ValueError(
                f"El código del artículo '{article_code_clean}' tiene {len(article_code_clean)} caracteres, "
                f"pero el máximo permitido es 30. Código recibido: '{article_code_clean}'"
            )
        
        # imagen_des: varchar(60) - máximo 60 caracteres
        description_clean = None
        if description:
            description_clean = description.strip()
            if len(description_clean) > 60:
                # Truncar el nombre de archivo de manera inteligente
                # Intentar preservar la extensión si es posible
                if '.' in description_clean:
                    name_part, ext = description_clean.rsplit('.', 1)
                    max_name_len = 60 - len(ext) - 1  # -1 para el punto
                    if max_name_len > 0:
                        description_clean = name_part[:max_name_len] + '.' + ext
                    else:
                        description_clean = description_clean[:60]
                else:
                    description_clean = description_clean[:60]
                self.logger.warning(
                    f"El nombre de archivo fue truncado de '{description}' a '{description_clean}' "
                    f"para cumplir con el límite de 60 caracteres"
                )
        
        # co_us_in: típicamente char(6) en Profit Plus - usar código corto, no email
        # Si created_by es un email, usar un código por defecto
        created_by_clean = (created_by or "API").strip()
        if '@' in created_by_clean:
            # Es un email, usar código por defecto
            created_by_clean = "API"
            self.logger.info(
                f"Se recibió un email '{created_by}' en created_by, se usará el código 'API' para co_us_in"
            )
        # Truncar a 6 caracteres si es necesario (típico en Profit Plus)
        if len(created_by_clean) > 6:
            created_by_clean = created_by_clean[:6]
            self.logger.warning(
                f"El código de usuario fue truncado de '{created_by}' a '{created_by_clean}' "
                f"para cumplir con el límite de 6 caracteres"
            )
        
        # co_sucu_in y co_sucu_mo: char(6) - código de sucursal
        # Usar "CCS" como código de sucursal (existe en dbo.saSucursal)
        sucursal_code = "CCS"
        
        new_guid = str(uuid4())
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # Determinar el código tip a usar
            if tip is None:
                # Si NO se proporciona tip, generar automáticamente (IMG001, IMG002, etc.)
                tip = self._generate_unique_tip(article_code_clean, cursor)
                self.logger.info(
                    f"Se generó automáticamente el código tip '{tip}' para el artículo {article_code_clean}"
                )
            else:
                # Si se proporciona tip (ej: "PRINC"), usar ese valor directamente
                tip = tip.strip().upper()[:6]  # Asegurar formato char(6) y mayúsculas
                if tip == "PRINC":
                    self.logger.info(
                        f"Se usará el código tip 'PRINC' para la imagen principal del artículo {article_code_clean}"
                    )
                # Verificar que el tip proporcionado no exista ya
                if self._check_tip_exists(tip, article_code_clean, cursor):
                    raise ValueError(
                        f"El código tip '{tip}' ya existe para el artículo {article_code_clean}. "
                        "Por favor, use un código diferente."
                    )
            
            # INSERT completo con todos los campos de auditoría requeridos
            insert_query = """
                INSERT INTO dbo.saArtImagen (
                    co_art,
                    imagen_des,
                    picture,
                    tip,
                    co_us_in,
                    fe_us_in,
                    co_sucu_in,
                    co_us_mo,
                    fe_us_mo,
                    co_sucu_mo,
                    rowguid
                )
                VALUES (%s, %s, %s, %s, %s, GETDATE(), %s, %s, GETDATE(), %s, %s)
            """
            cursor.execute(
                insert_query,
                (
                    article_code_clean,
                    description_clean,
                    image_bytes,
                    tip,
                    created_by_clean,  # co_us_in
                    sucursal_code,      # co_sucu_in
                    created_by_clean,  # co_us_mo = co_us_in para registros nuevos
                    sucursal_code,      # co_sucu_mo = co_sucu_in para registros nuevos
                    new_guid,
                ),
            )
            conn.commit()
            cursor.close()
            conn.close()
            return new_guid
        except ValueError:
            # Re-lanzar ValueError sin modificar (ya tienen mensajes claros)
            if conn:
                conn.rollback()
            if cursor:
                cursor.close()
            if conn:
                conn.close()
            raise
        except Exception as e:
            # Capturar otros errores y proporcionar contexto
            if conn:
                conn.rollback()
            if cursor:
                cursor.close()
            if conn:
                conn.close()
            # Si es un error de truncamiento, proporcionar más contexto
            error_msg = str(e)
            if "truncated" in error_msg.lower() or "8152" in error_msg:
                raise ValueError(
                    f"Error de truncamiento de datos. "
                    f"co_art: '{article_code_clean}' ({len(article_code_clean)} chars), "
                    f"imagen_des: '{description_clean}' ({len(description_clean) if description_clean else 0} chars), "
                    f"co_us_in: '{created_by_clean}' ({len(created_by_clean)} chars), "
                    f"tip: '{tip}' ({len(tip)} chars). "
                    f"Error original: {error_msg}"
                )
            raise

    def get_image_by_guid(self, image_guid: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene los datos binarios de una imagen almacenada en saArtImagen.
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # Normalizar el GUID: quitar espacios, convertir a mayúsculas, remover llaves
            image_guid_clean = (image_guid or "").strip().upper().replace('{', '').replace('}', '')
            if not image_guid_clean:
                self.logger.warning("Se recibió un GUID vacío")
                return None
            
            self.logger.info(f"Buscando imagen con GUID: {image_guid_clean}")
            
            # Usar CAST para convertir el string a UNIQUEIDENTIFIER
            # Esta es la forma más confiable en SQL Server con pymssql
            query = """
                SELECT 
                    picture,
                    imagen_des,
                    tip,
                    co_art
                FROM dbo.saArtImagen
                WHERE rowguid = CAST(%s AS UNIQUEIDENTIFIER)
            """
            cursor.execute(query, (image_guid_clean,))
            row = cursor.fetchone()
            
            if row:
                self.logger.info(f"Imagen encontrada para GUID: {image_guid_clean}, artículo: {row.get('co_art')}")
            else:
                self.logger.warning(f"No se encontró imagen con GUID: {image_guid_clean}")
            
            cursor.close()
            conn.close()
            return row
        except Exception as e:
            self.logger.error(f"Error obteniendo imagen por GUID {image_guid}: {str(e)}")
            if cursor:
                cursor.close()
            if conn:
                conn.close()
            raise

    def update_customer_password(self, customer_code: str, hashed_password: str) -> bool:
        """
        Actualiza la contraseña de un cliente en SourceSystem
        
        Args:
            customer_code: Código del cliente
            hashed_password: Contraseña hasheada
            
        Returns:
            bool: True si se actualizó correctamente
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            query = """
            UPDATE saCliente
            SET password = %s
            WHERE co_cli = %s
            """
            
            cursor.execute(query, (hashed_password, customer_code))
            conn.commit()
            
            rows_affected = cursor.rowcount
            cursor.close()
            conn.close()
            
            if rows_affected > 0:
                self.logger.info(f"Contraseña actualizada para cliente {customer_code}")
                return True
            else:
                self.logger.warning(f"No se encontró cliente {customer_code} para actualizar")
                return False
                
        except Exception as e:
            self.logger.error(f"Error actualizando contraseña para cliente {customer_code}: {str(e)}")
            raise

    def get_article_discount(
        self,
        article_code: str,
        customer_code: Optional[str] = None,
        quantity: Decimal = Decimal('1.00')
    ) -> Optional[Dict[str, Any]]:
        """
        Obtiene el descuento aplicable para un artículo desde saDescArticulo.
        
        Args:
            article_code: Código del artículo (co_art)
            customer_code: Código del cliente (co_cli). Si es None, busca descuentos generales
            quantity: Cantidad del artículo para determinar el rango de descuento
            
        Returns:
            Dict con información del descuento aplicable:
            {
                'discount_percentage': Decimal,  # Porcentaje de descuento
                'range_applied': str,  # Rango aplicado (hasta1, hasta2, etc.)
                'co_cli': str or None  # Cliente específico o None si es general
            }
            None si no hay descuento aplicable
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Primero intentar buscar descuento específico para el cliente
            discount = None
            if customer_code:
                query = """
                    SELECT 
                        porc1, porc2, porc3, porc4, porc5,
                        hasta1, hasta2, hasta3, hasta4, hasta5,
                        co_cli
                    FROM dbo.saDescArticulo
                    WHERE RTRIM(co_art) = %s 
                        AND RTRIM(co_cli) = %s
                """
                cursor.execute(query, (article_code.strip(), customer_code.strip()))
                discount = cursor.fetchone()
            
            # Si no hay descuento específico, buscar descuento general (co_cli IS NULL)
            if not discount:
                query = """
                    SELECT 
                        porc1, porc2, porc3, porc4, porc5,
                        hasta1, hasta2, hasta3, hasta4, hasta5,
                        co_cli
                    FROM dbo.saDescArticulo
                    WHERE RTRIM(co_art) = %s 
                        AND co_cli IS NULL
                """
                cursor.execute(query, (article_code.strip(),))
                discount = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            if not discount:
                return None
            
            # Determinar qué rango de descuento aplicar según la cantidad
            discount_percentage = Decimal('0.00')
            range_applied = None
            
            # Evaluar rangos en orden: hasta1, hasta2, hasta3, hasta4, hasta5
            hasta1 = Decimal(str(discount.get('hasta1') or 0))
            hasta2 = Decimal(str(discount.get('hasta2') or 0))
            hasta3 = Decimal(str(discount.get('hasta3') or 0))
            hasta4 = Decimal(str(discount.get('hasta4') or 0))
            hasta5 = Decimal(str(discount.get('hasta5') or 0))
            
            porc1 = Decimal(str(discount.get('porc1') or 0))
            porc2 = Decimal(str(discount.get('porc2') or 0))
            porc3 = Decimal(str(discount.get('porc3') or 0))
            porc4 = Decimal(str(discount.get('porc4') or 0))
            porc5 = Decimal(str(discount.get('porc5') or 0))
            
            # Determinar el rango aplicable
            if hasta5 > 0 and quantity <= hasta5:
                discount_percentage = porc5
                range_applied = 'hasta5'
            elif hasta4 > 0 and quantity <= hasta4:
                discount_percentage = porc4
                range_applied = 'hasta4'
            elif hasta3 > 0 and quantity <= hasta3:
                discount_percentage = porc3
                range_applied = 'hasta3'
            elif hasta2 > 0 and quantity <= hasta2:
                discount_percentage = porc2
                range_applied = 'hasta2'
            elif hasta1 > 0 and quantity <= hasta1:
                discount_percentage = porc1
                range_applied = 'hasta1'
            elif porc1 > 0:  # Si hay un porcentaje base sin rango específico
                discount_percentage = porc1
                range_applied = 'base'
            else:
                return None  # No hay descuento aplicable
            
            if discount_percentage <= 0:
                return None
            
            return {
                'discount_percentage': discount_percentage,
                'range_applied': range_applied,
                'co_cli': discount.get('co_cli'),
                'hasta': hasta1 if range_applied == 'hasta1' else (
                    hasta2 if range_applied == 'hasta2' else (
                        hasta3 if range_applied == 'hasta3' else (
                            hasta4 if range_applied == 'hasta4' else (
                                hasta5 if range_applied == 'hasta5' else None
                            )
                        )
                    )
                )
            }
            
        except Exception as e:
            self.logger.error(f"Error obteniendo descuento para artículo {article_code}: {str(e)}")
            raise

    def create_article_discount(self, discount_data: Dict[str, Any]) -> bool:
        """
        Crea o actualiza un registro de descuento en saDescArticulo usando co_desc como identificador.
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            co_desc = (discount_data.get("co_desc") or "").strip().upper()
            if not co_desc:
                raise ValueError("co_desc es requerido para crear un descuento")

            co_art = (discount_data.get("co_art") or "").strip().upper()
            if not co_art:
                raise ValueError("co_art es requerido para crear un descuento")

            tip_cli = (discount_data.get("tip_cli") or "GENERA").strip().upper()
            if not tip_cli:
                tip_cli = "GENERA"

            def _normalize_user_code(value: Optional[str], default: str = "API") -> str:
                if not value:
                    return default
                return value.strip().upper()[:6].ljust(6)

            co_us_in = _normalize_user_code(discount_data.get("co_us_in"))
            co_us_mo = _normalize_user_code(discount_data.get("co_us_mo", co_us_in))
            co_sucu_in = _normalize_user_code(discount_data.get("co_sucu_in", "CCS"))
            co_sucu_mo = _normalize_user_code(discount_data.get("co_sucu_mo", co_sucu_in))

            def _get_value(key: str):
                return discount_data.get(key)

            check_query = """
                SELECT COUNT(*) AS count
                FROM dbo.saDescArticulo
                WHERE co_desc = %s
            """
            cursor.execute(check_query, (co_desc,))
            result = cursor.fetchone()
            exists = result["count"] > 0 if result else False

            common_values = [
                _get_value("des_des"),
                co_art,
                tip_cli,
                _get_value("fecha_ini"),
                _get_value("fecha_fin"),
                _get_value("hasta1"),
                _get_value("porc1"),
                _get_value("hasta2"),
                _get_value("porc2"),
                _get_value("hasta3"),
                _get_value("porc3"),
                _get_value("hasta4"),
                _get_value("porc4"),
                _get_value("hasta5"),
                _get_value("porc5"),
                _get_value("porc6"),
                _get_value("campo1"),
                _get_value("campo2"),
                _get_value("campo3"),
                _get_value("campo4"),
                _get_value("campo5"),
                _get_value("campo6"),
                _get_value("campo7"),
                _get_value("campo8"),
            ]

            if exists:
                update_sql = """
                    UPDATE dbo.saDescArticulo
                    SET des_des=%s,
                        co_art=%s,
                        tip_cli=%s,
                        fecha_ini=%s,
                        fecha_fin=%s,
                        hasta1=%s, porc1=%s,
                        hasta2=%s, porc2=%s,
                        hasta3=%s, porc3=%s,
                        hasta4=%s, porc4=%s,
                        hasta5=%s, porc5=%s,
                        porc6=%s,
                        campo1=%s, campo2=%s, campo3=%s, campo4=%s,
                        campo5=%s, campo6=%s, campo7=%s, campo8=%s,
                        co_us_mo=%s,
                        co_sucu_mo=%s,
                        fe_us_mo=GETDATE()
                    WHERE co_desc=%s
                """
                params = common_values + [co_us_mo, co_sucu_mo, co_desc]
                cursor.execute(update_sql, tuple(params))
            else:
                insert_sql = """
                    INSERT INTO dbo.saDescArticulo (
                        co_desc, des_des, co_art, tip_cli, fecha_ini, fecha_fin,
                        hasta1, porc1,
                        hasta2, porc2,
                        hasta3, porc3,
                        hasta4, porc4,
                        hasta5, porc5,
                        porc6,
                        campo1, campo2, campo3, campo4,
                        campo5, campo6, campo7, campo8,
                        co_us_in, co_sucu_in, fe_us_in,
                        co_us_mo, co_sucu_mo, fe_us_mo,
                        revisado, trasnfe, rowguid
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, GETDATE(),
                        %s, %s, GETDATE(),
                        NULL, NULL, NEWID()
                    )
                """
                params = (
                    [co_desc] + common_values +
                    [co_us_in, co_sucu_in, co_us_mo, co_sucu_mo]
                )
                cursor.execute(insert_sql, tuple(params))

            conn.commit()
            cursor.close()
            conn.close()
            return True

        except Exception as e:
            if conn:
                conn.rollback()
                conn.close()
            self.logger.error(f"Error creating article discount: {str(e)}")
            raise

    def validate_tip_cli(self, tip_cli: str) -> bool:
        """
        Valida que el tip_cli exista en la tabla saTipoCliente.
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            query = """
                SELECT COUNT(*) AS count
                FROM dbo.saTipoCliente
                WHERE tip_cli = %s
            """
            cursor.execute(query, (tip_cli.strip().upper(),))
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            return result["count"] > 0 if result else False
        except Exception:
            cursor.close()
            conn.close()
            raise

    def get_valid_tip_cli_codes(self) -> list:
        """
        Obtiene todos los códigos de tipo de cliente válidos.
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            query = """
                SELECT tip_cli, des_tipo
                FROM dbo.saTipoCliente
                ORDER BY tip_cli
            """
            cursor.execute(query)
            results = cursor.fetchall()
            cursor.close()
            conn.close()
            return results or []
        except Exception:
            cursor.close()
            conn.close()
            raise

    def get_active_discounts_for_articles(
        self,
        article_codes: List[str],
        tip_cli: Optional[str] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Obtiene descuentos activos para múltiples artículos de forma optimizada.
        
        Args:
            article_codes: Lista de códigos de artículos
            tip_cli: Tipo de cliente para filtrar descuentos específicos
            
        Returns:
            Dict[str, Dict]: Mapa de article_code -> discount_info
        """
        if not article_codes:
            return {}
        
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Normalizar códigos
            normalized_codes = [code.strip().upper() for code in article_codes if code]
            if not normalized_codes:
                return {}
            
            # Construir placeholders para IN clause
            placeholders = ','.join(['%s'] * len(normalized_codes))
            
            # Query para obtener descuentos activos
            where_conditions = [
                f"RTRIM(d.co_art) IN ({placeholders})",
                "(d.fecha_ini IS NULL OR d.fecha_ini <= GETDATE())",
                "(d.fecha_fin IS NULL OR d.fecha_fin >= GETDATE())"
            ]
            params = list(normalized_codes)
            
            if tip_cli:
                where_conditions.append("RTRIM(d.tip_cli) = %s")
                params.append(tip_cli.strip().upper())
            
            where_clause = " AND ".join(where_conditions)
            
            query = f"""
                SELECT 
                    d.co_desc,
                    d.co_art,
                    d.tip_cli,
                    tc.des_tipo,
                    d.des_des,
                    d.fecha_ini,
                    d.fecha_fin,
                    d.hasta1, d.porc1,
                    d.hasta2, d.porc2,
                    d.hasta3, d.porc3,
                    d.hasta4, d.porc4,
                    d.hasta5, d.porc5,
                    d.porc6
                FROM dbo.saDescArticulo d
                LEFT JOIN dbo.saTipoCliente tc ON RTRIM(d.tip_cli) = RTRIM(tc.tip_cli)
                WHERE {where_clause}
                ORDER BY d.co_art, d.porc1 DESC
            """
            
            cursor.execute(query, tuple(params))
            results = cursor.fetchall() or []
            cursor.close()
            conn.close()
            
            # Organizar por artículo (tomar el primer descuento por artículo)
            discounts_map = {}
            for row in results:
                co_art = (row.get("co_art") or "").strip().upper()
                if co_art and co_art not in discounts_map:
                    discounts_map[co_art] = row
            
            return discounts_map
            
        except Exception:
            cursor.close()
            conn.close()
            raise

    def get_article_discounts(
        self,
        co_art: Optional[str] = None,
        tip_cli: Optional[str] = None,
        only_active: bool = False,
        page: int = 1,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Obtiene lista de descuentos de artículos desde saDescArticulo.
        
        Args:
            co_art: Filtrar por código de artículo (opcional)
            tip_cli: Filtrar por tipo de cliente (opcional)
            only_active: Si True, solo retorna descuentos vigentes
            page: Número de página (default: 1)
            limit: Registros por página (default: 50)
            
        Returns:
            Dict con items, total, page, limit, has_active, has_expired
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Construir WHERE clause dinámicamente
            where_conditions = []
            params = []
            
            if co_art:
                where_conditions.append("RTRIM(d.co_art) = %s")
                params.append(co_art.strip().upper())
            
            if tip_cli:
                where_conditions.append("RTRIM(d.tip_cli) = %s")
                params.append(tip_cli.strip().upper())
            
            if only_active:
                where_conditions.append("(d.fecha_ini IS NULL OR d.fecha_ini <= GETDATE())")
                where_conditions.append("(d.fecha_fin IS NULL OR d.fecha_fin >= GETDATE())")
            
            where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
            
            # Query para contar total
            count_query = f"""
                SELECT COUNT(*) AS total
                FROM dbo.saDescArticulo d
                {where_clause}
            """
            cursor.execute(count_query, tuple(params))
            total_result = cursor.fetchone()
            total = total_result["total"] if total_result else 0
            
            # Query para obtener datos paginados
            offset = (page - 1) * limit
            data_query = f"""
                SELECT 
                    d.co_desc,
                    d.co_art,
                    a.art_des,
                    d.tip_cli,
                    tc.des_tipo,
                    d.des_des,
                    d.fecha_ini,
                    d.fecha_fin,
                    d.hasta1, d.porc1,
                    d.hasta2, d.porc2,
                    d.hasta3, d.porc3,
                    d.hasta4, d.porc4,
                    d.hasta5, d.porc5,
                    d.porc6,
                    d.fe_us_in,
                    d.fe_us_mo,
                    CASE 
                        WHEN (d.fecha_ini IS NULL OR d.fecha_ini <= GETDATE())
                         AND (d.fecha_fin IS NULL OR d.fecha_fin >= GETDATE())
                        THEN 1
                        ELSE 0
                    END AS is_active
                FROM dbo.saDescArticulo d
                LEFT JOIN dbo.saArticulo a ON RTRIM(d.co_art) = RTRIM(a.co_art)
                LEFT JOIN dbo.saTipoCliente tc ON RTRIM(d.tip_cli) = RTRIM(tc.tip_cli)
                {where_clause}
                ORDER BY d.fecha_ini DESC, d.co_desc
                OFFSET %s ROWS FETCH NEXT %s ROWS ONLY
            """
            cursor.execute(data_query, tuple(params + [offset, limit]))
            items = cursor.fetchall() or []
            
            # Contar activos y expirados
            stats_query = f"""
                SELECT 
                    SUM(CASE 
                        WHEN (fecha_ini IS NULL OR fecha_ini <= GETDATE())
                         AND (fecha_fin IS NULL OR fecha_fin >= GETDATE())
                        THEN 1 ELSE 0 
                    END) AS active_count,
                    SUM(CASE 
                        WHEN fecha_fin IS NOT NULL AND fecha_fin < GETDATE()
                        THEN 1 ELSE 0 
                    END) AS expired_count
                FROM dbo.saDescArticulo d
                {where_clause}
            """
            cursor.execute(stats_query, tuple(params))
            stats = cursor.fetchone()
            has_active = stats["active_count"] if stats else 0
            has_expired = stats["expired_count"] if stats else 0
            
            cursor.close()
            conn.close()
            
            return {
                "items": items,
                "total": total,
                "page": page,
                "limit": limit,
                "has_active": has_active,
                "has_expired": has_expired
            }
            
        except Exception:
            cursor.close()
            conn.close()
            raise

# Singleton instance
source_system_service = SourceSystemService()
