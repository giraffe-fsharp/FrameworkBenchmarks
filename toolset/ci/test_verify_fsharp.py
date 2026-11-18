import unittest
from html import escape
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from verify_fsharp import verify, verify_response


class VerifyResponseTests(unittest.TestCase):
    @patch("verify_fsharp.time.sleep")
    @patch("verify_fsharp.urlopen")
    def test_waits_for_container_proxy_to_accept_connections(self, open_url, sleep):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"message":"Hello, World!"}'
        response.headers = {"Content-Type": "application/json"}
        open_url.side_effect = [ConnectionResetError("starting"), response, response]
        verify(Path("frameworks/FSharp/giraffe"), "newtonsoft", "http://localhost:8080")
        sleep.assert_called_once_with(1)

    @patch("verify_fsharp.time.sleep")
    @patch("verify_fsharp.urlopen")
    def test_http_errors_fail_without_retrying(self, open_url, sleep):
        open_url.side_effect = HTTPError("http://localhost:8080/json", 500, "error", {}, None)
        with self.assertRaises(HTTPError):
            verify(Path("frameworks/FSharp/giraffe"), "newtonsoft", "http://localhost:8080")
        sleep.assert_not_called()

    def test_json_and_plaintext(self):
        verify_response("json", '{"message":"Hello, World!"}', "application/json", [])
        verify_response("plaintext", "Hello, World!", "text/plain; charset=utf-8", [])
        for body, content_type in [
            ('{"message":"wrong"}', "application/json"),
            ('{"message":"Hello, World!"}', "text/html"),
        ]:
            with self.subTest(body=body, content_type=content_type):
                with self.assertRaises(ValueError):
                    verify_response("json", body, content_type, [])

    def test_fortunes_require_correct_ids_order_and_html_escaping(self):
        fortunes = [(1, '<script>alert("test")</script>'), (0, "Additional fortune")]
        rows = [
            f"<tr><td>{id_}</td><td>{escape(message)}</td></tr>"
            for id_, message in fortunes
        ]
        verify_response("fortune", "<table>" + "".join(rows) + "</table>", "text/html", fortunes)
        for body in [
            "".join(reversed(rows)),
            rows[0],
            "".join(rows).replace("<td>1</td>", "<td>2</td>"),
            "".join(rows).replace(escape(fortunes[0][1]), fortunes[0][1]),
        ]:
            with self.subTest(body=body):
                with self.assertRaises(ValueError):
                    verify_response("fortune", body, "text/html", fortunes)


if __name__ == "__main__":
    unittest.main()
