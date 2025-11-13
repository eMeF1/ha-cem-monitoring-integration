import aiohttp
import logging
from datetime import datetime

_LOGGER = logging.getLogger(__name__)

class CEMApiClient:
    def __init__(self, session, username, password):
        self._session = session
        self._username = username
        self._password = password
        self.token = None
        self.cookie = None
        self.valid_to = None

    async def authenticate(self):
        data = f"user={self._username}&pass={self._password}"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }

        try:
            async with self._session.post(
                "https://cemapi.unimonitor.eu/api?id=4",
                data=data,
                headers=headers
            ) as resp:
                if resp.status != 200:
                    _LOGGER.error("Authentication failed: %s", resp.status)
                    return False

                json_resp = await resp.json()
                self.token = json_resp.get("access_token")
                self.valid_to = int(json_resp.get("valid_to", 0))

                # Get cookie
                cookies = resp.cookies
                self.cookie = cookies.get("CEMAPI").value if "CEMAPI" in cookies else None

                _LOGGER.debug("Authenticated. Token: %s, Cookie: %s", self.token, self.cookie)
                return self.token is not None and self.cookie is not None

        except Exception as e:
            _LOGGER.exception("Exception during authentication: %s", e)
            return False

    def is_token_valid(self):
        if not self.valid_to:
            return False

        now = datetime.utcnow().timestamp() * 1000  # valid_to is in ms
        return self.valid_to > now