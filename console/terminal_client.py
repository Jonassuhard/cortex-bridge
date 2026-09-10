"""Small, deliberately bounded HTTP client for the local terminal backend."""

import ipaddress
import json
from urllib import error, parse, request


class ApiError(Exception):
    def __init__(self, status, message, uncertain=False):
        super().__init__(message)
        self.status = status
        self.message = message
        self.uncertain = uncertain


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ApiClient:
    _MAX_RESPONSE_BYTES = 4 * 1024 * 1024

    def __init__(self, base_url="http://127.0.0.1:8420", timeout=10.0):
        parsed = parse.urlsplit(base_url)
        if (
            parsed.scheme != "http"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("base_url must be a root loopback http URL")
        try:
            if not ipaddress.ip_address(parsed.hostname).is_loopback:
                raise ValueError("base_url host must be loopback")
            port = parsed.port
        except ValueError as exc:
            raise ValueError("base_url must have a valid loopback host and port") from exc
        if port is not None and not 1 <= port <= 65535:
            raise ValueError("base_url must have a valid port")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("timeout must be positive")
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self._opener = request.build_opener(_NoRedirect(), request.ProxyHandler({}))

    def request(self, method, path, body=None, query=None):
        if not isinstance(method, str) or not method:
            raise ValueError("method is required")
        if not isinstance(path, str) or not path.startswith("/api/"):
            raise ValueError("path must begin with /api/")
        parsed_path = parse.urlsplit(path)
        if parsed_path.path != path or parsed_path.netloc or parsed_path.query or parsed_path.fragment:
            raise ValueError("path must not contain a URL, query, or fragment")
        self._validate_path_segments(path)

        url = self.base_url + path
        if query:
            url += "?" + parse.urlencode(query, doseq=True)
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        operation = method.upper()
        try:
            response = self._opener.open(request.Request(url, data=data, headers=headers, method=operation), timeout=self.timeout)
            with response:
                return self._decode_response(response, response.status)
        except error.HTTPError as exc:
            with exc:
                message = self._error_message(exc, exc.code)
            raise ApiError(exc.code, message) from None
        except (error.URLError, TimeoutError, OSError) as exc:
            uncertain = operation in {"POST", "PUT", "PATCH", "DELETE"}
            raise ApiError(None, str(getattr(exc, "reason", exc)), uncertain) from None

    @staticmethod
    def _validate_path_segments(path):
        if "\\" in path:
            raise ValueError("path must not contain ambiguous separators")
        segments = path.split("/")[2:]
        for index, segment in enumerate(segments):
            if not segment:
                if index != len(segments) - 1:
                    raise ValueError("path must not contain ambiguous separators")
                continue
            decoded = segment
            while True:
                unquoted = parse.unquote(decoded)
                if unquoted == decoded:
                    break
                decoded = unquoted
            if decoded in (".", "..") or "/" in decoded or "\\" in decoded:
                raise ValueError("path must not contain traversal or encoded separators")

    def _decode_response(self, response, status):
        raw = response.read(self._MAX_RESPONSE_BYTES + 1)
        if len(raw) > self._MAX_RESPONSE_BYTES:
            raise ApiError(status, "response exceeds 4 MiB limit")
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(status, "response is not valid UTF-8 JSON") from None
        if not isinstance(result, (dict, list)):
            raise ApiError(status, "response JSON must be an object or array")
        return result

    def _error_message(self, response, status):
        try:
            result = self._decode_response(response, status)
        except ApiError:
            return "HTTP %d" % status
        if isinstance(result, dict) and "detail" in result:
            detail = result["detail"]
            if isinstance(detail, str):
                return detail
            return json.dumps(detail, ensure_ascii=False, separators=(",", ":"))
        return "HTTP %d" % status
