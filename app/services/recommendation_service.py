"""
Servicio de recomendaciones de artículos sin ML.
Implementa estrategias basadas en reglas y análisis de datos desde source_system (DEMOA).
Optimizado con pool de conexiones y caché.
"""
from decimal import Decimal
from typing import Any

from app.config.logging_config import get_logger
from app.services.cache_service import cache_service
from app.services.source_system_service import source_system_service

logger = get_logger(__name__)

# Configuración de caché para recomendaciones
CACHE_PREFIX_RECOMMENDATIONS = "recommendations"
CACHE_TTL_RELATED = 600  # 10 minutos para artículos relacionados
CACHE_TTL_FREQUENTLY_BOUGHT = 900  # 15 minutos para frecuentemente comprados
CACHE_TTL_RECOMMENDED = 300  # 5 minutos para recomendaciones personalizadas


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
    ) -> list[dict[str, Any]]:
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
                
                # Primero obtener información del artículo base
                base_query = """
                    SELECT 
                        a.co_art,
                        a.art_des,
                        a.co_cat,
                        a.co_lin,
                        a.co_subl,
                        ap.monto AS price
                    FROM dbo.saArticulo a
                    OUTER APPLY (
                        SELECT TOP 1 ap.monto
                        FROM dbo.saArtPrecio ap
                        WHERE ap.co_art = a.co_art 
                            AND RTRIM(ap.co_precio) = %s
                        ORDER BY ap.desde DESC
                    ) ap
                    WHERE a.co_art = %s AND a.anulado = 0
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
                
                query = f"""
                    SELECT DISTINCT
                        a.co_art,
                        a.art_des,
                        a.co_cat AS category_code,
                        cat.cat_des AS category_name,
                        ap.price,
                        ap.currency,
                        stock_data.stock AS stock,
                        stock_data.co_alma AS warehouse_code,
                        img.image_guid,
                        CASE WHEN RTRIM(a.co_cat) = %s THEN 0 ELSE 1 END AS category_match,
                        CASE WHEN RTRIM(a.co_lin) = %s THEN 0 ELSE 1 END AS line_match
                    FROM dbo.saArticulo a
                    LEFT JOIN dbo.saCatArticulo cat ON RTRIM(a.co_cat) = RTRIM(cat.co_cat)
                    OUTER APPLY (
                        SELECT 
                            RTRIM(sa.co_alma) AS co_alma,
                            SUM(sa.stock) AS stock
                        FROM dbo.saStockAlmacen sa
                        WHERE sa.co_art = a.co_art 
                            AND RTRIM(sa.co_alma) = %s
                            AND sa.tipo = 'ACT'
                        GROUP BY sa.co_alma
                    ) stock_data
                    OUTER APPLY (
                        SELECT TOP 1 
                            ap.monto AS price,
                            ap.co_mone AS currency
                        FROM dbo.saArtPrecio ap
                        WHERE ap.co_art = a.co_art 
                            AND RTRIM(ap.co_precio) = %s
                        ORDER BY ap.desde DESC
                    ) ap
                    OUTER APPLY (
                        SELECT TOP 1 img.rowguid AS image_guid
                        FROM dbo.saArtImagen img
                        WHERE img.co_art = a.co_art
                        ORDER BY CASE WHEN img.tip = 'PRINC' THEN 0 ELSE 1 END, img.fe_us_in DESC
                    ) img
                    WHERE {where_clause}
                        AND (stock_data.stock > 0 OR stock_data.stock IS NULL)
                    ORDER BY 
                        category_match,
                        line_match,
                        ap.price DESC
                    OFFSET 0 ROWS FETCH NEXT %s ROWS ONLY
                """
                
                params = [
                    base_category if base_category else '',
                    base_line if base_line else '',
                    warehouse_code,
                    price_code
                ]
                params.extend(where_params)
                params.append(limit)
                
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
            return []
    
    def get_frequently_bought_together(
        self,
        co_art: str,
        limit: int = 4
    ) -> list[dict[str, Any]]:
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
                
                # Obtener facturas que contienen este artículo
                invoices_query = """
                    SELECT DISTINCT fvr.doc_num
                    FROM dbo.saFacturaVentaReng fvr
                    INNER JOIN dbo.saFacturaVenta fv ON fvr.doc_num = fv.doc_num
                    WHERE fvr.co_art = %s
                        AND fv.anulado = 0
                """
                cursor.execute(invoices_query, (co_art,))
                invoices = cursor.fetchall()
                
                if not invoices:
                    cursor.close()
                    logger.debug(f"No se encontraron facturas con el artículo {co_art}")
                    # Cachear resultado vacío para evitar consultas repetidas
                    cache_service.set(cache_key, [], ttl=CACHE_TTL_FREQUENTLY_BOUGHT)
                    return []
                
                invoice_nums = [row.get('doc_num') for row in invoices]
                placeholders = ",".join(["%s"] * len(invoice_nums))
                
                # Contar artículos que aparecen en las mismas facturas
                count_query = f"""
                    SELECT 
                        fvr.co_art,
                        COUNT(DISTINCT fvr.doc_num) AS frequency
                    FROM dbo.saFacturaVentaReng fvr
                    INNER JOIN dbo.saFacturaVenta fv ON fvr.doc_num = fv.doc_num
                    WHERE fvr.doc_num IN ({placeholders})
                        AND fvr.co_art != %s
                        AND fv.anulado = 0
                    GROUP BY fvr.co_art
                    ORDER BY frequency DESC
                """
                cursor.execute(count_query, tuple(invoice_nums + [co_art]))
                frequent_articles = cursor.fetchall()[:limit]
                
                if not frequent_articles:
                    cursor.close()
                    cache_service.set(cache_key, [], ttl=CACHE_TTL_FREQUENTLY_BOUGHT)
                    return []
                
                # Obtener detalles de los artículos más frecuentes
                article_codes = [row.get('co_art') for row in frequent_articles]
                article_placeholders = ",".join(["%s"] * len(article_codes))
                
                detail_query = f"""
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
                    FROM dbo.saArticulo a
                    LEFT JOIN dbo.saCatArticulo cat ON RTRIM(a.co_cat) = RTRIM(cat.co_cat)
                    OUTER APPLY (
                        SELECT TOP 1 
                            ap.monto AS price,
                            ap.co_mone AS currency
                        FROM dbo.saArtPrecio ap
                        WHERE ap.co_art = a.co_art 
                            AND RTRIM(ap.co_precio) = '01'
                        ORDER BY ap.desde DESC
                    ) ap
                    OUTER APPLY (
                        SELECT 
                            RTRIM(sa.co_alma) AS co_alma,
                            SUM(sa.stock) AS stock
                        FROM dbo.saStockAlmacen sa
                        WHERE sa.co_art = a.co_art 
                            AND RTRIM(sa.co_alma) = '001'
                            AND sa.tipo = 'ACT'
                        GROUP BY sa.co_alma
                    ) stock_data
                    OUTER APPLY (
                        SELECT TOP 1 img.rowguid AS image_guid
                        FROM dbo.saArtImagen img
                        WHERE img.co_art = a.co_art
                        ORDER BY CASE WHEN img.tip = 'PRINC' THEN 0 ELSE 1 END, img.fe_us_in DESC
                    ) img
                    WHERE a.co_art IN ({article_placeholders})
                        AND a.anulado = 0
                """
                cursor.execute(detail_query, tuple(article_codes))
                articles = cursor.fetchall()
                cursor.close()
                
                # Ordenar según la frecuencia
                article_dict = {row.get('co_art'): row for row in articles}
                result = []
                for freq_row in frequent_articles:
                    art_code = freq_row.get('co_art')
                    if art_code in article_dict:
                        result.append(article_dict[art_code])
                
                result = result[:limit]
                
                # Guardar en caché
                cache_service.set(cache_key, result, ttl=CACHE_TTL_FREQUENTLY_BOUGHT)
                logger.debug(f"Cache SET para frecuentemente comprados: {co_art} ({len(result)} items)")
                
                return result
            
        except Exception as e:
            logger.error(f"Error obteniendo artículos frecuentemente comprados juntos para {co_art}: {e}")
            return []
    
    def get_recommended_articles(
        self,
        customer_code: str | None = None,
        limit: int = 12,
        price_code: str = "01",
        warehouse_code: str = "001"
    ) -> list[dict[str, Any]]:
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
                
                recommended = []
                
                if customer_code:
                    # Estrategia 1: Artículos de categorías que el cliente compra
                    categories_query = """
                        SELECT DISTINCT fvr.co_art, a.co_cat
                        FROM dbo.saFacturaVentaReng fvr
                        INNER JOIN dbo.saFacturaVenta fv ON fvr.doc_num = fv.doc_num
                        INNER JOIN dbo.saArticulo a ON fvr.co_art = a.co_art
                        WHERE fv.co_cli = %s
                            AND fv.anulado = 0
                            AND a.anulado = 0
                            AND a.co_cat IS NOT NULL
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
                            # Sanitizar categorías: máximo 50 chars, alfanumérico/guion/espacio
                            category_list = [
                                c[:50] for c in purchased_categories
                                if c and all(ch.isalnum() or ch in '- _' for ch in c)
                            ]
                            if not category_list:
                                category_list = []
                            category_placeholders = ",".join(["%s"] * len(category_list))
                            
                            category_query = f"""
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
                                FROM dbo.saArticulo a
                                LEFT JOIN dbo.saCatArticulo cat ON RTRIM(a.co_cat) = RTRIM(cat.co_cat)
                                OUTER APPLY (
                                    SELECT TOP 1 
                                        ap.monto AS price,
                                        ap.co_mone AS currency
                                    FROM dbo.saArtPrecio ap
                                    WHERE ap.co_art = a.co_art 
                                        AND RTRIM(ap.co_precio) = %s
                                    ORDER BY ap.desde DESC
                                ) ap
                                OUTER APPLY (
                                    SELECT 
                                        RTRIM(sa.co_alma) AS co_alma,
                                        SUM(sa.stock) AS stock
                                    FROM dbo.saStockAlmacen sa
                                    WHERE sa.co_art = a.co_art 
                                        AND RTRIM(sa.co_alma) = %s
                                        AND sa.tipo = 'ACT'
                                    GROUP BY sa.co_alma
                                ) stock_data
                                OUTER APPLY (
                                    SELECT TOP 1 img.rowguid AS image_guid
                                    FROM dbo.saArtImagen img
                                    WHERE img.co_art = a.co_art
                                    ORDER BY CASE WHEN img.tip = 'PRINC' THEN 0 ELSE 1 END, img.fe_us_in DESC
                                ) img
                                WHERE a.anulado = 0
                                    AND RTRIM(a.co_cat) IN ({category_placeholders})
                                    AND (stock_data.stock > 0 OR stock_data.stock IS NULL)
                            """
                            
                            # Excluir artículos ya comprados (validados: max 30 chars alfanuméricos)
                            if purchased_articles:
                                safe_purchased = [
                                    a[:30] for a in purchased_articles
                                    if a and all(ch.isalnum() or ch in '-_' for ch in a)
                                ]
                                if safe_purchased:
                                    article_placeholders = ",".join(["%s"] * len(safe_purchased))
                                    category_query += f" AND a.co_art NOT IN ({article_placeholders})"
                                    params.extend(safe_purchased)
                                    purchased_articles = set(safe_purchased)
                            
                            category_query += """
                                ORDER BY ap.price DESC
                                OFFSET 0 ROWS FETCH NEXT %s ROWS ONLY
                            """
                            
                            params = [price_code, warehouse_code] + category_list
                            if purchased_articles:
                                params.extend(list(purchased_articles))
                            params.append(limit)
                            
                            cursor.execute(category_query, tuple(params))
                            category_articles = cursor.fetchall()
                            recommended.extend(category_articles)
                            logger.debug(f"Encontrados {len(category_articles)} artículos de categorías del cliente")
                
                # Si no hay suficientes, completar con artículos populares
                if len(recommended) < limit:
                    popular_query = """
                        SELECT DISTINCT
                            a.co_art,
                            a.art_des,
                            a.co_cat AS category_code,
                            cat.cat_des AS category_name,
                            ap.price,
                            ap.currency,
                            stock_data.stock AS stock,
                            stock_data.co_alma AS warehouse_code,
                            img.image_guid,
                            COUNT(DISTINCT fvr.doc_num) AS sales_count
                        FROM dbo.saArticulo a
                        LEFT JOIN dbo.saCatArticulo cat ON RTRIM(a.co_cat) = RTRIM(cat.co_cat)
                        LEFT JOIN dbo.saFacturaVentaReng fvr ON a.co_art = fvr.co_art
                        LEFT JOIN dbo.saFacturaVenta fv ON fvr.doc_num = fv.doc_num AND fv.anulado = 0
                        OUTER APPLY (
                            SELECT TOP 1 
                                ap.monto AS price,
                                ap.co_mone AS currency
                            FROM dbo.saArtPrecio ap
                            WHERE ap.co_art = a.co_art 
                                AND RTRIM(ap.co_precio) = %s
                            ORDER BY ap.desde DESC
                        ) ap
                        OUTER APPLY (
                            SELECT 
                                RTRIM(sa.co_alma) AS co_alma,
                                SUM(sa.stock) AS stock
                            FROM dbo.saStockAlmacen sa
                            WHERE sa.co_art = a.co_art 
                                AND RTRIM(sa.co_alma) = %s
                                AND sa.tipo = 'ACT'
                            GROUP BY sa.co_alma
                        ) stock_data
                        OUTER APPLY (
                            SELECT TOP 1 img.rowguid AS image_guid
                            FROM dbo.saArtImagen img
                            WHERE img.co_art = a.co_art
                            ORDER BY CASE WHEN img.tip = 'PRINC' THEN 0 ELSE 1 END, img.fe_us_in DESC
                        ) img
                        WHERE a.anulado = 0
                            AND (stock_data.stock > 0 OR stock_data.stock IS NULL)
                    """
                    
                    params = [price_code, warehouse_code]
                    
                    if recommended:
                        recommended_codes = [
                            (row.get('co_art') or '').strip()[:30]
                            for row in recommended
                            if row.get('co_art')
                            and all(ch.isalnum() or ch in '-_' for ch in (row.get('co_art') or '').strip())
                        ]
                        if recommended_codes:
                            recommended_placeholders = ",".join(["%s"] * len(recommended_codes))
                            popular_query += f" AND a.co_art NOT IN ({recommended_placeholders})"
                            params.extend(recommended_codes)
                    
                    popular_query += """
                        GROUP BY a.co_art, a.art_des, a.co_cat, cat.cat_des, ap.price, ap.currency, 
                                 stock_data.stock, stock_data.co_alma, img.image_guid
                        ORDER BY sales_count DESC, ap.price DESC
                        OFFSET 0 ROWS FETCH NEXT %s ROWS ONLY
                    """
                    
                    params.append(limit - len(recommended))
                    
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
            return []
    
    @staticmethod
    def _to_decimal(value: Any) -> Decimal | None:
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
    def get_cache_stats() -> dict:
        """Obtiene estadísticas del caché."""
        return cache_service.get_stats()
