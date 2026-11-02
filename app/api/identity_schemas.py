"""The identity routes' request bodies, as the contract describes them.

Types and required fields only. What a value must be, such as a password's length or an
email's format, stays in the domain, so its refusal keeps its own message. A blank field
is still that rule's to refuse: a blank password at sign-in is wrong credentials.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictBool


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(_Body):
    email: str
    password: str


class AuthenticateRequest(_Body):
    email: str
    password: str
    # sessions.device_id is 36 characters, and the ID is stored and returned.
    device_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9._:-]{1,36}$")] | None = None
    user_agent: Annotated[str, Field(max_length=512)] | None = None


class RefreshRequest(_Body):
    refresh_token: str


class TokenRequest(_Body):
    token: str


class EmailRequest(_Body):
    email: str


class ResetPasswordRequest(_Body):
    token: str
    password: str


class ChangePasswordRequest(_Body):
    current_password: str
    new_password: str
    revoke_other_sessions: StrictBool = True
