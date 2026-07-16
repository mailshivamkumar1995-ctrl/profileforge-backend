from apps.imports.parsers import DocumentParser


class TxtParser(DocumentParser):
    extension = "txt"

    def parse(self, file_path: str) -> str:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
