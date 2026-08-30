"""
Exchange Rate Service

This service handles fetching exchange rates from the BCV API and updating product prices.
"""
import logging
from datetime import timedelta
from typing import Any

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.product import Product
from app.utils.timezone import get_ve_now

logger = logging.getLogger(__name__)

class ExchangeRateService:
    """Service to handle USD to VES exchange rate operations."""
    
    def __init__(self):
        self.base_url = "https://uneven-pru-jazz09a-0be5d85c.koyeb.app"
        self.rate_endpoint = "/api/v1/rate"
        self.refresh_endpoint = "/api/v1/rate/refresh"
        self._cached_rate = None
        self._last_fetch = None
        self._cache_duration = timedelta(hours=1)  # Cache for 1 hour
    
    async def get_exchange_rate(self, force_refresh: bool = False) -> dict[str, Any] | None:
        """
        Get the current USD to VES exchange rate.
        
        Args:
            force_refresh: If True, force refresh the rate from the API
            
        Returns:
            Dict containing rate information or None if failed
            Example: {
                "price": 36.5,
                "timestamp": "2024-01-15T10:30:00",
                "source": "BCV",
                "status": "success"
            }
        """
        # Check cache first (unless force refresh)
        if not force_refresh and self._is_cache_valid():
            logger.info("Using cached exchange rate")
            return self._cached_rate
        
        try:
            endpoint = self.refresh_endpoint if force_refresh else self.rate_endpoint
            url = f"{self.base_url}{endpoint}"
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                logger.info(f"Fetching exchange rate from: {url}")
                response = await client.get(url)
                response.raise_for_status()
                
                rate_data = response.json()
                
                # Validate response structure
                if not self._validate_rate_response(rate_data):
                    logger.error(f"Invalid rate response structure: {rate_data}")
                    return None
                
                # Cache the response
                self._cached_rate = rate_data
                self._last_fetch = get_ve_now()
                
                logger.info(f"Exchange rate fetched successfully: {rate_data['price']} VES/USD")
                return rate_data
                
        except httpx.TimeoutException:
            logger.error("Timeout fetching exchange rate")
            return None
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching exchange rate: {e.response.status_code}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching exchange rate: {e!s}")
            return None
    
    def _is_cache_valid(self) -> bool:
        """Check if cached rate is still valid."""
        if not self._cached_rate or not self._last_fetch:
            return False
        
        return get_ve_now() - self._last_fetch < self._cache_duration
    
    def _validate_rate_response(self, data: dict[str, Any]) -> bool:
        """Validate the structure of the rate response."""
        required_fields = ["price", "timestamp", "source", "status"]
        return all(field in data for field in required_fields) and isinstance(data["price"], (int, float))
    
    async def update_all_product_prices(self, db: Session, force_refresh: bool = False) -> dict[str, Any]:
        """
        Update all product prices based on the current exchange rate.
        
        Args:
            db: Database session
            force_refresh: Force refresh the exchange rate
            
        Returns:
            Dict with update results
        """
        # Get current exchange rate
        rate_data = await self.get_exchange_rate(force_refresh=force_refresh)
        
        if not rate_data:
            return {
                "success": False,
                "message": "Failed to fetch exchange rate",
                "updated_count": 0,
                "exchange_rate": None
            }
        
        exchange_rate = rate_data["price"]
        
        try:
            # Get all products
            products = db.query(Product).all()
            updated_count = 0
            
            for product in products:
                # Calculate new VES price based on USD reference price
                new_price_ves = round(product.price_ref * exchange_rate, 2)
                
                # Only update if the price has changed
                if product.price_ves != new_price_ves:
                    product.price_ves = new_price_ves
                    product.updated_at = func.now()
                    updated_count += 1
            
            # Commit all changes
            db.commit()
            
            logger.info(f"Updated {updated_count} product prices with exchange rate {exchange_rate}")
            
            return {
                "success": True,
                "message": f"Successfully updated {updated_count} product prices",
                "updated_count": updated_count,
                "exchange_rate": exchange_rate,
                "rate_timestamp": rate_data["timestamp"],
                "rate_source": rate_data["source"]
            }
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating product prices: {e!s}")
            return {
                "success": False,
                "message": f"Error updating product prices: {e!s}",
                "updated_count": 0,
                "exchange_rate": exchange_rate
            }
    
    def calculate_ves_price(self, usd_price: float, exchange_rate: float) -> float:
        """
        Calculate VES price from USD price and exchange rate.
        
        Args:
            usd_price: Price in USD
            exchange_rate: Current exchange rate (VES per USD)
            
        Returns:
            Price in VES, rounded to 2 decimal places
        """
        return round(usd_price * exchange_rate, 2)
    
    async def get_current_rate_for_product_creation(self) -> float | None:
        """
        Get the current exchange rate for product creation.
        Uses cached rate if available, otherwise fetches fresh data.
        
        Returns:
            Current exchange rate or None if failed
        """
        rate_data = await self.get_exchange_rate(force_refresh=False)
        return rate_data["price"] if rate_data else None


# Global instance
exchange_service = ExchangeRateService()
