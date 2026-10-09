module "cloud-storage" {
  source        = "terraform-google-modules/cloud-storage/google//modules/simple_bucket"
  version       = "~> 9.0"

  name          = "${var.project_id}-${var.cluster_prefix}-vector-storage"
  project_id    = var.project_id
  location      = var.region
  force_destroy = true
}

locals {
  workload_principal = "principal://iam.googleapis.com/projects/${data.google_project.project.number}/locations/global/workloadIdentityPools/${var.project_id}.svc.id.goog/subject/ns/milvus/sa/storage-access"
}

data "google_project" "project" {
  project_id               = var.project_id
}

module "cloud-storage-iam-bindings" {
  source          = "terraform-google-modules/iam/google//modules/storage_buckets_iam"
  version         = "~> 8.0"

  storage_buckets = [module.cloud-storage.name]
  mode            = "authoritative"
  bindings        = {
    "roles/storage.objectUser" = ["${local.workload_principal}"]
  }
  depends_on      = [module.cloud-storage]
}
