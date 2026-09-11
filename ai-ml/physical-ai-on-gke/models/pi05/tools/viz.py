# Copyright 2026 Google LLC. All rights reserved.
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

"""Tiny visual helper. Import-safe on Ray workers (no IPython at module level)."""
import base64
import os


def show_gif(path, width=680, caption=None):
    """Display an animated GIF inline. Call at the TOP of a long-running cell
    so it animates while the cell works. No-op (with a note) if the file is
    missing, so a partial checkout never breaks the caller."""
    from IPython.display import HTML, display

    if not os.path.exists(path):
        print(f"[show_gif] {path} not found - skipping visual")
        return
    with open(path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode()
    cap = (f'<div style="font-size:12px;color:#8f8f88;font-family:monospace;'
           f'margin:2px 0 8px 2px">{caption}</div>') if caption else ""
    display(HTML(
        f'<img src="data:image/gif;base64,{b64}" width="{width}" '
        f'style="border:1px solid #e7e7e0;border-radius:6px">{cap}'
    ))
