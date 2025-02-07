# Copyright 2023 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# [START gke_ap_autopilot_quickstart_ingress_terraform]
resource "google_compute_global_address" "gke_ingress_ipv4" {
  name = "external-address-gke-ingress-ipv4"
  ip_version = "IPV4"
  address_type = "EXTERNAL"
}

resource "google_compute_managed_ssl_certificate" "ingress-certs" {
  provider = google-beta
  name = "ingress-certs"

  managed {
    domains = local.certificate_host
  }
}

resource "kubernetes_ingress_v1" "example_ingress" {
  metadata {
    name = "example-ingress"
    annotations = {
      "kubernetes.io/ingress.global-static-ip-name" = "external-address-gke-ingress-ipv4"
      "ingress.gcp.kubernetes.io/pre-shared-cert" = "ingress-certs"
    }
  }
 
  spec {
    default_backend {
      service {
        name = "myapp-1"
        port {
          number = 8080
        }
      }
    }

    rule {
      http {
        path {
          backend {
            service {
              name = "myapp-1"
              port {
                number = 8080
              }
            }
          }

          path = "/app1/*"
        }

        path {
          backend {
            service {
              name = "myapp-2"
              port {
                number = 8080
              }
            }
          }

          path = "/app2/*"
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "example" {
  metadata {
    name = "myapp-1"
  }
  spec {
    selector = {
      app = kubernetes_pod_v1.example.metadata.0.labels.app
    }
    session_affinity = "ClientIP"
    port {
      port        = 8080
      target_port = 8080
    }

    type = "NodePort"
  }
}

resource "kubernetes_service_v1" "example2" {
  metadata {
    name = "myapp-2"
  }
  spec {
    selector = {
      app = kubernetes_pod_v1.example2.metadata.0.labels.app
    }
    session_affinity = "ClientIP"
    port {
      port        = 8080
      target_port = 8080
    }

    type = "NodePort"
  }
}

resource "kubernetes_pod_v1" "example" {
  metadata {
    name = "terraform-myapp1"
    labels = {
      app = "myapp-1"
    }
  }

  spec {
    container {
      image = "us-docker.pkg.dev/google-samples/containers/gke/hello-app:1.0"
      name  = "example"

      port {
        container_port = 8080
      }
    }
  }
}

resource "kubernetes_pod_v1" "example2" {
  metadata {
    name = "terraform-myapp2"
    labels = {
      app = "myapp-2"
    }
  }

  spec {
    container {
      image = "us-docker.pkg.dev/google-samples/containers/gke/hello-app:2.0"
      name  = "example"

      port {
        container_port = 8080
      }
    }
    # [END gke_ap_autopilot_quickstart_ingress_terraform]
  }
}

