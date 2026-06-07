class AppError(Exception):
    def __init__(self, status_code: int, detail: str, code: str) -> None:
        self.status_code = status_code
        self.detail = detail
        self.code = code
        super().__init__(detail)


class CityNotFoundError(AppError):
    def __init__(self, slug: str) -> None:
        super().__init__(
            404, f"City '{slug}' not found or not published", "city_not_found"
        )


class CityLockedError(AppError):
    def __init__(self, slug: str) -> None:
        super().__init__(
            403, f"Access to city '{slug}' requires a purchase", "city_locked"
        )
