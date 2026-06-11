#!/usr/bin/env python3
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Warm-pool entrypoint: wait for the dispatcher's {session_id, work_id} POST, then exec ant."""
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("DISPATCH_PORT", "8080"))
MAX_IDLE = os.environ.get("ANT_MAX_IDLE", "60s")
GCS_MOUNT = os.environ.get("GCS_MOUNT", "/mnt/gcs")
SESSION_OUTPUTS = os.environ.get("SESSION_OUTPUTS", "/mnt/session/outputs")
ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,128}$")


class Handler(BaseHTTPRequestHandler):
    """Accept exactly one validated {session_id, work_id} POST from the dispatcher."""

    def do_POST(self):  # noqa: N802
        """Validate the dispatch payload and store it on the server for main() to read."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length))
            session_id, work_id = body["session_id"], body["work_id"]
            if not (ID_RE.match(session_id) and ID_RE.match(work_id)):
                raise ValueError("invalid id")
        except Exception:
            self.send_response(400)
            self.end_headers()
            return
        self.send_response(202)
        self.end_headers()
        self.server.dispatch = {"session_id": session_id, "work_id": work_id}

    def log_message(self, *_):
        """Suppress the stdlib per-request access log."""
        pass


def main():
    """Block until dispatched, point /mnt/session/outputs at GCS, then exec ant beta:worker run."""
    httpd = HTTPServer(("0.0.0.0", PORT), Handler)
    httpd.dispatch = None
    while httpd.dispatch is None:
        httpd.handle_request()

    payload = httpd.dispatch
    env = os.environ.copy()
    env["ANTHROPIC_SESSION_ID"] = payload["session_id"]
    env["ANTHROPIC_WORK_ID"] = payload["work_id"]

    # Point /mnt/session/outputs at a per-session prefix in the GCS FUSE mount.
    if os.path.isdir(GCS_MOUNT):
        session_dir = os.path.join(GCS_MOUNT, payload["session_id"])
        os.makedirs(session_dir, exist_ok=True)
        if os.path.lexists(SESSION_OUTPUTS):
            os.remove(SESSION_OUTPUTS)
        os.symlink(session_dir, SESSION_OUTPUTS)
    else:
        os.makedirs(SESSION_OUTPUTS, exist_ok=True)

    argv = [
        "ant", "beta:worker", "run",
        "--workdir", "/workspace",
        "--max-idle", MAX_IDLE,
        "--log-format", "json",
    ]
    print(json.dumps({"event": "exec", "argv": argv, "session_id": payload["session_id"]}),
          file=sys.stderr)
    os.execvpe(argv[0], argv, env)


if __name__ == "__main__":
    main()
