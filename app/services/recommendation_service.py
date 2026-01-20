"""
Servicio de recomendaciones de artículos sin ML.
Implementa estrategias basadas en reglas y análisis de datos desde source_system (DEMOA).
Optimizado con pool de conexiones y caché.
"""
from typing import List, Optional, Dict, Any
from decimal import Decimal
from app.services.source_system_service import source_system_service
from app.services.cache_service import cache_service
from app.config.logging_config import get_logger

logger = get_logger(__name__)

# Configuración de caché para recomendaciones (TTLs aumentados para reducir carga en BD)
CACHE_PREFIX_RECOMMENDATIONS = "recommendations"
CACHE_TTL_RELATED = 3600  # 60 minutos para artículos relacionados
CACHE_TTL_FREQUENTLY_BOUGHT = 7200  # 2 horas para frecuentemente comprados juntos
CACHE_TTL_RECOMMENDED = 1800  # 30 minutos para recomendaciones personalizadas

# Timeout para queries (en segundos)
QUERY_TIMEOUT = 15  # Limitar queries a 15 segundos


class RecommendationService:
    """
    Servicio de recomendaciones optimizado.
    
    Características:
    - Usa context managers para conexiones seguras al pool
    - Caché en memoria para respuestas rápidas
    - No cierra conexiones manualmente (el pool lo maneja)
    """
    
    def __init__(self):
        self._source_service = source_system_service
    
    def get_related_articles(
        self, 
        co_art: str, 
        limit: int = 3,
        price_code: str = "01",
        warehouse_code: str = "001"
    ) -> List[Dict[str, Any]]:
        """
        Obtiene artículos relacionados basado en el artículo actual.
        Optimizado con context manager y caché.
        
        Estrategia:
        1. Misma categoría (co_cat) - prioridad alta
        2. Misma línea (co_lin) - prioridad media
        3. Misma sublínea (co_subl) - prioridad media
        4. Rango de precio similar (±30%) - prioridad baja
        """
        # Intentar obtener del caché
        cache_key = cache_service._generate_key(
            f"{CACHE_PREFIX_RECOMMENDATIONS}:related",
            co_art=co_art, limit=limit, price=price_code, warehouse=warehouse_code
        )
        cached = cache_service.get(cache_key)
        if cached is not None:
            logger.debug(f"Cache HIT para artículos relacionados: {co_art}")
            return cached
        
        try:
            # Usar context manager para manejo seguro de conexiones
            with self._source_service.connection() as conn:
                cursor = conn.cursor()
                
                # Establecer timeout para la query
                try:
                    cursor.execute(f"SET LOCK_TIMEOUT {QUERY_TIMEOUT * 1000}")  # En milisegundos
                except Exception:
                    pass  # Si falla, continuar sin timeout
                
                # Primero obtener información del artículo base (query simplificada)
                base_query = """
                    SELECT TOP 1
                        a.co_art,
                        a.art_des,
                        a.co_cat,
                        a.co_lin,
                        a.co_subl,
                        ISNULL(ap.monto, 0) AS price
                    FROM dbo.saArticulo a WITH (NOLOCK)
                    LEFT JOIN dbo.saArtPrecio ap WITH (NOLOCK) ON ap.co_art = a.co_art 
                        AND RTRIM(ap.co_precio) = %s
                    WHERE a.co_art = %s AND a.anulado = 0
                    ORDER BY ap.desde DESC
                """
                cursor.execute(base_query, (price_code, co_art))
                base_article = cursor.fetchone()
                
                if not base_article:
                    cursor.close()
                    logger.warning(f"Artículo {co_art} no encontrado para recomendaciones")
                    return []
                
                base_category = (base_article.get('co_cat') or '').strip() if base_article.get('co_cat') else None
                base_line = (base_article.get('co_lin') or '').strip() if base_article.get('co_lin') else None
                base_subline = (base_article.get('co_subl') or '').strip() if base_article.get('co_subl') else None
                base_price = self._to_decimal(base_article.get('price'))
                
                # Construir condiciones de similitud
                conditions = []
                condition_params = []
                
                if base_category:
                    conditions.append("RTRIM(a.co_cat) = %s")
                    condition_params.append(base_category)
                
                if base_line:
                    conditions.append("RTRIM(a.co_lin) = %s")
                    condition_params.append(base_line)
                
                if base_subline:
                    conditions.append("RTRIM(a.co_subl) = %s")
                    condition_params.append(base_subline)
                
                # Rango de precio similar (±30%)
                price_condition = None
                price_params = []
                if base_price:
                    price_range = base_price * Decimal('0.3')
                    min_price = base_price - price_range
                    max_price = base_price + price_range
                    price_condition = "ap.price >= %s AND ap.price <= %s"
                    price_params = [min_price, max_price]
                
                # Construir query con condiciones
                where_conditions = ["a.anulado = 0", "a.co_art != %s"]
                where_params = [co_art]
                
                if conditions:
                    where_conditions.append(f"({' OR '.join(conditions)})")
                    where_params.extend(condition_params)
                elif price_condition and base_price:
                    where_conditions.append(price_condition)
                    where_params.extend(price_params)
                
                where_clause = " AND ".join(where_conditions)
                
                # Query optimizada: usar subconsultas correlacionadas en SELECT en lugar de OUTER APPLY
                # para mejor rendimiento en SQL Server
                query = f"""
                    SELECT TOP {limit}
                        a.co_art,
                        a.art_des,
                        a.co_cat AS category_code,
                        cat.cat_des AS category_name,
                        (SELECT TOP 1 ap.monto 
                         FROM dbo.saArtPrecio ap WITH (NOLOCK)
                         WHERE ap.co_art = a.co_art AND RTRIM(ap.co_precio) = %s
                         ORDER BY ap.desde DESC) AS price,
                        (SELECT TOP 1 ap.co_mone 
                         FROM dbo.saArtPrecio ap WITH (NOLOCK)
                         WHERE ap.co_art = a.co_art AND RTRIM(ap.co_precio) = %s
                         ORDER BY ap.desde DESC) AS currency,
                        (SELECT SUM(sa.stock) 
                         FROM dbo.saStockAlmacen sa WITH (NOLOCK)
                         WHERE sa.co_art = a.co_art AND RTRIM(sa.co_alma) = %s AND sa.tipo = 'ACT') AS stock,
                        %s AS warehouse_code,
                        (SELECT TOP 1 img.rowguid 
                         FROM dbo.saArtImagen img WITH (NOLOCK)
                         WHERE img.co_art = a.co_art
                         ORDER BY CASE WHEN img.tip = 'PRINC' THEN 0 ELSE 1 END, img.fe_us_in DESC) AS image_guid,
                        CASE WHEN RTRIM(a.co_cat) = %s THEN 0 ELSE 1 END AS category_match,
                        CASE WHEN RTRIM(a.co_lin) = %s THEN 0 ELSE 1 END AS line_match
                    FROM dbo.saArticulo a WITH (NOLOCK)
                    LEFT JOIN dbo.saCatArticulo cat WITH (NOLOCK) ON RTRIM(a.co_cat) = RTRIM(cat.co_cat)
                    WHERE {where_clause}
                    ORDER BY 
                        category_match,
                        line_match,
                        price DESC
                    OPTION (MAXDOP 2, FAST {limit})
                """
                
                params = [
                    price_code,  # Para subconsulta de precio
                    price_code,  # Para subconsulta de moneda
                    warehouse_code,  # Para subconsulta de stock
                    warehouse_code,  # Para campo warehouse_code
                    base_category if base_category else '',
                    base_line if base_line else ''
                ]
                params.extend(where_params)
                
                cursor.execute(query, tuple(params))
                related = cursor.fetchall()
                cursor.close()
                # No llamar conn.close() - el context manager lo maneja
                
                result = related[:limit]
                
                # Guardar en caché
                cache_service.set(cache_key, result, ttl=CACHE_TTL_RELATED)
                logger.debug(f"Cache SET para artículos relacionados: {co_art} ({len(result)} items)")
                
                return result
            
        except Exception as e:
            logger.error(f"Error obteniendo artículos relacionados para {co_art}: {e}")
            # Fallback: intentar con query simplificada solo por categoría
            try:
                with self._source_service.connection() as conn:
                    cursor = conn.cursor()
                    fallback_query = f"""
                        SELECT TOP {limit}
                            a.co_art, a.art_des,
                            a.co_cat AS category_code, NULL AS category_name,
                            NULL AS price, 'VES' AS currency,
                            NULL AS stock, NULL AS warehouse_code,
                            NULL AS image_guid
                        FROM dbo.saArticulo a WITH (NOLOCK)
                        WHERE a.anulado = 0 AND a.co_art != %s
                        ORDER BY NEWID()
                        OPTION (FAST {limit})
                    """
                    cursor.execute(fallback_query, (co_art,))
                    fallback_results = cursor.fetchall() or []
                    cursor.close()
                    logger.info(f"Usando fallback para artículos relacionados: {len(fallback_results)} items")
                    # Cachear por menos tiempo ya que es fallback
                    cache_service.set(cache_key, fallback_results, ttl=300)
                    return fallback_results
            except Exception as fallback_error:
                logger.error(f"Error en fallback de artículos relacionados: {fallback_error}")
                return []
    
    def get_frequently_bought_together(
        self,
        co_art: str,
        limit: int = 4
    ) -> List[Dict[str, Any]]:
        """
        Obtiene artículos frecuentemente comprados junto con el artículo dado.
        Basado en análisis de facturas (saFacturaVentaReng).
        Optimizado con context manager y caché.
        """
        # Intentar obtener del caché
        cache_key = cache_service._generate_key(
            f"{CACHE_PREFIX_RECOMMENDATIONS}:frequently_bought",
            co_art=co_art, limit=limit
        )
        cached = cache_service.get(cache_key)
        if cached is not None:
            logger.debug(f"Cache HIT para frecuentemente comprados: {co_art}")
            return cached
        
        try:
            # Usar context manager para manejo seguro de conexiones
            with self._source_service.connection() as conn:
                cursor = conn.cursor()
                
                # Establecer timeout para la query
                try:
                    cursor.execute(f"SET LOCK_TIMEOUT {QUERY_TIMEOUT * 1000}")
                except Exception:
                    pass
                
                # Query optimizada: combinar todo en una sola consulta para reducir round-trips
                # Usar CTE (Common Table Expression) para mejor rendimiento
                combined_query = f"""
                    WITH ArticleInvoices AS (
                        -- Facturas que contienen el artículo objetivo
                        SELECT DISTINCT fvr.doc_num
                        FROM dbo.saFacturaVentaReng fvr WITH (NOLOCK)
                        INNER JOIN dbo.saFacturaVenta fv WITH (NOLOCK) ON fvr.doc_num = fv.doc_num
                        WHERE fvr.co_art = %s AND fv.anulado = 0
                    ),
                    FrequentArticles AS (
                        -- Artículos más comprados en esas facturas
                        SELECT TOP {limit}
                            fvr.co_art,
                            COUNT(DISTINCT fvr.doc_num) AS frequency
                        FROM dbo.saFacturaVentaReng fvr WITH (NOLOCK)
                        INNER JOIN ArticleInvoices ai ON fvr.doc_num = ai.doc_num
                        WHERE fvr.co_art != %s
                        GROUP BY fvr.co_art
                        ORDER BY frequency DESC
                    )
                    SELECT 
                        a.co_art,
                        a.art_des,
                        a.co_cat AS category_code,
                        cat.cat_des AS category_name,
                        (SELECT TOP 1 ap.monto 
                         FROM dbo.saArtPrecio ap WITH (NOLOCK)
                         WHERE ap.co_art = a.co_art AND RTRIM(ap.co_precio) = '01'
                         ORDER BY ap.desde DESC) AS price,
                        (SELECT TOP 1 ap.co_mone 
                         FROM dbo.saArtPrecio ap WITH (NOLOCK)
                         WHERE ap.co_art = a.co_art AND RTRIM(ap.co_precio) = '01'
                         ORDER BY ap.desde DESC) AS currency,
                        (SELECT SUM(sa.stock) 
                         FROM dbo.saStockAlmacen sa WITH (NOLOCK)
                         WHERE sa.co_art = a.co_art AND RTRIM(sa.co_alma) = '001' AND sa.tipo = 'ACT') AS stock,
                        '001' AS warehouse_code,
                        (SELECT TOP 1 img.rowguid 
                         FROM dbo.saArtImagen img WITH (NOLOCK)
                         WHERE img.co_art = a.co_art
                         ORDER BY CASE WHEN img.tip = 'PRINC' THEN 0 ELSE 1 END, img.fe_us_in DESC) AS image_guid,
                        fa.frequency
                    FROM FrequentArticles fa
                    INNER JOIN dbo.saArticulo a WITH (NOLOCK) ON a.co_art = fa.co_art
                    LEFT JOIN dbo.saCatArticulo cat WITH (NOLOCK) ON RTRIM(a.co_cat) = RTRIM(cat.co_cat)
                    WHERE a.anulado = 0
                    ORDER BY fa.frequency DESC
                    OPTION (MAXDOP 2, FAST {limit})
                """
                cursor.execute(combined_query, (co_art, co_art))
                articles = cursor.fetchall()
                cursor.close()
                
                # Los artículos ya vienen ordenados por frecuencia
                result = articles[:limit] if articles else []
                
                # Guardar en caché
                cache_service.set(cache_key, result, ttl=CACHE_TTL_FREQUENTLY_BOUGHT)
                logger.debug(f"Cache SET para frecuentemente comprados: {co_art} ({len(result)} items)")
                
                return result
            
        except Exception as e:
            logger.error(f"Error obteniendo artículos frecuentemente comprados juntos para {co_art}: {e}")
            # Fallback: retornar lista vacía y cachearla para evitar consultas repetidas
            cache_service.set(cache_key, [], ttl=300)
            return []
    
    def get_recommended_articles(
        self,
        customer_code: Optional[str] = None,
        limit: int = 12,
        price_code: str = "01",
        warehouse_code: str = "001"
    ) -> List[Dict[str, Any]]:
        """
        Obtiene artículos recomendados basado en el historial del cliente.
        Optimizado con context manager y caché.
        
        Estrategia:
        1. Artículos de categorías que el cliente compra
        2. Artículos destacados/populares
        """
        # Intentar obtener del caché
        cache_key = cache_service._generate_key(
            f"{CACHE_PREFIX_RECOMMENDATIONS}:recommended",
            customer=customer_code or "anonymous", limit=limit, 
            price=price_code, warehouse=warehouse_code
        )
        cached = cache_service.get(cache_key)
        if cached is not None:
            logger.debug(f"Cache HIT para recomendados: customer={customer_code}")
            return cached
        
        try:
            # Usar context manager para manejo seguro de conexiones
            with self._source_service.connection() as conn:
                cursor = conn.cursor()
                
                # Establecer timeout para la query
                try:
                    cursor.execute(f"SET LOCK_TIMEOUT {QUERY_TIMEOUT * 1000}")
                except Exception:
                    pass
                
                recommended = []
                
                if customer_code:
                    # Estrategia 1: Artículos de categorías que el cliente compra
                    # Optimizar con TOP y NOLOCK
                    categories_query = """
                        SELECT DISTINCT TOP 100 fvr.co_art, a.co_cat
                        FROM dbo.saFacturaVentaReng fvr WITH (NOLOCK)
                        INNER JOIN dbo.saFacturaVenta fv WITH (NOLOCK) ON fvr.doc_num = fv.doc_num
                        INNER JOIN dbo.saArticulo a WITH (NOLOCK) ON fvr.co_art = a.co_art
                        WHERE fv.co_cli = %s
                            AND fv.anulado = 0
                            AND a.anulado = 0
                            AND a.co_cat IS NOT NULL
                        OPTION (MAXDOP 2)
                    """
                    cursor.execute(categories_query, (customer_code,))
                    purchased_items = cursor.fetchall()
                    
                    if purchased_items:
                        purchased_categories = set()
                        purchased_articles = set()
                        for row in purchased_items:
                            if row.get('co_cat'):
                                purchased_categories.add(row.get('co_cat').strip())
                            if row.get('co_art'):
                                purchased_articles.add(row.get('co_art').strip())
                        
                        if purchased_categories:
                            category_list = list(purchased_categories)[:10]  # Limitar categorías para mejor rendimiento
                            category_placeholders = ",".join(["%s"] * len(category_list))
                            
                            # Query optimizada con subconsultas en SELECT
                            category_query = f"""
                                SELECT TOP {limit}
                                    a.co_art,
                                    a.art_des,
                                    a.co_cat AS category_code,
                                    cat.cat_des AS category_name,
                                    (SELECT TOP 1 ap.monto 
                                     FROM dbo.saArtPrecio ap WITH (NOLOCK)
                                     WHERE ap.co_art = a.co_art AND RTRIM(ap.co_precio) = %s
                                     ORDER BY ap.desde DESC) AS price,
                                    (SELECT TOP 1 ap.co_mone 
                                     FROM dbo.saArtPrecio ap WITH (NOLOCK)
                                     WHERE ap.co_art = a.co_art AND RTRIM(ap.co_precio) = %s
                                     ORDER BY ap.desde DESC) AS currency,
                                    (SELECT SUM(sa.stock) 
                                     FROM dbo.saStockAlmacen sa WITH (NOLOCK)
                                     WHERE sa.co_art = a.co_art AND RTRIM(sa.co_alma) = %s AND sa.tipo = 'ACT') AS stock,
                                    %s AS warehouse_code,
                                    (SELECT TOP 1 img.rowguid 
                                     FROM dbo.saArtImagen img WITH (NOLOCK)
                                     WHERE img.co_art = a.co_art
                                     ORDER BY CASE WHEN img.tip = 'PRINC' THEN 0 ELSE 1 END, img.fe_us_in DESC) AS image_guid
                                FROM dbo.saArticulo a WITH (NOLOCK)
                                LEFT JOIN dbo.saCatArticulo cat WITH (NOLOCK) ON RTRIM(a.co_cat) = RTRIM(cat.co_cat)
                                WHERE a.anulado = 0
                                    AND RTRIM(a.co_cat) IN ({category_placeholders})
                            """
                            
                            # Excluir artículos ya comprados
                            if purchased_articles:
                                purchased_list = list(purchased_articles)[:50]  # Limitar para mejor rendimiento
                                article_placeholders = ",".join(["%s"] * len(purchased_list))
                                category_query += f" AND a.co_art NOT IN ({article_placeholders})"
                            
                            category_query += """
                                ORDER BY NEWID()
                                OPTION (MAXDOP 2)
                            """
                            
                            params = [price_code, price_code, warehouse_code, warehouse_code] + category_list
                            if purchased_articles:
                                params.extend(purchased_list)
                            else:
                                purchased_list = []
                            
                            cursor.execute(category_query, tuple(params))
                            category_articles = cursor.fetchall()
                            recommended.extend(category_articles)
                            logger.debug(f"Encontrados {len(category_articles)} artículos de categorías del cliente")
                
                # Si no hay suficientes, completar con artículos populares
                if len(recommended) < limit:
                    remaining = limit - len(recommended)
                    
                    # Simplificar: obtener artículos aleatorios con stock en lugar de calcular popularidad
                    # (mucho más rápido y evita el costoso JOIN con facturas)
                    popular_query = f"""
                        SELECT TOP {remaining}
                            a.co_art,
                            a.art_des,
                            a.co_cat AS category_code,
                            cat.cat_des AS category_name,
                            (SELECT TOP 1 ap.monto 
                             FROM dbo.saArtPrecio ap WITH (NOLOCK)
                             WHERE ap.co_art = a.co_art AND RTRIM(ap.co_precio) = %s
                             ORDER BY ap.desde DESC) AS price,
                            (SELECT TOP 1 ap.co_mone 
                             FROM dbo.saArtPrecio ap WITH (NOLOCK)
                             WHERE ap.co_art = a.co_art AND RTRIM(ap.co_precio) = %s
                             ORDER BY ap.desde DESC) AS currency,
                            (SELECT SUM(sa.stock) 
                             FROM dbo.saStockAlmacen sa WITH (NOLOCK)
                             WHERE sa.co_art = a.co_art AND RTRIM(sa.co_alma) = %s AND sa.tipo = 'ACT') AS stock,
                            %s AS warehouse_code,
                            (SELECT TOP 1 img.rowguid 
                             FROM dbo.saArtImagen img WITH (NOLOCK)
                             WHERE img.co_art = a.co_art
                             ORDER BY CASE WHEN img.tip = 'PRINC' THEN 0 ELSE 1 END, img.fe_us_in DESC) AS image_guid
                        FROM dbo.saArticulo a WITH (NOLOCK)
                        LEFT JOIN dbo.saCatArticulo cat WITH (NOLOCK) ON RTRIM(a.co_cat) = RTRIM(cat.co_cat)
                        WHERE a.anulado = 0
                    """
                    
                    params = [price_code, price_code, warehouse_code, warehouse_code]
                    
                    if recommended:
                        recommended_codes = [(row.get('co_art') or '').strip() for row in recommended if row.get('co_art')][:50]
                        if recommended_codes:
                            recommended_placeholders = ",".join(["%s"] * len(recommended_codes))
                            popular_query += f" AND a.co_art NOT IN ({recommended_placeholders})"
                            params.extend(recommended_codes)
                    
                    popular_query += """
                        ORDER BY NEWID()
                        OPTION (MAXDOP 2)
                    """
                    
                    cursor.execute(popular_query, tuple(params))
                    popular_articles = cursor.fetchall()
                    recommended.extend(popular_articles)
                    logger.debug(f"Agregados {len(popular_articles)} artículos populares")
                
                cursor.close()
                # No llamar conn.close() - el context manager lo maneja
                
                result = recommended[:limit]
                
                # Guardar en caché
                cache_service.set(cache_key, result, ttl=CACHE_TTL_RECOMMENDED)
                logger.debug(f"Cache SET para recomendados: {len(result)} items")
                
                return result
            
        except Exception as e:
            logger.error(f"Error obteniendo artículos recomendados: {e}")
            # Fallback: intentar con query simplificada
            try:
                with self._source_service.connection() as conn:
                    cursor = conn.cursor()
                    fallback_query = f"""
                        SELECT TOP {limit}
                            a.co_art, a.art_des,
                            a.co_cat AS category_code, NULL AS category_name,
                            NULL AS price, 'VES' AS currency,
                            NULL AS stock, NULL AS warehouse_code,
                            NULL AS image_guid
                        FROM dbo.saArticulo a WITH (NOLOCK)
                        WHERE a.anulado = 0
                        ORDER BY NEWID()
                        OPTION (FAST {limit})
                    """
                    cursor.execute(fallback_query)
                    fallback_results = cursor.fetchall() or []
                    cursor.close()
                    logger.info(f"Usando fallback para artículos recomendados: {len(fallback_results)} items")
                    cache_service.set(cache_key, fallback_results, ttl=300)
                    return fallback_results
            except Exception as fallback_error:
                logger.error(f"Error en fallback de artículos recomendados: {fallback_error}")
                return []
    
    @staticmethod
    def _to_decimal(value: Any) -> Optional[Decimal]:
        """Convierte un valor a Decimal de forma segura."""
        if value is None:
            return None
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except Exception:
            return None
    
    # =========================================================================
    # Métodos de Caché
    # =========================================================================
    
    @staticmethod
    def invalidate_cache():
        """Invalida todo el caché de recomendaciones."""
        count = cache_service.invalidate_pattern(f"{CACHE_PREFIX_RECOMMENDATIONS}:")
        logger.info(f"Caché de recomendaciones invalidado: {count} entradas eliminadas")
        return count
    
    @staticmethod
    def invalidate_article_cache(co_art: str):
        """Invalida el caché de recomendaciones para un artículo específico."""
        count = cache_service.invalidate_pattern(f"{CACHE_PREFIX_RECOMMENDATIONS}:related:co_art={co_art}")
        count += cache_service.invalidate_pattern(f"{CACHE_PREFIX_RECOMMENDATIONS}:frequently_bought:co_art={co_art}")
        logger.debug(f"Caché de recomendaciones invalidado para {co_art}: {count} entradas")
        return count
    
    @staticmethod
    def get_cache_stats() -> Dict:
        """Obtiene estadísticas del caché."""
        return cache_service.get_stats()
    
    def warmup_cache(self, popular_articles: List[str] = None, customer_codes: List[str] = None):
        """
        Pre-calienta el caché con artículos populares.
        
        Args:
            popular_articles: Lista de códigos de artículos populares para pre-cargar
            customer_codes: Lista de códigos de clientes para pre-cargar recomendaciones
        
        Returns:
            Dict con estadísticas del warm-up
        """
        stats = {
            'related_loaded': 0,
            'frequently_bought_loaded': 0,
            'recommended_loaded': 0,
            'errors': 0
        }
        
        try:
            # Pre-cargar artículos relacionados para productos populares
            if popular_articles:
                logger.info(f"Iniciando warm-up de cache para {len(popular_articles)} artículos populares")
                for co_art in popular_articles:
                    try:
                        self.get_related_articles(co_art, limit=3)
                        stats['related_loaded'] += 1
                        
                        self.get_frequently_bought_together(co_art, limit=4)
                        stats['frequently_bought_loaded'] += 1
                    except Exception as e:
                        logger.warning(f"Error en warm-up para artículo {co_art}: {e}")
                        stats['errors'] += 1
            
            # Pre-cargar recomendaciones para clientes frecuentes
            if customer_codes:
                logger.info(f"Iniciando warm-up de recomendaciones para {len(customer_codes)} clientes")
                for customer_code in customer_codes:
                    try:
                        self.get_recommended_articles(customer_code=customer_code, limit=12)
                        stats['recommended_loaded'] += 1
                    except Exception as e:
                        logger.warning(f"Error en warm-up para cliente {customer_code}: {e}")
                        stats['errors'] += 1
            
            # Pre-cargar recomendaciones generales (sin cliente)
            try:
                self.get_recommended_articles(customer_code=None, limit=12)
                stats['recommended_loaded'] += 1
            except Exception as e:
                logger.warning(f"Error en warm-up de recomendaciones generales: {e}")
                stats['errors'] += 1
            
            logger.info(f"Warm-up completado: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Error en warm-up de caché: {e}")
            return stats
