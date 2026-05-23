"""
Обёртка над Nexus Mods API.
Используется для:
  - Получения детальной информации о моде (описание, версия, автор)
  - Получения списка файлов мода
  - Генерации ссылок на скачивание
"""

import json
import urllib.request
import urllib.error
from typing import Any
from dataclasses import dataclass


NEXUS_API_BASE = "https://api.nexusmods.com/v1"


@dataclass
class ModInfo:
    mod_id: int
    game: str
    name: str
    summary: str
    description: str
    version: str
    author: str
    category_id: int
    picture_url: str
    endorsement_count: int
    downloads_count: int
    created_timestamp: int
    updated_timestamp: int
    # Новое поле для списка всех изображений
    images: list[str] = None


@dataclass
class ModFile:
    file_id: int
    name: str
    version: str
    category_name: str  # MAIN, UPDATE, OPTIONAL, etc.
    size_kb: int
    description: str
    is_primary: bool


@dataclass
class DownloadLink:
    name: str
    short_name: str
    uri: str


class NexusApiError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class NexusApi:
    """Синхронный клиент Nexus API."""

    def __init__(self, api_key: str):
        self._api_key = api_key
        self.rate_limit_total = 0
        self.rate_limit_remaining = 0
        self.rate_limit_reset = ""

    def _request(self, endpoint: str) -> Any:
        """Выполняет GET-запрос к Nexus API."""
        if not self._api_key:
            raise NexusApiError("No API key configured", 401)

        url = f"{NEXUS_API_BASE}{endpoint}"
        req = urllib.request.Request(url)
        req.add_header("apikey", self._api_key)
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", "MO2-NexusCollector/1.0")

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                # Читаем лимиты из заголовков
                self.rate_limit_total = int(response.headers.get("x-rl-daily-limit", 0))
                self.rate_limit_remaining = int(response.headers.get("x-rl-daily-remaining", 0))
                self.rate_limit_reset = response.headers.get("x-rl-daily-reset", "")
                
                data = json.loads(response.read().decode("utf-8"))
                return data
        except urllib.error.HTTPError as e:
            # Даже при ошибке (например 429 Too Many Requests) лимиты могут быть в заголовках
            self.rate_limit_total = int(e.headers.get("x-rl-daily-limit", self.rate_limit_total))
            self.rate_limit_remaining = int(e.headers.get("x-rl-daily-remaining", self.rate_limit_remaining))
            
            body = e.read().decode("utf-8", errors="replace")
            raise NexusApiError(
                f"HTTP {e.code}: {body[:200]}",
                status_code=e.code,
            )
        except urllib.error.URLError as e:
            raise NexusApiError(f"Connection error: {e.reason}")

    def validate_key(self) -> bool:
        """Проверяет валидность API ключа."""
        try:
            self._request("/users/validate.json")
            return True
        except NexusApiError:
            return False

    def get_mod_info(self, game: str, mod_id: int) -> ModInfo:
        """Получает информацию о моде."""
        data = self._request(f"/games/{game}/mods/{mod_id}.json")
        
        # Попробуем получить список изображений
        # В основном эндпоинте /mods/{id}.json нет списка картинок.
        # Используем эндпоинт /mods/{id}/images.json
        images = []
        try:
            img_data = self._request(f"/games/{game}/mods/{mod_id}/images.json")
            if isinstance(img_data, list):
                # Формат: [{"URI": "...", "description": "..."}, ...]
                images = [item.get("URI") for item in img_data if item.get("URI")]
        except Exception:
            # Если не удалось получить список, используем основное изображение
            if data.get("picture_url"):
                images = [data.get("picture_url")]
        
        return ModInfo(
            mod_id=data.get("mod_id", mod_id),
            game=game,
            name=data.get("name", ""),
            summary=data.get("summary", ""),
            description=data.get("description", ""),
            version=data.get("version", ""),
            author=data.get("author", ""),
            category_id=data.get("category_id", 0),
            picture_url=data.get("picture_url", ""),
            endorsement_count=data.get("endorsement_count", 0),
            downloads_count=data.get("mod_downloads", 0),
            created_timestamp=data.get("created_timestamp", 0),
            updated_timestamp=data.get("updated_timestamp", 0),
            images=images
        )

    def get_mod_files(self, game: str, mod_id: int) -> list[ModFile]:
        """Получает список файлов мода."""
        data = self._request(f"/games/{game}/mods/{mod_id}/files.json")
        files = []
        for f in data.get("files", []):
            files.append(ModFile(
                file_id=f.get("file_id", 0),
                name=f.get("name", ""),
                version=f.get("version", ""),
                category_name=f.get("category_name", "MAIN"),
                size_kb=f.get("size_in_bytes", 0) // 1024,
                description=f.get("description", ""),
                is_primary=f.get("is_primary", False),
            ))
        return files

    def get_download_links(
        self, game: str, mod_id: int, file_id: int
    ) -> list[DownloadLink]:
        """
        Получает ссылки на скачивание.
        ВАЖНО: Для обычного API ключа (non-premium) Nexus API
        НЕ выдаёт прямые ссылки. Нужен Premium или nxm:// протокол.
        """
        try:
            data = self._request(
                f"/games/{game}/mods/{mod_id}/files/{file_id}/download_link.json"
            )
            links = []
            for item in data:
                links.append(DownloadLink(
                    name=item.get("name", ""),
                    short_name=item.get("short_name", ""),
                    uri=item.get("URI", ""),
                ))
            return links
        except NexusApiError as e:
            if e.status_code == 403:
                # Non-premium пользователь — нет доступа к прямым ссылкам
                raise NexusApiError(
                    "Direct download requires Nexus Premium. "
                    "Use 'Download with Nexus' button instead.",
                    403,
                )
            raise

    def get_game_domain(self, game_name: str) -> str:
        """
        Конвертирует имя игры из URL nexusmods
        в domain_name для API (обычно совпадают).
        """
        return game_name.lower().replace(" ", "")
