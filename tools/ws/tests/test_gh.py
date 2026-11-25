"""The real REST client against a local stand-in for api.github.com."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

import harness  # noqa: F401
from workstead import gh as G


class Handler(BaseHTTPRequestHandler):
    calls = []
    fail_once = {"n": 1}

    def log_message(self, *a):
        pass

    def reply(self, code, body, headers=None):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-RateLimit-Remaining", "4321")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        Handler.calls.append(("GET", self.path, self.headers.get("Authorization")))
        base = f"http://127.0.0.1:{self.server.server_port}"
        if self.path.startswith("/repos/a/b/issues?"):
            if "page=2" in self.path:
                return self.reply(200, [{"number": 3, "title": "c", "labels": [], "user": {"login": "z"},
                                         "pull_request": {}}])
            return self.reply(200, [{"number": 1, "title": "a", "labels": [{"name": "ws:task"}], "user": {"login": "x"},
                                     "assignees": [{"login": "q"}], "author_association": "OWNER"},
                                    {"number": 2, "title": "b", "labels": [], "user": {"login": "y"}}],
                              {"Link": f'<{base}/repos/a/b/issues?state=open&per_page=100&page=2>; rel="next"'})
        if self.path == "/repos/a/b/issues/9":
            if Handler.fail_once["n"]:
                Handler.fail_once["n"] -= 1
                return self.reply(502, {"message": "bad gateway"})
            return self.reply(200, {"number": 9, "title": "t", "labels": [], "user": {"login": "x"}})
        if self.path.startswith("/repos/a/b/commits/abc/check-runs"):
            return self.reply(200, {"check_runs": [{"name": "workstead-queue", "status": "in_progress"},
                                                   {"name": "Project checks", "status": "completed", "conclusion": "success"}]})
        if self.path == "/repos/a/b/commits/abc/status":
            return self.reply(200, {"state": "pending", "statuses": []})
        self.reply(404, {"message": "Not Found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        Handler.calls.append(("POST", self.path, body))
        if self.path == "/repos/a/b/issues/5/comments":
            return self.reply(201, {"id": 77, "body": body["body"], "user": {"login": "me"},
                                    "issue_url": "https://api.github.com/repos/a/b/issues/5"})
        self.reply(404, {"message": "Not Found"})


class RealClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.g = G.GitHub("a/b", tok="t0k", api=f"http://127.0.0.1:{cls.srv.server_port}")

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_pagination_and_normalisation(self):
        items = self.g.list_issues()
        self.assertEqual([i["number"] for i in items], [1, 2])  # the PR on page 2 is filtered out
        self.assertEqual(items[0]["labels"], ["ws:task"])
        self.assertEqual(items[0]["assignees"], ["q"])
        self.assertEqual(items[0]["author_association"], "OWNER")
        self.assertEqual(len(self.g.list_issues(include_prs=True)), 3)
        self.assertEqual(self.g.remaining, 4321)
        self.assertTrue(any(c[2] == "Bearer t0k" for c in Handler.calls if c[0] == "GET"))

    def test_retry_on_server_error(self):
        G.time.sleep, orig = (lambda s: None), G.time.sleep
        try:
            self.assertEqual(self.g.get_issue(9)["number"], 9)
        finally:
            G.time.sleep = orig

    def test_comment_and_checks(self):
        c = self.g.create_comment(5, "/claim node=x")
        self.assertEqual((c["id"], c["issue"], c["author"]), (77, 5, "me"))
        # Our own in-progress queue job is ignored; the project check passed.
        self.assertEqual(self.g.checks_state("abc"), "success")

    def test_errors_are_typed(self):
        with self.assertRaises(G.GitHubError) as e:
            self.g.get_pr(404)
        self.assertEqual(e.exception.status, 404)


if __name__ == "__main__":
    unittest.main()
