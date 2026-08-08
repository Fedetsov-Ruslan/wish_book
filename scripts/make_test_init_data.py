"""
Dev-only helper: build a validly-signed Telegram WebApp `initData` string, so
the API can be exercised with curl/httpie before wiring up the real Mini App
in Telegram. Uses the exact HMAC-SHA256 scheme Telegram's client uses (and
that src/webapp/auth.py verifies), signed with your own BOT_TOKEN from
.env — this is not an auth bypass, just a stand-in for a real Telegram
client during local development.

Usage:
    python scripts/make_test_init_data.py <tg_id> [first_name] [start_param]

    curl -H "Authorization: tma $(python scripts/make_test_init_data.py 111 Alice)" \\
         http://localhost:8000/api/me
"""

import hashlib
import hmac
import json
import os
import sys
import time
from urllib.parse import quote, urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import config  # noqa: E402


def build_init_data(tg_id: int, first_name: str = "Test", start_param: str | None = None) -> str:
    fields = {
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": tg_id, "first_name": first_name}, separators=(",", ":")),
    }
    if start_param:
        fields["start_param"] = start_param

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields, quote_via=quote)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    tg_id_arg = int(sys.argv[1])
    first_name_arg = sys.argv[2] if len(sys.argv) > 2 else "Test"
    start_param_arg = sys.argv[3] if len(sys.argv) > 3 else None
    print(build_init_data(tg_id_arg, first_name_arg, start_param_arg))
