/**
 * Copyright 2024 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

// Some of the Docker images from this repository are stored in Google Cloud's Artifact Registry (e.g., images referenced by GKE tutorials).
// Such images are rebuilt and repushed to Artifact Registry whenever related changes occur.
// The rebuilding/repushing is done by Google Cloud Build Triggers that we have set up in the "google-samples" Google Cloud project.
// This .tf file describes those Google Cloud Build Triggers and can be used to recreate them (e.g., in case they're accidentally deleted).
// How to use this file:
//     1. Install Terraform.
//     2. From this directory, run "terraform init". This will download the Google Terraform plugin.
//        If you get an error similar to "querying Cloud Storage failed: storage: bucket doesn't exist",
//        try running: gcloud auth application-default login
//     3. Finally, run "terraform apply" to create any missing Google Cloud Build Triggers.

terraform {
  backend "gcs" {
    bucket = "kubernetes-engine-samples"
    prefix = "terraform-state"
  }
}

provider "google" {
    project = "google-samples"
    region = "us-central1"
    zone = "us-central1-b"
}

locals {
    trigger_description = "This Cloud Build Trigger was created using Terraform (see github.com/GoogleCloudPlatform/kubernetes-engine-samples/tree/main/.github/terraform)."
}

resource "google_cloudbuild_trigger" "batch-ml-workload" {
    name = "kubernetes-engine-samples-batch-ml-workload"
    filename = "batch/aiml-workloads/src/cloudbuild.yaml"
    included_files = ["batch/aiml-workloads/src/**"]
    description = local.trigger_description

    github {
        owner = "GoogleCloudPlatform"
        name = "kubernetes-engine-samples"
        push {
            branch = "^main$"
        }
    }
}

resource "google_cloudbuild_trigger" "cloud-pubsub" {
    name = "kubernetes-engine-samples-cloud-pubsub"
    filename = "databases/cloud-pubsub/cloudbuild.yaml"
    included_files = ["databases/cloud-pubsub/**"]
    description = local.trigger_description

    github {
        owner = "GoogleCloudPlatform"
        name = "kubernetes-engine-samples"
        push {
            branch = "^main$"
        }
    }
}

resource "google_cloudbuild_trigger" "custom-metrics-direct-to-sd" {
    name = "kubernetes-engine-samples-custom-metrics-direct-to-sd"
    filename = "observability/custom-metrics-autoscaling/direct-to-sd/cloudbuild.yaml"
    included_files = ["observability/custom-metrics-autoscaling/direct-to-sd/**"]
    description = local.trigger_description

    github {
        owner = "GoogleCloudPlatform"
        name = "kubernetes-engine-samples"
        push {
            branch = "^main$"
        }
    }
}

resource "google_cloudbuild_trigger" "custom-metrics-gmp" {
    name = "kubernetes-engine-samples-custom-metrics-gmp"
    description = local.trigger_description
    filename = "observability/custom-metrics-autoscaling/google-managed-prometheus/cloudbuild.yaml"
    included_files = ["observability/custom-metrics-autoscaling/google-managed-prometheus/**"]

    github {
        owner = "GoogleCloudPlatform"
        name = "kubernetes-engine-samples"
        push {
            branch = "^main$"
        }
    }
}

resource "google_cloudbuild_trigger" "guestbook-php-redis" {
    name = "kubernetes-engine-samples-guestbook-php-redis"
    filename = "quickstarts/guestbook/php-redis/cloudbuild.yaml"
    included_files = ["quickstarts/guestbook/php-redis/**"]
    description = local.trigger_description

    github {
        owner = "GoogleCloudPlatform"
        name = "kubernetes-engine-samples"
        push {
            branch = "^main$"
        }
    }
}

resource "google_cloudbuild_trigger" "guestbook-redis-follower" {
    name = "kubernetes-engine-samples-guestbook-redis-follower"
    filename = "quickstarts/guestbook/redis-follower/cloudbuild.yaml"
    included_files = ["quickstarts/guestbook/redis-follower/**"]
    description = local.trigger_description

    github {
        owner = "GoogleCloudPlatform"
        name = "kubernetes-engine-samples"
        push {
            branch = "^main$"
        }
    }
}

resource "google_cloudbuild_trigger" "hello-app" {
    name = "kubernetes-engine-samples-hello-app"
    filename = "quickstarts/hello-app/cloudbuild.yaml"
    included_files = ["quickstarts/hello-app/**"]
    description = local.trigger_description

    github {
        owner = "GoogleCloudPlatform"
        name = "kubernetes-engine-samples"
        push {
            branch = "^main$"
        }
    }
}

resource "google_cloudbuild_trigger" "hello-app-cdn" {
    name = "kubernetes-engine-samples-hello-app-cdn"
    filename = "quickstarts/hello-app-cdn/cloudbuild.yaml"
    included_files = ["quickstarts/hello-app-cdn/**"]
    description = local.trigger_description

    github {
        owner = "GoogleCloudPlatform"
        name = "kubernetes-engine-samples"
        push {
            branch = "^main$"
        }
    }
}

resource "google_cloudbuild_trigger" "hello-app-redis" {
    name = "kubernetes-engine-samples-hello-app-redis"
    filename = "quickstarts/hello-app-redis/cloudbuild.yaml"
    included_files = ["quickstarts/hello-app-redis/**"]
    description = local.trigger_description

    github {
        owner = "GoogleCloudPlatform"
        name = "kubernetes-engine-samples"
        push {
            branch = "^main$"
        }
    }
}

resource "google_cloudbuild_trigger" "hello-app-tls" {
    name = "kubernetes-engine-samples-hello-app-tls"
    filename = "quickstarts/hello-app-tls/cloudbuild.yaml"
    included_files = ["quickstarts/hello-app-tls/**"]
    description = local.trigger_description

    github {
        owner = "GoogleCloudPlatform"
        name = "kubernetes-engine-samples"
        push {
            branch = "^main$"
        }
    }
}

resource "google_cloudbuild_trigger" "whereami" {
    name = "kubernetes-engine-samples-whereami"
    filename = "quickstarts/whereami/cloudbuild.yaml"
    included_files = ["quickstarts/whereami/**"]
    description = local.trigger_description

    github {
        owner = "GoogleCloudPlatform"
        name = "kubernetes-engine-samples"
        push {
            branch = "^main$"
        }
    }
}

resource "google_cloudbuild_trigger" "wi-secret-store" {
    name = "kubernetes-engine-samples-wi-secrets"
    filename = "security/wi-secrets/cloudbuild.yaml"
    included_files = ["security/wi-secrets/**"]
    description = local.trigger_description

    github {
        owner = "GoogleCloudPlatform"
        name = "kubernetes-engine-samples"
        push {
            branch = "^main$"
        }
    }
}

resource "google_cloudbuild_trigger" "maven-vulns" {
    name = "kubernetes-engine-samples-maven-vulns"
    filename = "security/language-vulns/maven/cloudbuild.yaml"
    included_files = ["security/language-vulns/maven/**"]
    description = local.trigger_description

    github {
        owner = "GoogleCloudPlatform"
        name = "kubernetes-engine-samples"
        push {
            branch = "^main$"
        }
    }
}

resource "google_cloudbuild_trigger" "workload-metrics" {
    name = "kubernetes-engine-samples-workload-metrics"
    filename = "observability/workload-metrics/cloudbuild.yaml"
    included_files = ["observability/workload-metrics/**"]
    description = local.trigger_description

    github {
        owner = "GoogleCloudPlatform"
        name = "kubernetes-engine-samples"
        push {
            branch = "^main$"
        }
    }
}

resource "google_cloudbuild_trigger" "keda-cloud-pubsub" {
    name = "kubernetes-engine-samples-keda-cloud-pubsub"
    filename = "cost-optimization/gke-keda/cloud-pubsub/cloudbuild.yaml"
    included_files = ["cost-optimization/gke-keda/cloud-pubsub/**"]
    description = local.trigger_description

    github {
        owner = "GoogleCloudPlatform"
        name = "kubernetes-engine-samples"
        push {
            branch = "^main$"
        }
    }
}

resource "google_cloudbuild_trigger" "metrics-exporter" {
    name = "kubernetes-engine-samples-metrics-exporter"
    filename = "cost-optimization/gke-vpa-recommendations/metrics-exporter/cloudbuild.yaml"
    included_files = ["cost-optimization/gke-vpa-recommendations/metrics-exporter/**"]
    description = local.trigger_description

    github {
        owner = "GoogleCloudPlatform"
        name = "kubernetes-engine-samples"
        push {
            branch = "^main$"
        }
    }
}

resource "google_cloudbuild_trigger" "hello-app-cloud-spanner" {
    name = "kubernetes-engine-samples-hello-app-cloud-spanner"
    filename = "databases/hello-app-cloud-spanner/cloudbuild.yaml"
    included_files = ["databases/hello-app-cloud-spanner/**"]
    description = local.trigger_description

    github {
        owner = "GoogleCloudPlatform"
        name = "kubernetes-engine-samples"
        push {
            branch = "^main$"
        }
    }
}
