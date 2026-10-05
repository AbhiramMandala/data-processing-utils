"""Python data-processing utilities (OOP + generators).

Covers: data cleansing, file validation, JSON/XML integration,
log analysis, and automated file processing.

All I/O is streaming (generators) so large files never load fully
into memory. Standard library only.
"""
from .cleaning import DataCleaner
from .validation import FileValidator, ValidationResult
from .formats import JsonXmlConverter
from .log_analysis import LogAnalyzer, LogRecord
from .processor import FileProcessor, ProcessResult

__all__ = [
    "DataCleaner",
    "FileValidator",
    "ValidationResult",
    "JsonXmlConverter",
    "LogAnalyzer",
    "LogRecord",
    "FileProcessor",
    "ProcessResult",
]
