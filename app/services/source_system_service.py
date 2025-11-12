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
            print(f"SourceSystem configurado - Server: {self.server}, DB: {self.database}, User: {self.user[:3]}***")
            self.logger.info(f"SourceSystem configurado - Server: {self.server}, DB: {self.database}, User: {self.user[:3]}***")
        else:
            print(f"SourceSystem configurado - Server: {self.server}, DB: {self.database}, User: (sin autenticación)")
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
            print(f"Server clean: {server_clean}")
            database_clean = self.database.strip() if isinstance(self.database, str) else self.database
            print(f"Database clean: {database_clean}")
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
            print(f"Conectando a SourceSystem: {server_clean}:{self.port}/{database_clean}")
            self.logger.info(f"Conectando a SourceSystem: {server_clean}:{self.port}/{database_clean}")
            
            print(f"Parámetros de conexión: {connect_kwargs}")
            conn = pymssql.connect(**connect_kwargs)
            print(f"Conexión a SourceSystem establecida exitosamente: {conn}")
            self.logger.info("Conexión a SourceSystem establecida exitosamente")
            print(f"Conexión a SourceSystem establecida exitosamente: {conn}")
            self.logger.info("Conexión a SourceSystem establecida exitosamente")
            return conn
        except Exception as e:
            error_msg = str(e)
            print(f"Error conectando a SourceSystem: {error_msg}")
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

# Singleton instance
source_system_service = SourceSystemService()
