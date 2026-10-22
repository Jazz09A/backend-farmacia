from typing import Literal

from pydantic import BaseModel, Field


class CustomerAddressItem(BaseModel):
    """Dirección individual del cliente desde Profit Plus"""

    type: Literal["principal", "entrega", "secundaria"] = Field(..., description="Tipo de dirección")
    label: str = Field(..., description="Etiqueta descriptiva de la dirección")
    address: str = Field(..., description="Dirección completa")
    city: str | None = Field(None, description="Ciudad")
    postal_code: str | None = Field(None, description="Código postal")
    phones: str | None = Field(None, description="Teléfonos de contacto")
    customer_name: str | None = Field(None, description="Nombre del cliente")


class CustomerAddressesResponse(BaseModel):
    """Respuesta con las direcciones del cliente desde Profit Plus"""

    customer_code: str = Field(..., description="Código de cliente (co_cli)")
    addresses: list[CustomerAddressItem] = Field(..., description="Lista de direcciones disponibles")
