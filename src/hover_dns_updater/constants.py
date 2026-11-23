"""Default configuration and constants used by the Hover DNS updater."""

default_config = {
    # Your hover.com username and password
    "username": "ENV",
    "password": "ENV",
    "toptkey": "ENV",
    # Sign into hover.com and then go to: https://www.hover.com/api/domains/YOURDOMAIN.COM/dns
    # Look for the subdomain record(s) that you want to update and put its/their id(s) here.
    "dns_ids": ["ENV"],
    "logfile": "ENV",
    "run-as-service": False,
    "poll-time": 600,  # 10 minutes
}

API_BASE_URL = "https://www.hover.com/api"
SIGNIN_URL = "https://www.hover.com/signin"
TIMEOUT = (10, 30)
AUTH_CACHE_SECONDS = 2 * 60 * 60
