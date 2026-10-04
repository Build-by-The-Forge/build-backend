from app.api import identity as identity_api

VERIFICATION_SUBJECT = "Verify your BUILD email address"


def verify_email(client, email: str) -> None:
    """Verify a freshly registered account through the real API path.

    Tenant-scoped routes require a verified email (decision D4).
    """
    message = identity_api.service.email_sender.latest_to(email, VERIFICATION_SUBJECT)
    assert message is not None, f"no verification email sent to {email}"
    code = message.body.split("\n\n")[1]
    response = client.post("/identity/verify-email", json={"token": code})
    assert response.status_code == 200, response.text
