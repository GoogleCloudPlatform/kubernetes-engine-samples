# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance
# with the License. You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,
# either express or implied. See the License for the specific
# language governing permissions and limitations under the License.

"""
Workload and Simulation object dataclasses for 
recommendations and cost savings in Kubernetes.
"""

from dataclasses import dataclass, field, asdict
import numpy as np
import pandas as pd
import json
from typing import Literal, Optional, List
from datetime import datetime
from .config import Config

# Helper function to handle JSON serialization
def make_json_serializable(data):
    """
    Recursively convert non-serializable objects to JSON-compatible format.
    """

    if isinstance(data, (datetime, pd.Timestamp)):
        return data.isoformat()
    if isinstance(data, list):
        return [make_json_serializable(item) for item in data]
    if isinstance(data, dict):
        return {
            key: make_json_serializable(value) for key, value in data.items()}
    if isinstance(data, (float, int)):
        return float(data)  # Ensure all numeric types are JSON-compatible
    if pd.isna(data):  # Handle NaN or None values
        return None
    return str(data)  # Default case: convert to string

@dataclass
class WorkloadDetails:
    """
    Represents Kubernetes workload details.

    Attributes:
        config (Config): Config object containing startup configuration.
        project_id (str): GCP project ID.
        cluster_name (str): Cluster name.
        location (str): Cluster location.
        namespace (str): Workload namespace.
        controller_name (str): Controller name.
        controller_type (str): Controller type.
        container_name (str): Container name.
        scheduled_to_ready_seconds (float): Time in sec.
    """

    config: Config
    project_id: str
    cluster_name: str
    location: str
    namespace: str
    controller_name: str
    controller_type: Literal["Deployment"]
    container_name: str
    min_replicas: int = 0
    max_replicas: int = 0
    _scheduled_to_ready_seconds: float = 0.0  # Renamed to internal attribute

    def __post_init__(self):
        if self._scheduled_to_ready_seconds == 0.0:
            self._scheduled_to_ready_seconds = self.config.DEFAULT_POD_STARTUPTIME

        if self.config.DISTANCE_BETWEEN_POINTS_SECONDS <= 0:
            raise ValueError(
                "DISTANCE_BETWEEN_POINTS_SECONDS must be greater than 0.")

    @property
    def total_startup_seconds(self) -> float:
        """
        Computes total startup time dynamically.
        """
        return (
            self._scheduled_to_ready_seconds
            + self.config.DEFAULT_CLUSTER_AUTOSCALER_STARTUP_TIME
            + self.config.DEFAULT_HPA_PROCESSING_TIME
        )

    @property
    def workload_e2e_startup_latency_rows(self) -> int:
        """
        Computes the number of rows required for the startup latency dynamically.
        """
        return int(
            np.ceil(
                self.total_startup_seconds /
                self.config.DISTANCE_BETWEEN_POINTS_SECONDS
                )
        )

    @property
    def scheduled_to_ready_seconds(self) -> float:
        return self._scheduled_to_ready_seconds

    @scheduled_to_ready_seconds.setter
    def scheduled_to_ready_seconds(self, value: float):
        self._scheduled_to_ready_seconds = value


@dataclass
class PodDetails:
    """
    Details of a pod including probes and timings.

    Attributes:
        name (str): Pod name.
        namespace (str): Pod namespace.
        has_readiness_probe (bool): Readiness probe flag.
        pod_scheduled_time (datetime): Schedule time.
        ready_time (datetime): Ready state time.
        time_difference_seconds (float): Time from
            scheduling to ready state.
    """

    name: str
    namespace: str
    has_readiness_probe: bool
    pod_scheduled_time: datetime
    ready_time: datetime
    time_difference_seconds: float = 0.0

    def __post_init__(self):
        """
        Calculate time difference between scheduling
        and readiness in seconds.
        """
        if self.pod_scheduled_time and self.ready_time:
            self.time_difference_seconds = (
                self.ready_time - self.pod_scheduled_time
            ).total_seconds()

@dataclass
class MetricRequestParameter:
    """
    Parameters for querying metrics.

    Attributes:
        metric (str): Metric type to query.
        per_series_aligner (str): Series alignment.
        cross_series_reducer (str): Series aggregation.
        latest_value (bool): Latest value flag.
    """

    metric: str
    per_series_aligner: str
    cross_series_reducer: str
    latest_value: bool = False

@dataclass
class WorkloadPlan:
    """
        method(str):  algorithm (DCR/DMR).
        recommended_cpu_request: float
        recommended_mem_request_and_limits_mi: float
        recommended_cpu_request (float): CPU request.
        recommended_mem_request_and_limits_mi (float): Memory request.
        recommended__min_replicas(int): Min replicas.
        recommended__max_replicas(int): Max replicas.
        recommended__target_cpu (float): Target CPU.
    """
    recommended_cpu_request: float
    recommended_mem_request_and_limits_mi: float
    recommended_cpu_limit_or_unbounded: Optional[float] = 0.0
    recommended_min_replicas: Optional[int] = 0
    recommended_max_replicas: Optional[int] = 0
    recommended_hpa_target_cpu: Optional[float] = 0.0
    max_usage_slope_up_ratio: float = 0.0
    workload_e2e_startup_latency_rows: int = 0
    method: str = ""

    def to_json(self):
        return json.dumps(make_json_serializable(asdict(self)), indent=2)

@dataclass
class WorkloadRecommendation:
    """
     Workload recommendation details.

    """
    workload_details: WorkloadDetails
    plan: WorkloadPlan
    analysis_period_start: str = ""
    analysis_period_end: str = ""
    scale_up_behaviour_to_x_times: float = 0.0
    valid: bool = False
    validation_msg: str = ""
    forecast_mem_saving_mi: float = 0.0
    forecast_cpu_saving: float = 0.0
    logs: List[str] = field(default_factory=list)
    def to_json(self) -> str:
        """
        Returns the class data as a JSON string.
        If `valid` is True, excludes logs. If `valid` is False,
        includes only workload_details and logs.

        Returns:
            str: JSON-formatted string based on `valid`.
        """
        if self.valid:
            # Exclude logs when valid is True
            data = asdict(self)
        else:
            # Include only workload_details and logs when valid is False
            data = {
                "Plan": self.plan,
                "Valid": self.valid,
                "Reason": self.validation_msg,
            }
        return json.dumps(make_json_serializable(data), indent=2)
    def add_log(self, message: str, *args):
        """
        Adds a log message with optional interpolation.

        Args:
            message (str): The log message template with placeholders.
            *args: Values to be formatted into the message. Tuples and other
                   non-string types are converted to strings automatically.
        """
        # Convert non-string args (like tuple) to string
        args = tuple(str(arg) for arg in args)

        # Interpolate message with args if provided
        if args:
            message = message % args

        # Append the formatted message to the logs
        self.logs.append(message)

    def get_details(self):
        """
        Returns all attributes of the class except for 'logs'.

        Returns:
            dict: A dictionary of all attributes except logs.
        """
        all_data = asdict(self)
        # Remove 'logs' from the dictionary
        all_data.pop("logs", None)
        return all_data

    def get_logs(self) -> str:
        """
        Returns a formatted string of the logs.

        Returns:
            str: The accumulated logs as a single string.
        """
        return "\n".join(self.logs) if self.logs else "No logs available."
