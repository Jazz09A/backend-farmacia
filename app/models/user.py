import uuid

from sqlalchemy import JSON, Boolean, Column, Date, DateTime, String
from sqlalchemy.orm import relationship

from app.config.database import Base
from app.utils.timezone import get_ve_now


class User(Base):
    __tablename__ = "users"
    
    # Primary key
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Authentication fields
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    
    # Common user information
    user_type = Column(String, nullable=False, index=True)  # 'natural' o 'juridico'
    phone = Column(String, nullable=False)
    preferred_currency = Column(String, default='VES')
    
    # Natural user fields (persona)
    first_name = Column(String, nullable=True)  # Only for natural users
    last_name = Column(String, nullable=True)   # Only for natural users
    cedula = Column(String, nullable=True)      # Only for natural users
    birth_date = Column(Date, nullable=True)    # Only for natural users
    address = Column(String, nullable=True)     # Only for natural users
    
    # Juridico user fields (empresa/farmacia)
    company_name = Column(String, nullable=True)           # Only for juridico users
    rif = Column(String, nullable=True)                    # Only for juridico users
    registro_mercantil = Column(String, nullable=True)     # Only for juridico users
    
    # Representantes legales
    representante_legal_cedula = Column(String, nullable=True)
    representante_legal_nombre = Column(String, nullable=True)
    representantes_adicionales = Column(JSON, nullable=True)  # List of cédulas
    
    # Referencias comerciales y bancarias
    referencia_comercial_proveedor = Column(String, nullable=True)
    referencia_bancaria = Column(String, nullable=True)
    
    # Contactos especializados - Dueño
    dueno_telefono = Column(String, nullable=True)
    dueno_email = Column(String, nullable=True)
    dueno_cumpleanos = Column(Date, nullable=True)
    
    # Contactos especializados - Encargado de compras
    encargado_compra_telefono = Column(String, nullable=True)
    encargado_compra_email = Column(String, nullable=True)
    encargado_compra_cumpleanos = Column(Date, nullable=True)
    
    # Contactos especializados - Encargado de cobranzas
    encargado_cobranza_telefono = Column(String, nullable=True)
    encargado_cobranza_email = Column(String, nullable=True)
    encargado_cobranza_cumpleanos = Column(Date, nullable=True)
    
    # Información adicional para jurídicos
    redes_sociales = Column(String, nullable=True)
    pagina_web = Column(String, nullable=True)
    codigo_sicm = Column(String, nullable=True)
    fotos_establecimiento = Column(JSON, nullable=True)  # List of URLs
    direccion_establecimiento = Column(String, nullable=True)
    
    # Account status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    
    # Role system
    role = Column(String, default="user", nullable=False)  # user, manager, admin, super_admin
    
    # Email verification
    verification_token = Column(String, nullable=True)
    
    # Password reset
    reset_token = Column(String, nullable=True)
    reset_token_expires = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=get_ve_now)
    updated_at = Column(DateTime, default=get_ve_now, onupdate=get_ve_now)
    last_login = Column(DateTime, nullable=True)

    # Relationships
    addresses = relationship("Address", back_populates="user", cascade="all, delete-orphan")
    # orders relationship eliminado - Order no se usa con Profit Plus
    # orders = relationship("Order", back_populates="user")
    cart_items = relationship("CartItem", back_populates="user", cascade="all, delete-orphan")
    preferences = relationship("UserPreferences", back_populates="user", uselist=False, cascade="all, delete-orphan")
    favorites = relationship("UserFavorite", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        if self.user_type == 'natural':
            name = f"{self.first_name} {self.last_name}" if self.first_name and self.last_name else "N/A"
        else:
            name = self.company_name or "N/A"
        return f"<User(id={self.id}, email={self.email}, name={name})>"
    
    @property
    def full_name(self):
        """Return full name based on user type."""
        if self.user_type == 'natural':
            if self.first_name and self.last_name:
                return f"{self.first_name} {self.last_name}"
            return self.first_name or self.last_name or "Usuario"
        else:
            return self.company_name or "Empresa"
    
    @property
    def display_name(self):
        """Return display name for UI."""
        return self.full_name

    # Role hierarchy system
    ROLE_HIERARCHY = {
        "user": 0,           # Usuario normal
        "manager": 1,        # Puede ver reportes
        "admin": 2,          # Puede gestionar usuarios
        "super_admin": 3     # Puede promover a admin
    }
    
    def get_role_level(self) -> int:
        """Get numeric level of user's role."""
        return self.ROLE_HIERARCHY.get(self.role, 0)
    
    def has_role_level(self, required_role: str) -> bool:
        """Check if user has required role level or higher."""
        user_level = self.get_role_level()
        required_level = self.ROLE_HIERARCHY.get(required_role, 0)
        return user_level >= required_level
    
    def is_admin(self) -> bool:
        """Check if user has admin privileges."""
        return self.role in ["admin", "super_admin"]
    
    def is_super_admin(self) -> bool:
        """Check if user has super admin privileges."""
        return self.role == "super_admin"
    
    def can_promote_to(self, target_role: str) -> bool:
        """Check if user can promote another user to target role."""
        if self.role == "super_admin":
            return target_role in ["user", "manager", "admin"]
        elif self.role == "admin":
            return target_role in ["user", "manager"]
        return False
    
    def get_total_orders(self) -> int:
        return len(self.orders)
    
    def get_total_spent(self) -> float:
        return sum(order.total for order in self.orders)
    
    def get_total_products_purchased(self) -> int:
        return sum(order.item_count for order in self.orders)
    