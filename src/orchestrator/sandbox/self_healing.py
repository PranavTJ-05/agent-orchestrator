from dataclasses import dataclass
from enum import Enum


class ErrorType(Enum):
    SYNTAX = "syntax"
    RUNTIME = "runtime"
    LOGIC = "logic"
    IMPORT = "import"
    TIMEOUT = "timeout"
    MEMORY = "memory"
    PERMISSION = "permission"
    UNKNOWN = "unknown"


@dataclass
class ErrorInfo:
    error_type: ErrorType
    message: str
    line_number: int | None = None
    fix_suggestion: str | None = None


class ErrorClassifier:
    SYNTAX_PATTERNS = [
        "SyntaxError",
        "invalid syntax",
        "expected",
        "EOL",
        "EOF",
    ]

    RUNTIME_PATTERNS = [
        "NameError",
        "TypeError",
        "ValueError",
        "IndexError",
        "KeyError",
        "AttributeError",
        "ZeroDivisionError",
        "AssertionError",
    ]

    IMPORT_PATTERNS = [
        "ImportError",
        "ModuleNotFoundError",
        "No module named",
    ]

    TIMEOUT_PATTERNS = [
        "timeout",
        "timed out",
        "TimeoutError",
    ]

    MEMORY_PATTERNS = [
        "MemoryError",
        "out of memory",
    ]

    PERMISSION_PATTERNS = [
        "PermissionError",
        "Access denied",
        "Permission denied",
    ]

    @classmethod
    def classify(cls, error_message: str) -> ErrorInfo:
        error_msg = error_message.lower()

        for pattern in cls.SYNTAX_PATTERNS:
            if pattern.lower() in error_msg:
                return ErrorInfo(
                    error_type=ErrorType.SYNTAX,
                    message=error_message,
                    fix_suggestion="Check for missing colons, parentheses, or indentation errors."
                )

        for pattern in cls.IMPORT_PATTERNS:
            if pattern.lower() in error_msg:
                return ErrorInfo(
                    error_type=ErrorType.IMPORT,
                    message=error_message,
                    fix_suggestion="Verify the module is installed or the import path is correct."
                )

        for pattern in cls.TIMEOUT_PATTERNS:
            if pattern.lower() in error_msg:
                return ErrorInfo(
                    error_type=ErrorType.TIMEOUT,
                    message=error_message,
                    fix_suggestion="Optimize the code to run faster or increase timeout."
                )

        for pattern in cls.MEMORY_PATTERNS:
            if pattern.lower() in error_msg:
                return ErrorInfo(
                    error_type=ErrorType.MEMORY,
                    message=error_message,
                    fix_suggestion="Process data in smaller chunks or optimize memory usage."
                )

        for pattern in cls.PERMISSION_PATTERNS:
            if pattern.lower() in error_msg:
                return ErrorInfo(
                    error_type=ErrorType.PERMISSION,
                    message=error_message,
                    fix_suggestion="Check file permissions or run with appropriate access."
                )

        for pattern in cls.RUNTIME_PATTERNS:
            if pattern.lower() in error_msg:
                return ErrorInfo(
                    error_type=ErrorType.RUNTIME,
                    message=error_message,
                    fix_suggestion="Check variable types and ensure proper error handling."
                )

        return ErrorInfo(
            error_type=ErrorType.UNKNOWN,
            message=error_message,
            fix_suggestion="Review the error message and fix accordingly."
        )


def extract_line_number(error_message: str) -> int | None:
    import re
    match = re.search(r"line (\d+)", error_message)
    if match:
        return int(match.group(1))
    return None


__all__ = ["ErrorType", "ErrorInfo", "ErrorClassifier", "extract_line_number"]