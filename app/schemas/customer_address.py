from pydantic import BaseModel, Field
from typing import Optional, List, Literal


class CustomerAddressItem(BaseModel):
    """Dirección individual del cliente desde Profit Plus"""
    type: Literal["principal", "entrega", "secundaria"] = Field(..., description="Tipo de dirección")
    label: str = Field(..., description="Etiqueta descriptiva de la dirección")
    address: str = Field(..., description="Dirección completa")
    city: Optional[str] = Field(None, description="Ciudad")
    postal_code: Optional[str] = Field(None, description="Código postal")
    phones: Optional[str] = Field(None, description="Teléfonos de contacto")
    customer_name: Optional[str] = Field(None, description="Nombre del cliente")


class CustomerAddressesResponse(BaseModel):
    """Respuesta con las direcciones del cliente desde Profit Plus"""
    customer_code: str = Field(..., description="Código de cliente (co_cli)")
    addresses: List[CustomerAddressItem] = Field(..., description="Lista de direcciones disponibles")

