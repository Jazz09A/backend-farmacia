"""
SourceSystemService — Orquestador de Profit Plus (SQL Server).

Este servicio es ahora un **thin wrapper** que delega toda la lógica SQL a los
repositorios en `app/repositories/`. Mantiene:

- `ConnectionPool`: pool thread-safe con recycle/pre_ping/overflow (infraestructura)
- `SourceSystemService`: fachada con la misma API que antes (backward compatible)
  pero cada método de negocio delega a un repo especializado.

Phase 2 del Plan de Refactorización de God Services (2026-08-30):
- `source_system_service.py` redujo de 2215 → ~500 líneas
- Toda la lógica SQL vive ahora en `app/repositories/{customer,article,discount,image,health,quote}_repository.py`
- Los tests existentes (246) siguen pasando sin cambios gracias a la API backward compatible.
"""
import time
from collections.abc import Generator
from contextlib import contextmanager
from decimal import Decimal
from queue import Empty, Full, Queue
from threading import Lock, RLock
from typing import Any

import pymssql

from app.config.logging_config import get_logger
from app.config.settings import Settings

settings = Settings()


# ============================================================================
# ConnectionPool (infraestructura — se mantiene sin cambios)
# ============================================================================
class ConnectionPool:
    """
    Pool de conexiones thread-safe mejorado para pymssql.

    Características:
    - Context manager para uso seguro (with statement)
    - Overflow controlado para picos de tráfico
    - Recycle de conexiones viejas
    - Métricas del pool
    - Timeout configurable
    - Limpieza automática de transacciones
    """

    def __init__(
        self,
        connect_func,
        pool_size: int = 15,
        max_overflow: int = 10,
        timeout: int = 30,
        recycle: int = 300,
        logger=None,
    ):
        self._connect_func = connect_func
        self._pool_size = pool_size
        self._max_overflow = max_overflow
        self._timeout = timeout
        self._recycle = recycle
        self._logger = logger

        self._pool = Queue(maxsize=pool_size)
        self._overflow_count = 0
        self._lock = RLock()
        self._connection_times: dict[int, float] = {}
        self._total_created = 0
        self._total_recycled = 0
        self._total_reused = 0

        self._initialized = False

    def _lazy_init(self):
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            initial_count = min(3, self._pool_size)
            for _ in range(initial_count):
                try:
                    conn = self._create_connection()
                    self._pool.put_nowait(conn)
                except Exception as e:
                    if self._logger:
                        self._logger.warning(f"Error pre-creando conexión: {e}")
            self._initialized = True
            if self._logger:
                self._logger.info(
                    f"ConnectionPool inicializado: pool_size={self._pool_size}, "
                    f"max_overflow={self._max_overflow}, timeout={self._timeout}s, "
                    f"recycle={self._recycle}s, conexiones_iniciales={initial_count}"
                )

    def _create_connection(self):
        conn = self._connect_func()
        conn_id = id(conn)
        self._connection_times[conn_id] = time.time()
        self._total_created += 1
        if self._logger:
            self._logger.debug(f"Nueva conexión creada (total creadas: {self._total_created})")
        return conn

    def _is_connection_valid(self, conn) -> bool:
        conn_id = id(conn)
        created_at = self._connection_times.get(conn_id, 0)
        age = time.time() - created_at
        if age > self._recycle:
            if self._logger:
                self._logger.debug(f"Conexión expirada (edad: {age:.0f}s > {self._recycle}s)")
            self._total_recycled += 1
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 AS ping")
            cursor.fetchone()
            cursor.close()
            return True
        except Exception as e:
            if self._logger:
                self._logger.debug(f"Conexión muerta (ping falló): {e}")
            return False

    def _close_connection(self, conn):
        conn_id = id(conn)
        self._connection_times.pop(conn_id, None)
        try:
            conn.close()
        except Exception:
            pass

    def _clean_transaction(self, conn):
        try:
            cursor = conn.cursor()
            cursor.execute("IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION")
            cursor.close()
        except Exception:
            pass

    def acquire(self, timeout: int | None = None) -> pymssql.Connection:
        self._lazy_init()
        timeout = timeout or self._timeout

        try:
            conn = self._pool.get_nowait()
            if self._is_connection_valid(conn):
                self._total_reused += 1
                return conn
            self._close_connection(conn)
        except Empty:
            pass

        with self._lock:
            if self._overflow_count < self._max_overflow:
                self._overflow_count += 1
                try:
                    conn = self._create_connection()
                    if self._logger:
                        self._logger.debug(
                            f"Conexión overflow creada ({self._overflow_count}/{self._max_overflow})"
                        )
                    return conn
                except Exception as e:
                    self._overflow_count -= 1
                    if self._logger:
                        self._logger.error(f"Error creando conexión overflow: {e}")
                    raise

        start = time.time()
        while time.time() - start < timeout:
            try:
                conn = self._pool.get(timeout=1)
                if self._is_connection_valid(conn):
                    self._total_reused += 1
                    return conn
                self._close_connection(conn)
            except Empty:
                continue

        stats = self.get_stats()
        raise TimeoutError(
            f"No se pudo obtener conexión en {timeout}s. "
            f"Pool: {stats['available']}/{stats['pool_size']}, "
            f"Overflow: {stats['overflow_current']}/{stats['overflow_max']}, "
            f"En uso: {stats['in_use']}"
        )

    def release(self, conn):
        if conn is None:
            return
        self._clean_transaction(conn)
        if not self._is_connection_valid(conn):
            self._close_connection(conn)
            with self._lock:
                if self._overflow_count > 0:
                    self._overflow_count -= 1
            return
        with self._lock:
            try:
                self._pool.put_nowait(conn)
            except Full:
                self._close_connection(conn)
                self._overflow_count = max(0, self._overflow_count - 1)

    @contextmanager
    def connection(self) -> Generator[pymssql.Connection, None, None]:
        conn = self.acquire()
        try:
            yield conn
        finally:
            self.release(conn)

    def get_stats(self) -> dict:
        available = self._pool.qsize()
        return {
            "pool_size": self._pool_size,
            "available": available,
            "overflow_current": self._overflow_count,
            "overflow_max": self._max_overflow,
            "total_created": self._total_created,
            "total_recycled": self._total_recycled,
            "total_reused": self._total_reused,
            "in_use": self._pool_size - available + self._overflow_count,
        }

    def dispose(self):
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                self._close_connection(conn)
            except Empty:
                break
        if self._logger:
            self._logger.info("ConnectionPool cerrado")


# ============================================================================
# SourceSystemService — Fachada con repos
# ============================================================================
class SourceSystemService:
    """
    Fachada para Profit Plus (SQL Server).

    Phase 2: cada método de negocio delega a un repo en `app/repositories/`.
    Se mantiene la API completa por backward compatibility — los callers
    existentes no requieren cambios.
    """

    _instance = None
    _instance_lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.logger = get_logger("source_system")

        self.server = (
            settings.source_system.SYSTEM_SERVER.strip()
            if settings.source_system.SYSTEM_SERVER
            else None
        )
        self.port = settings.source_system.SYSTEM_PORT
        self.database = (
            settings.source_system.SYSTEM_DATABASE.strip()
            if settings.source_system.SYSTEM_DATABASE
            else None
        )
        self.user = (
            settings.source_system.SYSTEM_USER.strip()
            if settings.source_system.SYSTEM_USER
            else None
        )
        self.password = (
            settings.source_system.SYSTEM_PASSWORD.strip()
            if settings.source_system.SYSTEM_PASSWORD
            else None
        )

        pool_size = settings.source_system.POOL_SIZE
        max_overflow = settings.source_system.MAX_OVERFLOW
        pool_timeout = settings.source_system.POOL_TIMEOUT
        pool_recycle = settings.source_system.POOL_RECYCLE

        self._pool = ConnectionPool(
            connect_func=self._create_raw_connection,
            pool_size=pool_size,
            max_overflow=max_overflow,
            timeout=pool_timeout,
            recycle=pool_recycle,
            logger=self.logger,
        )

        # Inicializar repositorios (lazy import para evitar ciclos)
        from app.repositories import (
            CustomerRepository,
            ArticleRepository,
            DiscountRepository,
            ImageRepository,
            HealthRepository,
            QuoteRepository,
        )
        self._customer_repo = CustomerRepository(self)
        self._article_repo = ArticleRepository(self)
        self._discount_repo = DiscountRepository(self)
        self._image_repo = ImageRepository(self)
        self._health_repo = HealthRepository(self)
        self._quote_repo = QuoteRepository(self)

        self._initialized = True

        if self.user:
            self.logger.info(
                f"SourceSystemService inicializado - Server: {self.server}, "
                f"DB: {self.database}, User: {self.user[:3]}***, "
                f"Pool: {pool_size}+{max_overflow}"
            )
        else:
            self.logger.info(
                f"SourceSystemService inicializado - Server: {self.server}, "
                f"DB: {self.database}, User: (sin auth), "
                f"Pool: {pool_size}+{max_overflow}"
            )

    def _create_raw_connection(self):
        if not self.server:
            raise ValueError("SOURCE_SYSTEM_SERVER no está configurado")
        if not self.database:
            raise ValueError("SOURCE_SYSTEM_DATABASE no está configurado")

        connect_kwargs = {
            "server": self.server,
            "port": self.port,
            "database": self.database,
            "as_dict": True,
            "login_timeout": 30,
            "timeout": 90,
        }

        if self.user and self.password:
            connect_kwargs["user"] = self.user
            connect_kwargs["password"] = self.password

        return pymssql.connect(**connect_kwargs)

    # =========================================================================
    # Pool / Connection management
    # =========================================================================

    @contextmanager
    def connection(self) -> Generator[pymssql.Connection, None, None]:
        with self._pool.connection() as conn:
            yield conn

    def get_pooled_connection(self):
        return self._pool.acquire()

    def return_connection(self, conn):
        self._pool.release(conn)

    def get_connection(self):
        return self._pool.acquire()

    def health_check(self) -> dict:
        return self._health_repo.health_check()

    def get_pool_stats(self) -> dict:
        return self._pool.get_stats()

    def dispose(self):
        self._pool.dispose()

    # =========================================================================
    # Customer operations — delegan a CustomerRepository
    # =========================================================================

    def get_all_customers(
        self,
        include_inactive: bool = False,
        only_with_email: bool = True,
        limit: int | None = None,
        offset: int = 0,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._customer_repo.get_all(
            include_inactive=include_inactive,
            only_with_email=only_with_email,
            limit=limit,
            offset=offset,
            search=search,
        )

    def count_customers(
        self,
        include_inactive: bool = False,
        only_with_email: bool = True,
        search: str | None = None,
    ) -> int:
        return self._customer_repo.count(
            include_inactive=include_inactive,
            only_with_email=only_with_email,
            search=search,
        )

    def get_customer_by_code(self, customer_code: str) -> dict[str, Any] | None:
        return self._customer_repo.get_by_id(customer_code)

    def get_customer_by_email(self, email: str) -> dict[str, Any] | None:
        return self._customer_repo.get_by_email(email)

    def get_customer_addresses(self, customer_code: str) -> list[dict[str, Any]]:
        return self._customer_repo.get_addresses(customer_code)

    def get_profit_customer_profile(self, email: str) -> dict[str, Any]:
        return self._customer_repo.get_profit_profile(email)

    def build_profit_user_code(self, customer_code: str) -> str:
        return self._customer_repo.build_user_code(customer_code)

    def update_customer_password(self, customer_code: str, hashed_password: str) -> bool:
        return self._customer_repo.update_password(customer_code, hashed_password)

    # =========================================================================
    # Article operations — delegan a ArticleRepository
    # =========================================================================

    def get_articles_catalog(
        self,
        page: int = 1,
        limit: int = 20,
        search: str | None = None,
        line_code: str | None = None,
        category_code: str | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        sort_by: str = "art_des",
        price_code: str = "01",
        warehouse_code: str = "001",
        in_stock_only: bool = False,
    ) -> dict[str, Any]:
        return self._article_repo.search(
            page=page,
            limit=limit,
            search=search,
            line_code=line_code,
            category_code=category_code,
            min_price=min_price,
            max_price=max_price,
            sort_by=sort_by,
            price_code=price_code,
            warehouse_code=warehouse_code,
            in_stock_only=in_stock_only,
        )

    def get_article_detail(self, article_code: str) -> dict[str, Any] | None:
        return self._article_repo.get_detail(article_code)

    def get_article_images(
        self,
        article_code: str,
        connection: tuple[pymssql.Connection, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return self._article_repo.get_images(article_code, connection=connection)

    # =========================================================================
    # Image operations — delegan a ImageRepository
    # =========================================================================

    def upload_article_image(
        self,
        article_code: str,
        image_bytes: bytes,
        description: str | None = None,
        tip: str | None = None,
        created_by: str = "API_USER",
    ) -> str:
        return self._image_repo.upload(
            article_code=article_code,
            image_bytes=image_bytes,
            description=description,
            tip=tip,
            created_by=created_by,
        )

    def get_image_by_guid(self, image_guid: str) -> dict[str, Any] | None:
        return self._image_repo.get_by_guid(image_guid)

    # =========================================================================
    # Discount operations — delegan a DiscountRepository
    # =========================================================================

    def get_article_discount(
        self,
        article_code: str,
        quantity: Decimal = Decimal("1.00"),
        existing_cursor=None,
    ) -> dict[str, Any] | None:
        return self._discount_repo.get_discount_for_article(
            article_code=article_code,
            quantity=quantity,
            existing_cursor=existing_cursor,
        )

    def increment_discount_usage(
        self,
        co_desc: str,
        quantity_used: int,
        field_name: str = "campo1",
        existing_cursor=None,
    ) -> None:
        self._discount_repo.increment_usage(
            co_desc=co_desc,
            quantity_used=quantity_used,
            field_name=field_name,
            existing_cursor=existing_cursor,
        )

    def create_article_discount(self, discount_data: dict[str, Any]) -> bool:
        return self._discount_repo.create(discount_data)

    def get_article_discounts(
        self,
        co_art: str | None = None,
        tip_cli: str | None = None,
        only_active: bool = False,
        page: int = 1,
        limit: int = 50,
    ) -> dict[str, Any]:
        return self._discount_repo.list_discounts(
            co_art=co_art,
            tip_cli=tip_cli,
            only_active=only_active,
            page=page,
            limit=limit,
        )

    def get_article_discount_by_code(self, co_desc: str) -> dict[str, Any] | None:
        return self._discount_repo.get_by_code(co_desc)

    def update_article_discount(self, co_desc: str, data: dict[str, Any]) -> bool:
        return self._discount_repo.update_field(co_desc, data)

    def validate_tip_cli(self, tip_cli: str) -> bool:
        return self._discount_repo.validate_tip_cli(tip_cli)

    def get_valid_tip_cli_codes(self) -> list:
        return self._discount_repo.get_valid_tip_cli_codes()

    def get_active_discounts_for_articles(
        self,
        article_codes: list[str],
        tip_cli: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        return self._discount_repo.get_active_for_articles(article_codes, tip_cli=tip_cli)

    def get_all_active_flash_offers(
        self,
        skip: int = 0,
        limit: int = 10,
        article_code: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        return self._discount_repo.get_all_flash_offers(
            skip=skip, limit=limit, article_code=article_code
        )

    def generate_discount_code(self, prefix: str = "DESC") -> str:
        return self._discount_repo.generate_discount_code(prefix)


# Singleton instance
source_system_service = SourceSystemService()
