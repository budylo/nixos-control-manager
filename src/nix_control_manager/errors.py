class NcmError(Exception):
    """Base error safe to present to a user."""


class ValidationError(NcmError):
    """The managed state is invalid."""


class StorageError(NcmError):
    """A managed file could not be read or written safely."""


class TransactionError(NcmError):
    """A journaled configuration transaction could not complete safely."""
