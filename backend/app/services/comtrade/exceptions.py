class ComtradeError(Exception):
    """Base exception class for COMTRADE errors"""
    pass

class ComtradeFormatError(ComtradeError):
    """Raised when there are format-related errors"""
    pass

class CfgValidationError(ComtradeError):
    """Raised when CFG file validation fails"""
    pass

class DatReaderError(ComtradeError):
    """Raised when DAT file reading fails"""
    pass

class FileEncodingError(ComtradeError):
    """Raised when file encoding issues occur"""
    pass

class TimestampError(ComtradeError):
    """Raised when timestamp processing fails"""
    pass