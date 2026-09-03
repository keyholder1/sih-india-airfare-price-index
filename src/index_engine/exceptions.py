"""Exceptions raised by the index engine."""


class IndexEngineError(Exception):
    """Base class for all index engine errors."""


class ConfigurationError(IndexEngineError):
    """Raised when the engine is configured inconsistently."""


class InsufficientDataError(IndexEngineError):
    """Raised when there is not enough valid data to compute any index."""


class SchemaError(IndexEngineError):
    """Raised when input observations do not match the expected schema."""
