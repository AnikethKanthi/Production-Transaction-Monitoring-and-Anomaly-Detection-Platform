"""Check the API, web page, and browser-to-API proxy using the standard library."""

import argparse
import json
from urllib.request import urlopen


def check(api_url: str, web_url: str) -> None:
    for endpoint in (f"{api_url}/health", f"{web_url}/api/health"):
        with urlopen(endpoint, timeout=10) as response:
            payload = json.load(response)
            if response.status != 200 or payload.get("status") != "ok":
                raise RuntimeError(f"Health check failed: {endpoint}")
        print(f"PASS {endpoint}")
    with urlopen(web_url, timeout=10) as response:
        html = response.read().decode()
        if response.status != 200 or '<div id="root"></div>' not in html:
            raise RuntimeError("React entry page is unavailable")
    print(f"PASS {web_url}")
    with urlopen(f"{web_url}/openapi.json", timeout=10) as response:
        if "/health" not in json.load(response).get("paths", {}):
            raise RuntimeError("Proxied API documentation schema is unavailable")
    print("PASS API documentation proxy")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--web-url", default="http://localhost:5173")
    args = parser.parse_args()
    check(args.api_url.rstrip("/"), args.web_url.rstrip("/"))
