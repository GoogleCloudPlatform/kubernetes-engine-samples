# How to contribute to kubernetes-engine-samples

## Steps to follow

1. [Submit an issue](https://github.com/GoogleCloudPlatform/kubernetes-engine-samples/issues/new) describing your proposed changes.
1. Wait for the proposed changes to be accepted by a repo maintainer.
1. Sign a [Contributor License Agreement](#contributor-license-agreement-cla) if you haven't done so.
1. Fork the repo, develop, and test your code changes.
1. Ensure that your code follows [samples requirements](#samples-requirements).
1. Create a [pull request (PR)](https://github.com/GoogleCloudPlatform/kubernetes-engine-samples/compare).

Note that:
- The PR reviewer may not be looking at the correctness of the code. They are
  generally focusing on the PR structure and that it follows samples requirements.
- You are responsible for making prompt fixes to any issues arising with your samples. If a sample
  goes out-of-date or breaks, it may be deprecated, depending on business needs.

## Samples requirements

All new code samples require the following:
- **Directory** for all files of the sample (e.g. `/databases/mysql-on-gke/**`).
  - Use one of the pre-existing top-level topic directories, if possible.
- **README file** with a link pointing to the tutorial or content using the sample.
  [[Template](https://github.com/GoogleCloudPlatform/kubernetes-engine-samples/blob/main/.github/new-samples-templates/README.md)]
  - There should only be one source of truth for sample instructions (i.e. don't duplicate
    instructions in the README that are or will be made available elsewhere).
- **Code** that has been tested end-to-end and follows the [Google style guides](https://google.github.io/styleguide/).
- **GitHub Action workflow** that tests the sample code. At minimum, this should
  dry-run any container images or Terraform scripts and pass without any errors.
  [[Template](https://github.com/GoogleCloudPlatform/kubernetes-engine-samples/blob/main/.github/new-samples-templates/workflow.yml)]
  - Each container image should build successfully (e.g. `docker build...`).
  - Each Terraform script should validate successfully (e.g. `terraform validate...`).
  - If there are any other quick tests that can be performed, they should also be added here.
- **Dependencies** using up-to-date versions.
  - Note that we have automation in place to update these versions on a weekly-basis.
- **License headers** on all source code and manifest files.
  [[Example](https://github.com/GoogleCloudPlatform/kubernetes-engine-samples/blob/main/.github/new-samples-templates/cloudbuild.yaml#L1-L13)]
- **Region tags** surrounding any file or snippets of code that will be embeded in a tutorial.
  [[Example](https://github.com/GoogleCloudPlatform/kubernetes-engine-samples/blob/main/ai-ml/llm-multiple-gpus/llm-service.yaml#L15-L28)]
  - These surround code to be embeded and look like: `[START gke_topic_sample_title_file_name]` and
    `[END gke_topic_sample_title_file_name]`.
- **Editable variables**, where applicable. Samples from this repository that are embedded in cloud.google.com documentation can be configured to include editable variables. In other words, readers should be able edit variables such as `PROJECT_ID` on the cloud.google.com page itself. [[Example](https://cloud.google.com/kubernetes-engine/docs/tutorials/serve-vllm-tpu#deploy-vllm)]
- **CODEOWNERS file** with an entry listing the samples maintainers.
  [[CODEOWNERS](/.github/CODEOWNERS)]

### Canonical container images
- If the sample relies on canonical image artifacts, these can be hosted officially, which requires:
  - **Cloud Build configs** for all container images that pushes to the `google-samples` artifact registry.
  [[Template](https://github.com/GoogleCloudPlatform/kubernetes-engine-samples/blob/main/.github/new-samples-templates/cloudbuild.yaml)]
  - **A Terraform resource** for the above Cloud Build configs.
  [[Example](https://github.com/GoogleCloudPlatform/kubernetes-engine-samples/blob/main/.github/terraform/google-cloud-build-triggers.tf#L194-L207)]
    - Note that in order for the Cloud Build configs to be applied to the
      `google-samples` project, you need to run `terraform init && terraform apply`
      while in that project (a repository admin will do this for you). [[Docs](/.github/terraform/README.md)]
    - The images will be of the form `us-docker.pkg.dev/google-samples/containers/gke<image_name>:latest`

## Contributor License Agreement (CLA)

Before you're able to contribute to this repository, you need to sign a Contributor License Agreement (CLA).
You can follow the links below to fill out the appropriate CLA (individual, or corporate):

* **[Individual CLA](https://developers.google.com/open-source/cla/individual):**
  You are an individual writing original source code and own the intellectual property.
* **[Corporate CLA](https://developers.google.com/open-source/cla/corporate):**
  You work for a company that allows you to contribute your work.

Follow either of the two links above to access the appropriate CLA and instructions for how to sign and
return it. Once we receive it, we'll be able to accept your pull requests. You can visit
<https://cla.developers.google.com/> to confirm your current agreements or to sign a new one.

## Community guidelines

This project follows [Google's Open Source Community Guidelines](https://opensource.google/conduct/).
