from email.message import Message
from typing import Tuple
from urllib.request import HTTPRedirectHandler, Request, build_opener


class _RejectRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(request: Request, max_bytes: int, timeout: int = 30) -> Tuple[str, Message]:
    """Fetch `request` without following redirects, raising `ValueError` past `max_bytes`"""
    with build_opener(_RejectRedirectHandler()).open(request, timeout=timeout) as response:
        body = response.read(max_bytes + 1)
        headers = response.headers
    if len(body) > max_bytes:
        raise ValueError(f"{request.full_url}: response exceeds {max_bytes} bytes")
    return body.decode("utf-8"), headers
