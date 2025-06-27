# Copyright 2025 Google LLC
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

""" Module for managing Asset Inventory data pull to determine startup time """
import logging
import pandas as pd
from google.cloud import asset_v1
import google.auth
from google.api_core.gapic_v1.client_info import ClientInfo
from google.api_core.exceptions import GoogleAPIError
from google.auth.exceptions import DefaultCredentialsError
from hpaconfigrecommender.utils.models import (
    WorkloadDetails,
    PodDetails
)
from hpaconfigrecommender.utils.config import (
    Config,  USER_AGENT
)
from hpaconfigrecommender.utils.log import (
    log_exec_time
)

# Configure logger
logger = logging.getLogger(__name__)


def _extract_pod_times(status: dict) -> tuple:
    """
    Extract the 'PodScheduled' and 'Ready' times from pod status conditions.

    Args:
        status (dict): The status dictionary from the pod details.

    Returns:
        tuple: A tuple containing pod_scheduled_time and ready_time.
    """
    pod_scheduled_time = None
    ready_time = None
    for condition in status.get("conditions", []):
        if condition.get("type") == "PodScheduled":
            pod_scheduled_time = pd.to_datetime(
                condition.get("lastTransitionTime")
            )
        if condition.get("type") == "Ready":
            ready_time = pd.to_datetime(condition.get("lastTransitionTime"))
    return pod_scheduled_time, ready_time


def _fetch_workload_pods_details(
    workload_details: WorkloadDetails
) -> pd.DataFrame:
    """
    Fetches Kubernetes asset inventory data from Google Cloud API
    and returns it as a pandas DataFrame containing pod details.

    Args:
        workload_details(WorkloadDetails): workload information to query assets.

    Returns:
        pd.DataFrame: A DataFrame containing the details of the fetched pods.
    """
    # Initialize the API client
    try:
        credentials, _ = google.auth.default()

        # Print credentials and project to confirm they're correctly set
        if not credentials:
            logger.error(
                "No credentials found. Please authenticate with "
                "`gcloud auth application-default login` before running."
            )
            raise DefaultCredentialsError("Credentials missing or invalid")

    except DefaultCredentialsError as e:
        raise RuntimeError(
            "Failed to retrieve Google credentials: %s" % e) from e
    client = asset_v1.AssetServiceClient(
        credentials=credentials, client_info=ClientInfo(user_agent=USER_AGENT)
    )
    try:
        api_response = client.search_all_resources(
            request={
                "scope": f"projects/{workload_details.project_id}",
                "query": (
                    f"//container.googleapis.com/projects/"
                    f"{workload_details.project_id}/locations/"
                    f"{workload_details.location}/clusters/"
                    f"{workload_details.cluster_name}/k8s/namespaces/"
                    f"{workload_details.namespace}/pods/"
                    f"{workload_details.controller_name}"
                ),
                "asset_types": ["k8s.io/Pod"],
                "read_mask": "versionedResources",
            }
        )
        # Check if any resources were returned
        if not list(api_response):
            logger.warning(
                "No pod details found for the workload_details."
                " Exiting the program."
            )
            return pd.DataFrame()
    except GoogleAPIError as e:
        # Handle specific errors related to API requests
        logger.error("Failed to fetch workload pod details: %s", e)
        raise GoogleAPIError() from e

    pod_list = []

    for result in api_response:
        for versioned_resource in result.versioned_resources:
            resource_data = versioned_resource.resource

            # Extract the pod times using the helper function
            pod_scheduled_time, ready_time = _extract_pod_times(
                resource_data.get("status", {})
            )

            # Check if there is a readiness probe
            has_readiness_probe = any(
                container.get("readinessProbe")
                for container in resource_data.get("spec", {}).get(
                    "containers", []
                )
            )

            # Create a PodDetail object and add to the list
            pod_details = PodDetails(
                name=resource_data.get("metadata", {}).get("name"),
                namespace=resource_data.get("metadata", {}).get("namespace"),
                has_readiness_probe=has_readiness_probe,
                pod_scheduled_time=pod_scheduled_time,
                ready_time=ready_time,
            )
            pod_list.append(pod_details)
    # Convert the list of Pod objects into a DataFrame
    return pd.DataFrame([pod.__dict__ for pod in pod_list])

@log_exec_time(logger)
def get_workload_startup_time(
    config: Config,
    workload_details: WorkloadDetails,
) -> WorkloadDetails:
    """
    Calculate the workload startup time by removing anomalies,
    calculating the maximum time difference between pod scheduling
    and readiness, and adding HPA processing time and cluster autoscaler time.

    Args:
        config (HPAConfig): Run configurations.
        workload_dettails (WorkloadDetails): The workload information for
        querying assets.

    Returns:
        WorkloadDetails: The updated WorkloadDetails object with calculated
        startup time.
    """
    logger.info(
        "Calculating total startup time for workload: %s\n", workload_details
    )

    workload_pods_details = _fetch_workload_pods_details(workload_details)

    if workload_pods_details.empty:
        logger.warning(
            "No pod details available, setting startup time to config default.")
        return workload_details

    hpa_processing_time_seconds = config.get_value(
        "DEFAULT_HPA_PROCESSING_TIME")

    ca_startup_time_seconds = config.get_value(
        "DEFAULT_CLUSTER_AUTOSCALER_STARTUP_TIME")


    first_quartile = workload_pods_details["time_difference_seconds"].quantile(
        0.25
    )

    third_quartile = workload_pods_details["time_difference_seconds"].quantile(
        0.75
    )

    interquartile_range = third_quartile - first_quartile
    logger.info(
        "First quartile: %s, Third quartile: %s, Interquartile range: %s",
        first_quartile,
        third_quartile,
        interquartile_range,
    )

    df_filtered = workload_pods_details[
        (
            workload_pods_details["time_difference_seconds"]
            >= (first_quartile - 1.5 * interquartile_range)
        )
        & (
            workload_pods_details["time_difference_seconds"]
            <= (third_quartile + 1.5 * interquartile_range)
        )
    ]

    # Calculate the max after removing anomalies
    max_pod_startup_seconds = df_filtered["time_difference_seconds"].max()
    logger.info(
        "Max pod startup time after filtering: %s seconds.",
        max_pod_startup_seconds,
    )

    # Calculate startup time
    total_startup_seconds = (
        max_pod_startup_seconds
        + hpa_processing_time_seconds
        + ca_startup_time_seconds
    )

    # Append the calculated values to the WorkloadDetails object
    workload_details.scheduled_to_ready_seconds = max_pod_startup_seconds

    logger.info(
        "\nUpdated workload details:\n"
        "scheduled_to_ready_seconds: %d,total_startup_seconds: %d ",
        workload_details.scheduled_to_ready_seconds,
        workload_details.total_startup_seconds,
    )

    return workload_details
