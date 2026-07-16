import abc
import logging

logger = logging.getLogger(__name__)

_REGISTRY: dict[str, "DocumentParser"] = {}


class DocumentParser(abc.ABC):
    """Abstract base for all document parsers. Each parser handles one file type."""

    extension: str  # subclass must set this

    @abc.abstractmethod
    def parse(self, file_path: str) -> str:
        """Read the file at file_path and return its full text content."""
        ...

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "extension") and cls.extension:
            _REGISTRY[cls.extension.lower()] = cls()


def get_parser(extension: str) -> "DocumentParser":
    """Return the parser registered for the given file extension.
    Raises ValueError for unsupported extensions.
    """
    parser = _REGISTRY.get(extension.lower().lstrip("."))
    if parser is None:
        supported = ", ".join(sorted(_REGISTRY.keys()))
        raise ValueError(
            f"No parser registered for extension '{extension}'. "
            f"Supported: {supported}"
        )
    return parser


def supported_extensions() -> list[str]:
    return sorted(_REGISTRY.keys())


# Trigger __init_subclass__ registration for all concrete parsers
from apps.imports.parsers import registry as _  # noqa: F401
