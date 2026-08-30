
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.models.product import Product


class ImageService:
    def __init__(self, db: Session = Depends(get_db)):
        self.db = db
    
    def get_product_by_id(self, product_id: str):
        product = self.db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        return product
    
    # =============================================================================
    # ADD IMAGES TO PRODUCT
    # =============================================================================
    async def add_images_to_product(self, product_id: str, images: list[str] | None = None):
        if images is None:
            raise HTTPException(status_code=400, detail="No se proporcionaron imágenes")
        
        product = self.get_product_by_id(product_id)
        
        for image in images:
            product.images.append(image)
            
        self.db.commit()
        return product
    
    # =============================================================================
    # GET IMAGES FROM PRODUCT
    # =============================================================================
    async def get_images_from_product(self, product_id: str):
        product = self.get_product_by_id(product_id)
        return product.images
    
    # =============================================================================
    # DELETE IMAGE FROM PRODUCT
    # =============================================================================
    async def delete_image_from_product(self, product_id: str, image_url: str):
        product = self.get_product_by_id(product_id)
        
        product.images.remove(image_url)
        self.db.commit()
        return product
    
    # =============================================================================
    # GET ALL IMAGES
    # =============================================================================
    async def get_all_images(self, product_id: str):
        product = self.get_product_by_id(product_id)
        return product.images
