from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse


PROTOCOL_SCHEME = "apson-ytdownloader"
MAX_EXTERNAL_URL_LENGTH = 4096


class ExternalActivationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ExternalActivation:
    url: str | None = None
    auto_analyze: bool = True

    @property
    def is_url_request(self) -> bool:
        return self.url is not None

    @classmethod
    def from_protocol_uri(cls, uri: str) -> "ExternalActivation":
        if len(uri) > MAX_EXTERNAL_URL_LENGTH + 256:
            raise ExternalActivationError("Żądanie z przeglądarki jest zbyt długie.")
        parsed = urlparse(uri.strip())
        action = parsed.netloc.lower() or parsed.path.strip("/").lower()
        if parsed.scheme.lower() != PROTOCOL_SCHEME or action != "add":
            raise ExternalActivationError("Nieobsługiwana akcja protokołu aplikacji.")
        values = parse_qs(parsed.query, keep_blank_values=True)
        if set(values) != {"url"} or parsed.fragment:
            raise ExternalActivationError("Żądanie zawiera nieobsługiwane parametry.")
        urls = values.get("url", [])
        if len(urls) != 1:
            raise ExternalActivationError("Żądanie musi zawierać dokładnie jeden adres URL.")
        return cls(cls.validate_web_url(urls[0]), auto_analyze=True)

    @classmethod
    def from_argv(cls, argv: list[str]) -> "ExternalActivation | None":
        candidate: str | None = None
        for index, argument in enumerate(argv[1:], start=1):
            if argument == "--protocol":
                if index + 1 >= len(argv):
                    raise ExternalActivationError("Brak URI po parametrze --protocol.")
                candidate = argv[index + 1]
                break
            if argument == "--add-url":
                if index + 1 >= len(argv):
                    raise ExternalActivationError("Brak URL po parametrze --add-url.")
                return cls(cls.validate_web_url(argv[index + 1]), auto_analyze=True)
            if argument.lower().startswith(f"{PROTOCOL_SCHEME}:"):
                candidate = argument
                break
        return cls.from_protocol_uri(candidate) if candidate is not None else None

    @staticmethod
    def validate_web_url(url: str) -> str:
        normalized = url.strip()
        if not normalized or len(normalized) > MAX_EXTERNAL_URL_LENGTH:
            raise ExternalActivationError("Adres URL jest pusty albo zbyt długi.")
        if any(ord(character) < 32 for character in normalized):
            raise ExternalActivationError("Adres URL zawiera niedozwolone znaki sterujące.")
        try:
            parsed = urlparse(normalized)
            hostname = parsed.hostname
            parsed.port
        except ValueError as error:
            raise ExternalActivationError("Adres URL ma nieprawidłową składnię.") from error
        if parsed.scheme.lower() not in {"http", "https"} or not hostname:
            raise ExternalActivationError("Dozwolone są wyłącznie pełne adresy HTTP/HTTPS.")
        if parsed.username or parsed.password:
            raise ExternalActivationError("Adresy zawierające dane logowania są niedozwolone.")
        return normalized
