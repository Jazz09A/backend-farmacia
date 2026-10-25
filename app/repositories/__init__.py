# Repositories package
# Protocol interfaces for SourceSystem (Profit Plus) data access

from .protocols import (
    ArticleRepositoryProtocol,
    CustomerRepositoryProtocol,
    DiscountRepositoryProtocol,
    HealthRepositoryProtocol,
    ImageRepositoryProtocol,
)

# Concrete implementations
from .customer_repository import CustomerRepository
from .article_repository import ArticleRepository
from .discount_repository import DiscountRepository
from .image_repository import ImageRepository
from .health_repository import HealthRepository
from .quote_repository import QuoteRepository

__all__ = [
    "ArticleRepositoryProtocol",
    "CustomerRepositoryProtocol",
    "DiscountRepositoryProtocol",
    "HealthRepositoryProtocol",
    "ImageRepositoryProtocol",
    "ArticleRepository",
    "CustomerRepository",
    "DiscountRepository",
    "ImageRepository",
    "HealthRepository",
    "QuoteRepository",
]