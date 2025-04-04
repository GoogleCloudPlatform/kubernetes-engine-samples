variable "cluster_name" {
  type = string
  default = "wordpress-cluster"
  description = "The name of the gke cluster to be deployed"
}
variable "gke_node_sa_name" {
  type = string
  default = "gke-service-account"
  description = "(Between 6 and 30 characters) the name of the GKE service account"
}
variable "gke_num_nodes" {
  type = number
  default = 1
  description = "The number of GKE nodes to be deployed"
}
variable "kubernetes_service_account_name" {
  type = string
  default = "kubernetes-service-account"
  description = "(Between 6 and 30 characters) the name of the Kubernetes service account"
}
variable "machine_type" {
  type = string
  default = "n1-standard-1"
  description = "(See https://cloud.google.com/compute/docs/machine-resource) The machine type for the CloudSQL instance"
}
variable "project_id" {
  type = string
  description = "The name of the Google Cloud Project created for this deployment"
}
variable "region" {
  type = string
  default = "us-east1"
  description = "(See https://cloud.google.com/about/locations) The region for all cloud deployments"
}
variable "sql_database_name" {
  type = string
  default = "mysql-wb-db"
  description = "The name of the Google Cloud MySQL Database"
}
variable "sql_database_version" {
  type = string
  default = "MYSQL_8_0"
  description = "The version of MySQL to use for the database"
}
variable "sql_instance_name" {
  type = string
  default = "mysql-wb-instance"
  description = "The name of the Google Cloud MySQL instance"
}
variable "sql_tier" {
  type = string
  default = "db-f1-micro"
  description = "(Run `gcloud sql tiers list` to get a list of available tiers) the service tier to use for Cloud SQL"
}
variable "sql_user_name" {
  type = string
  description = "The username to use for Cloud SQL"
}
variable "wordpress_app_sa_name" {
  type = string
  default = "wordpress-service-account"
  description = "(Between 6 and 30 characters) the name of the service account to use for the wordpress app"
}
variable "wp_storage_size_gb" {
  type = number
  default = "4"
  description = "The size of the wordpress persistent storage available in Gb"
}
variable "zone" {
  type = string
  default = "us-east1-b"
  description = "(See https://cloud.google.com/compute/docs/regions-zones) the zone to use for Google Cloud resources"
}
