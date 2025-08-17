from pydantic import BaseModel, Field
from typing import Optional
import uuid
from datetime import datetime

class AddressBase(BaseModel):
    street: str = Field(..., description="Street name and number.")
    city: str = Field(..., description="City.")
    state: str = Field(..., description="State or province.")
    postal_code: Optional[str] = Field(None, description="Postal code.")
    country: str = Field("Venezuela", description="Country.")
    recipient_name: str = Field(..., description="Full name of the recipient.")
    recipient_phone: str = Field(..., description="Contact phone number of the recipient.")
    address_type: Optional[str] = Field(None, description="Type of address (e.g., home, office).")
    delivery_instructions: Optional[str] = Field(None, description="Special instructions for delivery.")
    is_default: bool = Field(False, description="Is this the default address?")

class AddressCreate(AddressBase):
    pass

class AddressUpdate(BaseModel):
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_phone: Optional[str] = None
    address_type: Optional[str] = None
    delivery_instructions: Optional[str] = None
    is_default: Optional[bool] = None

class AddressResponse(AddressBase):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
