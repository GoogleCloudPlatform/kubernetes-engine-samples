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

# Session-outputs bucket, mounted into the sandbox via GCS FUSE CSI.
resource "google_storage_bucket" "session_outputs" {
  name                        = "${var.project_id}-claude-session-outputs"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true

  lifecycle_rule {
    condition { age = var.session_output_retention_days }
    action { type = "Delete" }
  }

  depends_on = [google_project_service.required]
}

# Worker GSA: objectUser on this bucket only, no project-level roles.
resource "google_storage_bucket_iam_member" "worker_object_user" {
  bucket = google_storage_bucket.session_outputs.name
  role   = "roles/storage.objectUser"
  member = google_service_account.component["worker"].member
}
