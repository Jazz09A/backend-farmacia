from fastapi import APIRouter

from app.services.exchange_service import ExchangeRateService

exchange_service = ExchangeRateService()

router = APIRouter()


@router.get("/")
async def get_exchange_rate():
    """
    Get the current exchange rate.
    """
    exchange_rate = await exchange_service.get_exchange_rate()
    return {"exchange_rate": exchange_rate}
