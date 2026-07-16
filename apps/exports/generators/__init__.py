import abc

_REGISTRY: dict[str, "DocumentGenerator"] = {}


class DocumentGenerator(abc.ABC):
    """Abstract base for all document generators. Each subclass handles one output format."""

    format: str  # subclass must set this

    @abc.abstractmethod
    def generate(self, html_content: str, profile_data: dict | None = None, template_slug: str | None = None) -> bytes:
        """Generate and return document bytes from HTML content."""
        ...

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "format") and cls.format:
            _REGISTRY[cls.format.lower()] = cls()


def get_generator(fmt: str) -> "DocumentGenerator":
    """Return the generator registered for the given format (pdf/docx).
    Raises ValueError for unsupported formats.
    """
    generator = _REGISTRY.get(fmt.lower())
    if generator is None:
        supported = ", ".join(sorted(_REGISTRY.keys()))
        raise ValueError(
            f"No generator registered for format '{fmt}'. Supported: {supported}"
        )
    return generator


def supported_formats() -> list[str]:
    return sorted(_REGISTRY.keys())
