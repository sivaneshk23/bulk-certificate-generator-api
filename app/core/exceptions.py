class CertificateGenerationError(Exception):
    """Raised when one certificate cannot be generated."""


class CertificateFileNotFoundError(Exception):
    """Raised when a completed certificate file is missing."""
