"""The explicit mark that an exception's message may reach a client."""


class ClientMessage:
    """Its message is written for clients: no submitted input, address, provider
    text or other internal detail. tests/test_client_safe_messages.py enforces the
    interpolation rule. Anything without this mark gets a fixed message instead."""


class ClientSafeError(ClientMessage, ValueError):
    """A rule was refused, in words a client may read."""
