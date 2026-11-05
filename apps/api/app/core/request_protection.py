import asyncio

from starlette.responses import JSONResponse


class RequestProtectionMiddleware:
    def __init__(self, app, max_bytes=65536, body_timeout=5):
        self.app, self.max_bytes, self.body_timeout = app, max_bytes, body_timeout

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def secure_send(message):
            if message["type"] == "http.response.start":
                message = dict(message)
                message["headers"] = list(message.get("headers", [])) + [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                    (b"cache-control", b"no-store"),
                ]
                if scope["path"] not in {"/docs", "/redoc"}:
                    message["headers"].append(
                        (
                            b"content-security-policy",
                            b"default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
                        )
                    )
                if scope["scheme"] == "https":
                    message["headers"].append((b"strict-transport-security", b"max-age=31536000"))
            await send(message)

        async def reject(status, code):
            response = JSONResponse(
                {"error": {"code": code, "message": code.replace("_", " ")}}, status_code=status
            )
            await response(scope, receive, secure_send)

        headers = scope.get("headers", [])
        lengths = [value for key, value in headers if key == b"content-length"]
        if len(lengths) > 1 or (lengths and not lengths[0].isdigit()):
            return await reject(400, "invalid_content_length")
        if lengths and any(key == b"transfer-encoding" for key, _ in headers):
            return await reject(400, "ambiguous_body_framing")
        if lengths and len(lengths[0]) > 10:
            return await reject(413, "request_too_large")
        if lengths and int(lengths[0]) > self.max_bytes:
            return await reject(413, "request_too_large")
        if any(k == b"content-encoding" and v.lower() != b"identity" for k, v in headers):
            return await reject(415, "unsupported_content_encoding")

        async def read_body():
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return None
                chunk = message.get("body", b"")
                if len(body) + len(chunk) > self.max_bytes:
                    raise OverflowError
                body.extend(chunk)
                if not message.get("more_body", False):
                    return bytes(body)

        try:
            body = await asyncio.wait_for(read_body(), self.body_timeout)
        except OverflowError:
            return await reject(413, "request_too_large")
        except TimeoutError:
            return await reject(408, "request_body_timeout")
        if body is None:
            return
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, secure_send)
