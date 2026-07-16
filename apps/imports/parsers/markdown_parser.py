import re
from apps.imports.parsers import DocumentParser


class MarkdownParser(DocumentParser):
    extension = "md"

    _PATTERNS = [
        (re.compile(r"^#{1,6}\s+", re.MULTILINE), ""),   # headings
        (re.compile(r"\*\*(.+?)\*\*"), r"\1"),            # bold
        (re.compile(r"\*(.+?)\*"), r"\1"),                 # italic
        (re.compile(r"`{1,3}([^`]+)`{1,3}"), r"\1"),      # code
        (re.compile(r"!\[.*?\]\(.*?\)"), ""),              # images
        (re.compile(r"\[(.+?)\]\(.*?\)"), r"\1"),          # links
        (re.compile(r"^\s*[-*+]\s+", re.MULTILINE), ""),  # unordered list markers
        (re.compile(r"^\s*\d+\.\s+", re.MULTILINE), ""),  # ordered list markers
        (re.compile(r"^>+\s?", re.MULTILINE), ""),        # blockquotes
        (re.compile(r"[-]{3,}|[=]{3,}"), ""),             # hr / setext headings
        (re.compile(r"\\\|"), " "),                        # escaped pipe \| -> space (removes \ artifact)
        (re.compile(r"\|"), " "),                          # remaining table pipes
        (re.compile(r"\\\s"), " "),                        # backslash + whitespace -> space (cleans trailing \<space>)
    ]

    def parse(self, file_path: str) -> str:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()

        for pattern, replacement in self._PATTERNS:
            text = pattern.sub(replacement, text)

        # Collapse excessive blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
