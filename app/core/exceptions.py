from typing import Any

from fastapi import HTTPException, status


class FarmaException(HTTPException):
    """Base exception for FarmaPlus application."""

    def __init__(
        self,
        status_code: int,
        detail: str,
        headers: dict[str, Any] | None = None,
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)


class UserNotFoundException(FarmaException):
    """Exception raised when user is not found."""

    def __init__(self, detail: str = "Usuario no encontrado"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class ProductNotFoundException(FarmaException):
    """Exception raised when product is not found."""

    def __init__(self, detail: str = "Producto no encontrado"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class OrderNotFoundException(FarmaException):
    """Exception raised when order is not found."""

    def __init__(self, detail: str = "Pedido no encontrado"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class InsufficientStockException(FarmaException):
    """Exception raised when product has insufficient stock."""

    def __init__(self, detail: str = "Stock insuficiente"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class InvalidCredentialsException(FarmaException):
    """Exception raised for invalid login credentials."""

    def __init__(self, detail: str = "Email o contraseña incorrectos"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"}
        )


class UserAlreadyExistsException(FarmaException):
    """Exception raised when trying to create a user that already exists."""

    def __init__(self, detail: str = "El usuario ya existe"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class EmailNotVerifiedException(FarmaException):
    """Exception raised when user email is not verified."""

    def __init__(self, detail: str = "Email no verificado"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class PaymentProcessingException(FarmaException):
    """Exception raised when payment processing fails."""

    def __init__(self, detail: str = "Error al procesar el pago"):
        super().__init__(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=detail)


class CartEmptyException(FarmaException):
    """Exception raised when cart is empty."""

    def __init__(self, detail: str = "El carrito está vacío"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class PrescriptionRequiredException(FarmaException):
    """Exception raised when prescription is required for a product."""

    def __init__(self, detail: str = "Este producto requiere receta médica"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class FileUploadException(FarmaException):
    """Exception raised when file upload fails."""

    def __init__(self, detail: str = "Error al subir archivo"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class InvalidFileTypeException(FarmaException):
    """Exception raised when file type is not allowed."""

    def __init__(self, detail: str = "Tipo de archivo no permitido"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
