from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class QuoteItem(BaseModel):
    line_number: int = Field(..., ge=1)
    product_code: str
    product_name: Optional[str] = None
    quantity: float = Field(..., gt=0)
    unit_price: str
    discount_amount: Optional[str] = "0.00"
    tax_amount: Optional[str] = "0.00"


class QuoteCustomer(BaseModel):
    code: str
    email: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None


class QuoteDelivery(BaseModel):
    mode: Optional[Literal["pickup", "delivery"]] = "pickup"
    address_id: Optional[str] = None
    notes: Optional[str] = None


class QuoteCreate(BaseModel):
    customer: QuoteCustomer
    channel: Optional[str] = "web_b2b"
    valid_until: Optional[str] = None  # ISO 8601 string
    currency: Optional[str] = "VES"
    payment_terms: Optional[str] = "CONTADO"
    delivery: Optional[QuoteDelivery] = None
    notes: Optional[str] = None
    items: List[QuoteItem]


class QuoteCreatedResponse(BaseModel):
    quote_id: str
    profit_plus_id: str
    status: Literal["pending", "accepted", "expired", "cancelled", "converted"]
    currency: str
    total_net: str
    total_tax: str
    total_gross: str
    expires_at: Optional[str] = None
    email_sent_at: Optional[str] = None


class QuoteListItem(BaseModel):
    quote_id: str
    profit_plus_id: str
    status: Literal["pending", "accepted", "expired", "cancelled", "converted"]
    created_at: str
    expires_at: Optional[str] = None
    total_gross: str
    currency: str
    items_count: int
    email_sent_at: Optional[str] = None


class Pagination(BaseModel):
    page: int
    page_size: int
    total_pages: int
    total_items: int


class QuoteListResponse(BaseModel):
    results: List[QuoteListItem]
    pagination: Pagination


class QuoteDetailItem(BaseModel):
    line_number: int
    product_code: str
    product_name: Optional[str] = None
    quantity: str
    unit_price: str
    discount_amount: str
    tax_amount: str
    line_total: str


class QuoteHistoryEvent(BaseModel):
    timestamp: str
    event: str
    detail: Optional[str] = None


class QuoteTotals(BaseModel):
    total_net: str
    total_tax: str
    total_discount: Optional[str] = "0.00"
    total_gross: str


class QuoteDetailResponse(BaseModel):
    quote_id: str
    profit_plus_id: str
    status: Literal["pending", "accepted", "expired", "cancelled", "converted"]
    created_at: str
    expires_at: Optional[str] = None
    currency: str
    payment_terms: Optional[str] = None
    delivery: Optional[dict] = None
    totals: QuoteTotals
    items: List[QuoteDetailItem]
    history: List[QuoteHistoryEvent] = []


class QuoteStatus(BaseModel):
    code: Literal["pending", "accepted", "expired", "cancelled", "converted"]
    label: str
    description: str


