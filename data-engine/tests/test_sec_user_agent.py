"""La via live de SEC (data.sec.gov) exige User-Agent declarado con contacto;
bloquea placeholders tipo example.com con 403 - eso rompia toda ingesta sin
snapshot local (verificado en prod 25/9: example.com -> 403, este UA -> 200)."""

from app.core.config import get_settings
from app.services.connectors.sec import SECClient


def test_default_sec_user_agent_is_not_a_blocked_placeholder():
    settings = get_settings()
    assert "example.com" not in settings.sec_user_agent
    assert "@" in settings.sec_user_agent  # SEC pide contacto en el UA


def test_client_sends_user_agent():
    client = SECClient()
    assert client.headers["User-Agent"] == client.user_agent
    assert "example.com" not in client.headers["User-Agent"]
