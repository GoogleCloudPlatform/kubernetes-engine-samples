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

"""Smoke test: create a session against the self-hosted env, send a prompt, print events until end_turn."""
# /// script
# requires-python = ">=3.11"
# dependencies = ["anthropic>=0.104.1"]
# ///
import argparse
import json
import os
import time

import anthropic


def parse_args():
    """Parse CLI flags, with defaults from the matching env vars."""
    p = argparse.ArgumentParser()
    p.add_argument("--environment-id", default=os.environ.get("ANTHROPIC_ENVIRONMENT_ID"))
    p.add_argument("--agent-id", default=os.environ.get("ANTHROPIC_AGENT_ID"),
                   help="Reuse an existing agent instead of creating one")
    p.add_argument("--model", default=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"))
    p.add_argument("--prompt", default=os.environ.get(
        "PROMPT",
        "Run `uname -a && hostname && head -3 /etc/os-release` and tell me what sandbox you are in."))
    p.add_argument("--timeout", type=int, default=120)
    return p.parse_args()


def main():
    """Create a session bound to the self-hosted environment, send one prompt, print events until end_turn."""
    args = parse_args()
    if not args.environment_id:
        raise SystemExit("ANTHROPIC_ENVIRONMENT_ID not set (source .env)")

    client = anthropic.Anthropic()

    if args.agent_id:
        agent_id = args.agent_id
    else:
        agent = client.beta.agents.create(
            name="gke-sandbox-probe",
            model=args.model,
            system=("You run tools inside a self-hosted sandbox on GKE under gVisor. "
                    "Use bash to inspect the environment when asked."),
            tools=[{"type": "agent_toolset_20260401"}],
        )
        agent_id = agent.id
        print(f"agent       {agent_id}")

    session = client.beta.sessions.create(
        agent=agent_id,
        environment_id=args.environment_id,
        title="GKE self-hosted smoke test",
    )
    print(f"session     {session.id}")
    print(f"environment {args.environment_id}")
    print("-" * 60)

    client.beta.sessions.events.send(
        session.id,
        events=[{"type": "user.message", "content": [{"type": "text", "text": args.prompt}]}],
    )

    # events.stream() can sit silent; poll events.list instead.
    seen, deadline = set(), time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        page = client.beta.sessions.events.list(session.id, order="asc")
        done = False
        for ev in page.data:
            if ev.id in seen:
                continue
            seen.add(ev.id)
            print(json.dumps(ev.model_dump(), default=str))
            if (getattr(ev, "type", "") == "session.status_idle"
                    and getattr(getattr(ev, "stop_reason", None), "type", "") == "end_turn"):
                done = True
        if done:
            break
        time.sleep(2)
    else:
        raise SystemExit(f"timed out after {args.timeout}s without end_turn")


if __name__ == "__main__":
    main()
