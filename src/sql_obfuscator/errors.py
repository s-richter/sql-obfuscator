class ObfuscatorError(Exception):
    """Base application error."""


class InputFileError(ObfuscatorError):
    """Raised when the input file cannot be read."""


class ParseScriptError(ObfuscatorError):
    """Raised when SQL parsing fails."""
