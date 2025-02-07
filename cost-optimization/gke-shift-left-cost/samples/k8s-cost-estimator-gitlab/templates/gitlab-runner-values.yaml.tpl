gitlabUrl: https://gitlab.com
runnerRegistrationToken: "GITLAB_RUNNER_TOKEN"
fullnameOverride: gitlab-runner
logLevel: info
rbac:
  create: true
  resources: ["pods", "pods/exec", "secrets"]
  verbs: ["get", "list", "watch", "create", "patch", "delete"]
  serviceAccountAnnotations: {
    "iam.gke.io/gcp-service-account":"gitlab-runner@GCP_PROJECT_ID.iam.gserviceaccount.com"
  }
runners:
  tags: "k8s-cost-estimator-runner"
  requestConcurrency: 10
  serviceAccountName: gitlab-runner