import httpx


def get_access_token(url: str, username: str, password: str) -> str:
    result = httpx.post(
        url=f"{url}/token",
        files={
            "username": (None, username),
            "password": (None, password),
        },
    )

    data = result.json()

    return data.get("access_token")
