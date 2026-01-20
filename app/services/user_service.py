from sqlalchemy.orm import Session
from app.models.user import User
from app.services.source_system_service import source_system_service
from app.services.cache_service import cache_service
from app.config.logging_config import get_logger

logger = get_logger(__name__)

class UserService:
    def __init__(self, db: Session):
        self.db = db

    def get_user_by_id(self, user_id: str) -> User:
        return self.db.query(User).filter(User.id == user_id).first()
    
    def get_user_stats_by_id(self, user_id: str, user_email: str = None) -> dict:
        """
        Obtiene estadísticas del usuario desde source_system (DEMOA).
        
        Args:
            user_id: ID del usuario en la base de datos local
            user_email: Email del usuario (opcional, se obtiene del user si no se proporciona)
            
        Returns:
            Diccionario con total_orders, total_spent, total_products_purchased
        """
        user = self.get_user_by_id(user_id)
        if not user:
            logger.warning(f"Usuario {user_id} no encontrado")
            return {
                "total_orders": 0,
                "total_spent": 0.0,
                "total_products_purchased": 0
            }
        
        # Usar el email proporcionado o el del usuario
        email = user_email or user.email
        
        try:
            # Obtener código de cliente desde source_system
            customer = source_system_service.get_customer_by_email(email)
            if not customer or not customer.get('customer_code'):
                logger.warning(f"No se encontró cliente en source_system para email: {email}")
                return {
                    "total_orders": 0,
                    "total_spent": 0.0,
                    "total_products_purchased": 0
                }
            
            customer_code = (customer.get('customer_code') or '').strip()
            if not customer_code:
                logger.warning(f"Código de cliente vacío para email: {email}")
                return {
                    "total_orders": 0,
                    "total_spent": 0.0,
                    "total_products_purchased": 0
                }
            
            logger.debug(f"Obteniendo estadísticas para cliente {customer_code} (email: {email})")
            
            # Obtener estadísticas desde source_system
            return self._get_stats_from_source_system(customer_code)
            
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas desde source_system para usuario {user_id}: {e}")
            # Retornar valores por defecto en caso de error
            return {
                "total_orders": 0,
                "total_spent": 0.0,
                "total_products_purchased": 0
            }
    
    def _get_stats_from_source_system(self, customer_code: str) -> dict:
        """
        Obtiene estadísticas del cliente desde Profit Plus.
        Optimizado con context manager y caché (10 min).
        
        Las estadísticas se calculan desde las facturas (productos ya comprados):
        - total_orders: Total de facturas del cliente (COUNT de facturas únicas)
        - total_spent: Suma del total_neto de todas las facturas
        - total_products_purchased: Suma de la cantidad de productos comprados (total_art de los renglones)
        
        Args:
            customer_code: Código de cliente (co_cli) en Profit Plus
            
        Returns:
            Diccionario con total_orders, total_spent, total_products_purchased
        """
        # Normalizar código
        normalized_code = (customer_code or '').strip()
        empty_stats = {
            'total_orders': 0,
            'total_spent': 0.0,
            'total_products_purchased': 0
        }
        
        if not normalized_code:
            return empty_stats
        
        # Intentar obtener del caché (10 minutos)
        cache_key = f"user_stats:customer:{normalized_code}"
        try:
            cached = cache_service.get(cache_key)
            if cached is not None:
                return cached
        except Exception:
            pass
        
        try:
            # Usar context manager para evitar leaks
            with source_system_service.connection() as conn:
                cursor = conn.cursor()
                
                # Usar subconsultas para evitar que el JOIN multiplique el total_neto
                # cuando una factura tiene múltiples renglones
                query = """
                SELECT 
                    (SELECT COUNT(DISTINCT doc_num) 
                     FROM saFacturaVenta 
                     WHERE RTRIM(co_cli) = %s AND anulado = 0) AS total_orders,
                    
                    (SELECT ISNULL(SUM(total_neto), 0) 
                     FROM saFacturaVenta 
                     WHERE RTRIM(co_cli) = %s AND anulado = 0) AS total_spent,
                    
                    (SELECT ISNULL(SUM(fr.total_art), 0) 
                     FROM saFacturaVentaReng fr
                     INNER JOIN saFacturaVenta f ON fr.doc_num = f.doc_num
                     WHERE RTRIM(f.co_cli) = %s AND f.anulado = 0) AS total_products_purchased
                """
                
                cursor.execute(query, (normalized_code, normalized_code, normalized_code))
                result = cursor.fetchone()
                cursor.close()
                
                if result:
                    stats = {
                        'total_orders': result.get('total_orders', 0) or 0,
                        'total_spent': float(result.get('total_spent', 0) or 0),
                        'total_products_purchased': result.get('total_products_purchased', 0) or 0
                    }
                    
                    logger.info(
                        f"Estadísticas obtenidas para cliente {normalized_code}",
                        extra={
                            'customer_code': normalized_code,
                            **stats
                        }
                    )
                    
                    # Cachear resultado (10 minutos)
                    try:
                        cache_service.set(cache_key, stats, ttl=600)
                    except Exception:
                        pass
                    
                    return stats
                
                return empty_stats
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas desde source_system para cliente {customer_code}: {e}", exc_info=True)
            return empty_stats