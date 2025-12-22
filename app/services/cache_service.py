import time
import hashlib
import json
from typing import Any, Optional, Dict
from threading import RLock
from app.config.settings import Settings
from app.config.logging_config import get_logger

settings = Settings()


class CacheEntry:
    """Entrada de cache con TTL."""
    
    def __init__(self, value: Any, ttl: int):
        self.value = value
        self.created_at = time.time()
        self.ttl = ttl
    
    def is_expired(self) -> bool:
        """Verifica si la entrada ha expirado."""
        if self.ttl <= 0:
            return False  # Sin expiración
        return (time.time() - self.created_at) > self.ttl
    
    def age(self) -> float:
        """Retorna la edad de la entrada en segundos."""
        return time.time() - self.created_at


class CacheService:
    """
    Servicio de cache en memoria thread-safe con soporte para TTL.
    
    Características:
    - Thread-safe usando RLock
    - TTL configurable por entrada
    - Limpieza automática de entradas expiradas
    - Estadísticas de uso
    """
    
    _instance = None
    _instance_lock = RLock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return
        
        self.logger = get_logger("cache")
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = RLock()
        self._enabled = getattr(settings, 'CACHE_ENABLED', True)
        
        # Estadísticas
        self._stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'invalidations': 0,
            'cleanups': 0,
        }
        
        self._initialized = True
        self.logger.info("CacheService inicializado")
    
    def _generate_key(self, prefix: str, *args, **kwargs) -> str:
        """
        Genera una clave de cache única basada en parámetros.
        
        Args:
            prefix: Prefijo para el tipo de cache (ej: 'catalog', 'article')
            *args: Argumentos posicionales a incluir en la clave
            **kwargs: Argumentos con nombre a incluir en la clave
        
        Returns:
            Clave de cache única
        """
        # Normalizar valores None a string vacío
        parts = [prefix]
        
        for arg in args:
            if arg is None:
                parts.append('')
            elif isinstance(arg, (int, float, str)):
                parts.append(str(arg))
            else:
                parts.append(str(arg))
        
        # Ordenar kwargs para consistencia
        sorted_kwargs = sorted(kwargs.items())
        for key, value in sorted_kwargs:
            if value is None:
                parts.append(f"{key}=")
            else:
                parts.append(f"{key}={value}")
        
        key_string = ":".join(parts)
        
        # Si la clave es muy larga, usar hash
        if len(key_string) > 200:
            key_hash = hashlib.md5(key_string.encode()).hexdigest()
            return f"{prefix}:hash:{key_hash}"
        
        return key_string
    
    def get(self, key: str) -> Optional[Any]:
        """
        Obtiene un valor del cache.
        
        Args:
            key: Clave de cache
        
        Returns:
            Valor cacheado o None si no existe o ha expirado
        """
        if not self._enabled:
            return None
        
        with self._lock:
            entry = self._cache.get(key)
            
            if entry is None:
                self._stats['misses'] += 1
                return None
            
            if entry.is_expired():
                # Eliminar entrada expirada
                del self._cache[key]
                self._stats['misses'] += 1
                return None
            
            self._stats['hits'] += 1
            return entry.value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Almacena un valor en el cache.
        
        Args:
            key: Clave de cache
            value: Valor a almacenar
            ttl: Tiempo de vida en segundos. Si es None, usa el TTL por defecto del tipo
        """
        if not self._enabled:
            return
        
        with self._lock:
            # Si no se especifica TTL, usar el por defecto según el prefijo
            if ttl is None:
                ttl = self._get_default_ttl(key)
            
            self._cache[key] = CacheEntry(value, ttl)
            self._stats['sets'] += 1
    
    def _get_default_ttl(self, key: str) -> int:
        """Obtiene el TTL por defecto según el tipo de cache."""
        if key.startswith('catalog:'):
            return getattr(settings, 'CACHE_CATALOG_TTL', 1800)  # 30 minutos
        elif key.startswith('article:'):
            return getattr(settings, 'CACHE_DETAIL_TTL', 3600)  # 60 minutos
        elif key.startswith('categories:') or key.startswith('lines:'):
            return getattr(settings, 'CACHE_STATIC_TTL', 7200)  # 2 horas
        else:
            return getattr(settings, 'CACHE_DEFAULT_TTL', 1800)  # 30 minutos por defecto
    
    def invalidate(self, key: str) -> bool:
        """
        Invalida una entrada específica del cache.
        
        Args:
            key: Clave de cache a invalidar
        
        Returns:
            True si se invalidó, False si no existía
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._stats['invalidations'] += 1
                return True
            return False
    
    def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalida todas las entradas que coincidan con un patrón.
        
        Args:
            pattern: Patrón de prefijo (ej: 'catalog:', 'article:ABC123')
        
        Returns:
            Número de entradas invalidadas
        """
        count = 0
        with self._lock:
            keys_to_remove = [key for key in self._cache.keys() if key.startswith(pattern)]
            for key in keys_to_remove:
                del self._cache[key]
                count += 1
                self._stats['invalidations'] += 1
        return count
    
    def clear(self) -> int:
        """
        Limpia todo el cache.
        
        Returns:
            Número de entradas eliminadas
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._stats['invalidations'] += count
        return count
    
    def cleanup_expired(self) -> int:
        """
        Limpia todas las entradas expiradas del cache.
        
        Returns:
            Número de entradas eliminadas
        """
        count = 0
        with self._lock:
            keys_to_remove = [
                key for key, entry in self._cache.items()
                if entry.is_expired()
            ]
            for key in keys_to_remove:
                del self._cache[key]
                count += 1
        
        if count > 0:
            self._stats['cleanups'] += count
            self.logger.debug(f"Limpieza automática: {count} entradas expiradas eliminadas")
        
        return count
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas del cache.
        
        Returns:
            Diccionario con estadísticas
        """
        with self._lock:
            total_entries = len(self._cache)
            expired_count = sum(1 for entry in self._cache.values() if entry.is_expired())
            
            total_requests = self._stats['hits'] + self._stats['misses']
            hit_rate = (self._stats['hits'] / total_requests * 100) if total_requests > 0 else 0
            
            return {
                'enabled': self._enabled,
                'total_entries': total_entries,
                'expired_entries': expired_count,
                'active_entries': total_entries - expired_count,
                'hits': self._stats['hits'],
                'misses': self._stats['misses'],
                'sets': self._stats['sets'],
                'invalidations': self._stats['invalidations'],
                'cleanups': self._stats['cleanups'],
                'hit_rate': round(hit_rate, 2),
                'total_requests': total_requests,
            }
    
    def enable(self):
        """Habilita el cache."""
        self._enabled = True
        self.logger.info("Cache habilitado")
    
    def disable(self):
        """Deshabilita el cache."""
        self._enabled = False
        self.logger.info("Cache deshabilitado")


# Instancia singleton
cache_service = CacheService()

