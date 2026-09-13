"""Contracts for the terminal's bounded loopback HTTP client."""

import json
import os
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from terminal_client import ApiClient, ApiError


class _Server:
    def __init__(self, responder):
        self.requests = []
        self._responder = responder
        parent = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                parent._respond(self)

            def do_POST(self):
                parent._respond(self)

            def log_message(self, format, *args):
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever)

    @property
    def base_url(self):
        return "http://127.0.0.1:%d" % self._server.server_port

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._server.shutdown()
        self._thread.join()
        self._server.server_close()

    def _respond(self, handler):
        length = int(handler.headers.get("Content-Length", "0"))
        self.requests.append(
            {
                "method": handler.command,
                "path": handler.path,
                "headers": dict(handler.headers),
                "body": handler.rfile.read(length),
            }
        )
        response = self._responder(handler)
        if len(response) == 2:
            status, body = response
            headers = {}
        else:
            status, body, headers = response
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        for name, value in headers.items():
            handler.send_header(name, value)
        handler.end_headers()
        try:
            handler.wfile.write(body)
        except BrokenPipeError:
            pass


class TerminalClientTests(unittest.TestCase):
    def test_get_returns_a_json_dictionary(self):
        with _Server(lambda _: (200, b'{"ok":true}')) as server:
            result = ApiClient(server.base_url).request("GET", "/api/status")

        self.assertEqual({"ok": True}, result)

    def test_get_returns_a_json_list(self):
        with _Server(lambda _: (200, b'[{"id":"one"}]')) as server:
            result = ApiClient(server.base_url).request("GET", "/api/runs")

        self.assertEqual([{"id": "one"}], result)

    def test_post_sends_exact_utf8_json_headers_and_encoded_query(self):
        with _Server(lambda _: (200, b'{"id":"run-1"}')) as server:
            result = ApiClient(server.base_url).request(
                "POST",
                "/api/chat/send",
                {"text": "été"},
                {"tag": ["first", "second"], "q": "été"},
            )
            received = server.requests[0]

        self.assertEqual({"id": "run-1"}, result)
        self.assertEqual("POST", received["method"])
        self.assertEqual(
            "/api/chat/send?tag=first&tag=second&q=%C3%A9t%C3%A9", received["path"]
        )
        self.assertEqual(b'{"text":"\xc3\xa9t\xc3\xa9"}', received["body"])
        self.assertEqual("application/json", received["headers"]["Accept"])
        self.assertEqual(
            "application/json; charset=utf-8", received["headers"]["Content-Type"]
        )

    def test_constructor_rejects_non_root_or_non_loopback_urls(self):
        invalid_urls = (
            "https://127.0.0.1:8420",
            "http://localhost:8420",
            "http://192.168.1.2:8420",
            "http://user:pass@127.0.0.1:8420",
            "http://127.0.0.1:8420/api",
            "http://127.0.0.1:8420/?q=1",
            "http://127.0.0.1:8420/#fragment",
            "http://127.0.0.1:0",
            "http://127.0.0.1:65536",
        )

        for url in invalid_urls:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    ApiClient(url)

    def test_constructor_exposes_the_validated_base_url(self):
        client = ApiClient("http://127.0.0.1:8420/")

        self.assertEqual("http://127.0.0.1:8420", client.base_url)

    def test_request_refuses_non_api_paths_and_embedded_url_parts(self):
        client = ApiClient()

        for path in ("/status", "/api", "/api/status?override=1", "/api/status#part"):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    client.request("GET", path)

    def test_request_rejects_traversal_and_ambiguous_separators_before_network(self):
        with _Server(lambda _: (200, b'{"unexpected":true}')) as server:
            client = ApiClient(server.base_url)
            for path in (
                "/api/../x",
                "/api/%2e%2e/x",
                "/api/%252e%252e/x",
                "/api/a%2fb",
                "/api/a%5cb",
                "/api/a\\b",
                "/api//x",
            ):
                with self.subTest(path=path):
                    with self.assertRaises(ValueError):
                        client.request("GET", path)

            self.assertEqual([], server.requests)

    def test_constructor_rejects_boolean_timeout(self):
        for timeout in (True, False):
            with self.subTest(timeout=timeout):
                with self.assertRaises(ValueError):
                    ApiClient(timeout=timeout)

    def test_redirect_is_reported_without_following_it(self):
        with _Server(
            lambda _: (302, b'{"detail":"follow denied"}', {"Location": "/api/other"})
        ) as server:
            with self.assertRaises(ApiError) as raised:
                ApiClient(server.base_url).request("GET", "/api/redirect")

        self.assertEqual(302, raised.exception.status)
        self.assertEqual("follow denied", raised.exception.message)

    def test_http_error_status_and_string_detail_are_retained(self):
        for status in (403, 409, 422, 503):
            with self.subTest(status=status), _Server(
                lambda _, code=status: (code, b'{"detail":"blocked"}')
            ) as server:
                with self.assertRaises(ApiError) as raised:
                    ApiClient(server.base_url).request("GET", "/api/fail")

            self.assertEqual(status, raised.exception.status)
            self.assertEqual("blocked", raised.exception.message)
            self.assertFalse(raised.exception.uncertain)

    def test_http_error_serializes_dictionary_detail(self):
        with _Server(lambda _: (422, b'{"detail":{"field":"text"}}')) as server:
            with self.assertRaises(ApiError) as raised:
                ApiClient(server.base_url).request("POST", "/api/chat/send", {"text": "x"})

        self.assertEqual(422, raised.exception.status)
        self.assertEqual('{"field":"text"}', raised.exception.message)

    def test_invalid_json_is_an_api_error(self):
        with _Server(lambda _: (200, b"not json")) as server:
            with self.assertRaises(ApiError) as raised:
                ApiClient(server.base_url).request("GET", "/api/status")

        self.assertEqual(200, raised.exception.status)
        self.assertIn("valid UTF-8 JSON", raised.exception.message)

    def test_response_over_four_mebibytes_is_rejected(self):
        oversized = b" " * (4 * 1024 * 1024 + 1)
        with _Server(lambda _: (200, oversized)) as server:
            with self.assertRaises(ApiError) as raised:
                ApiClient(server.base_url).request("GET", "/api/large")

        self.assertEqual(200, raised.exception.status)
        self.assertIn("4 MiB", raised.exception.message)

    def test_post_timeout_is_uncertain_and_attempted_once(self):
        def delayed_response(_):
            time.sleep(0.15)
            return 200, b'{"ok":true}'

        with _Server(delayed_response) as server:
            with self.assertRaises(ApiError) as raised:
                ApiClient(server.base_url, timeout=0.02).request(
                    "POST", "/api/chat/send", {"text": "synthetic"}
                )
            time.sleep(0.2)
            request_count = len(server.requests)

        self.assertIsNone(raised.exception.status)
        self.assertTrue(raised.exception.uncertain)
        self.assertEqual(1, request_count)

    def test_environment_proxy_is_not_used(self):
        old_proxy = os.environ.get("http_proxy")
        os.environ["http_proxy"] = "http://127.0.0.1:1"
        try:
            with _Server(lambda _: (200, b'{"ok":true}')) as server:
                result = ApiClient(server.base_url).request("GET", "/api/status")
        finally:
            if old_proxy is None:
                del os.environ["http_proxy"]
            else:
                os.environ["http_proxy"] = old_proxy

        self.assertEqual({"ok": True}, result)


if __name__ == "__main__":
    unittest.main()
