class AppError(Exception):
    """Base class for all application errors."""
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

class ServiceError(AppError):
    """Raised when an internal service fails."""
    def __init__(self, message: str):
        super().__init__(message, status_code=500)

class ExternalServiceError(AppError):
    """Raised when an external API (OpenAI, Pinecone, etc.) fails."""
    def __init__(self, message: str):
        super().__init__(message, status_code=502)

class ValidationError(AppError):
    """Raised when input validation fails."""
    def __init__(self, message: str):
        super().__init__(message, status_code=400)

class NotFoundError(AppError):
    """Raised when a requested resource is not found."""
    def __init__(self, message: str):
        super().__init__(message, status_code=404)
