from datetime import datetime

from pydantic import BaseModel, Field


class AddressBase(BaseModel):
    street: str = Field(..., description="Street name and number.")
    city: str = Field(..., description="City.")
    state: str = Field(..., description="State or province.")
    postal_code: str | None = Field(None, description="Postal code.")
    country: str = Field("Venezuela", description="Country.")
    recipient_name: str = Field(..., description="Full name of the recipient.")
    recipient_phone: str = Field(..., description="Contact phone number of the recipient.")
    address_type: str | None = Field(None, description="Type of address (e.g., home, office).")
    delivery_instructions: str | None = Field(None, description="Special instructions for delivery.")
    is_default: bool = Field(False, description="Is this the default address?")
    # shipping_zone_id eliminado - ShippingZone no se usa con Profit Plus
    
class AddressCreate(AddressBase):
    pass

class AddressUpdate(BaseModel):
    street: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    recipient_name: str | None = None
    recipient_phone: str | None = None
    address_type: str | None = None
    delivery_instructions: str | None = None
    is_default: bool | None = None

class AddressResponse(AddressBase):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
