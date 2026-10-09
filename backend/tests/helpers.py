"""Small helpers shared by several test modules."""


# func to register a user and return auth headers for them
def auth_headers(client, email: str, timezone: str | None = None) -> dict[str, str]:
    """Register `email` (optionally in `timezone`), log in, and return the auth header."""
    password = "correct-horse"
    body = {"email": email, "password": password, "full_name": "Test User"}
    if timezone:
        body["timezone"] = timezone
    client.post("/auth/register", json=body)
    token = client.post(
        "/auth/login", json={"email": email, "password": password}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
