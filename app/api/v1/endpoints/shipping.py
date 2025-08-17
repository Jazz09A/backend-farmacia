from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import get_current_active_user, get_admin_user
from app.models.shipping import ShippingZone
from app.schemas.shipping import ShippingZoneCreate, ShippingZoneUpdate, ShippingZoneResponse
from app.models.user import User

router = APIRouter()

@router.get(
    "/shipping/zones",
    response_model=List[ShippingZoneResponse],
    summary="Get all shipping zones",
    tags=["Shipping Zones"]
)
def get_all_shipping_zones(db: Session = Depends(get_db)):
    """
    🚚 **Get Shipping Zones**

    Retrieves a list of all available shipping zones and their costs.
    This is a public endpoint and does not require authentication.
    """
    zones = db.query(ShippingZone).all()
    return zones

@router.post(
    "/shipping/zones",
    response_model=ShippingZoneResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new shipping zone",
    tags=["Admin", "Shipping Zones"]
)
def create_shipping_zone(
    zone_data: ShippingZoneCreate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_admin_user)
):
    """
    ➕ **Create Shipping Zone**

    Adds a new shipping zone to the database.
    *Requires admin privileges.*
    """
    db_zone = db.query(ShippingZone).filter(ShippingZone.id == zone_data.id).first()
    if db_zone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Zone with ID '{zone_data.id}' already exists."
        )
    
    new_zone = ShippingZone(**zone_data.dict())
    db.add(new_zone)
    db.commit()
    db.refresh(new_zone)
    return new_zone

@router.put(
    "/shipping/zones/{zone_id}",
    response_model=ShippingZoneResponse,
    summary="Update a shipping zone",
    tags=["Admin", "Shipping Zones"]
)
def update_shipping_zone(
    zone_id: str,
    zone_data: ShippingZoneUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_admin_user)
):
    """
    ✏️ **Update Shipping Zone**

    Updates the details of an existing shipping zone.
    *Requires admin privileges.*
    """
    db_zone = db.query(ShippingZone).filter(ShippingZone.id == zone_id).first()
    if not db_zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Zone with ID '{zone_id}' not found."
        )
    
    for key, value in zone_data.dict(exclude_unset=True).items():
        setattr(db_zone, key, value)
        
    db.commit()
    db.refresh(db_zone)
    return db_zone

@router.delete(
    "/shipping/zones/{zone_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a shipping zone",
    tags=["Admin", "Shipping Zones"]
)
def delete_shipping_zone(
    zone_id: str,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_admin_user)
):
    """
    ❌ **Delete Shipping Zone**

    Deletes a shipping zone from the database.
    *Requires admin privileges.*
    """
    db_zone = db.query(ShippingZone).filter(ShippingZone.id == zone_id).first()
    if not db_zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Zone with ID '{zone_id}' not found."
        )
    
    db.delete(db_zone)
    db.commit()
    return None
