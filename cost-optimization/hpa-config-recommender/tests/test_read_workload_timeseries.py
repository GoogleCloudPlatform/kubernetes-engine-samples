# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on
# an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,
# either express or implied.
# See the License for the specific language governing
# permissions and limitations under the License.

"""Unit test for reading metric timeseries"""
import unittest
from datetime import datetime
import pandas as pd
import pytz
from hpaconfigrecommender.read_workload_timeseries import (
    _build_workload_filter_query,
    get_workload_agg_timeseries,
    WorkloadDetails,
    MetricRequestParameter,
)
from hpaconfigrecommender.utils.config import Config


class TestUnitFunctions(unittest.TestCase):
    """Unit tests for functions in read_timeseries."""

    def setUp(self):
        """Set up test data for unit tests."""
        self.config = Config()
        self.workload_details = WorkloadDetails(
            config = self.config,
            project_id="gtools-koptimize",
            location="us-central1",
            cluster_name="online-boutique-cluster",
            namespace="default",
            controller_name="adservice",
            controller_type="Deployment",
            container_name="server",
        )
        self.missing_container_workload_details = WorkloadDetails(
            config = self.config,
            project_id="gtools-koptimize",
            location="us-central1",
            cluster_name="online-boutique-cluster",
            namespace="default",
            controller_name="adservice",
            controller_type="Deployment",
            container_name="",
        )
        self.valid_start = datetime(2024, 11, 5, 12, 0, tzinfo=pytz.UTC)
        self.valid_end = datetime(2024, 11, 5, 13, 0, tzinfo=pytz.UTC)
        self.metric_param = MetricRequestParameter(
            metric="kubernetes.io/container/memory/request_bytes",
            per_series_aligner="ALIGN_RATE",
            cross_series_reducer="REDUCE_MEAN",
        )

        # Mock data for a valid DataFrame
        self.valid_data = {
            "double_value": [0.0015, 0.0018],
            "int64_value": [0, 0],
            "start_time": ["2024-09-01 00:01:00", "2024-09-01 00:02:00"],
            "end_time": ["2024-09-01 00:01:00", "2024-09-01 00:02:00"],
            "metric.type": ["kubernetes.io/container/memory/request_bytes"] * 2,
            "resource.type": ["k8s_container"] * 2,
            "resource.labels.project_id": ["gtools-koptimize"] * 2,
            "resource.labels.location": ["us-central1"] * 2,
            "resource.labels.cluster_name": ["online-boutique-cluster"] * 2,
            "resource.labels.namespace_name": ["default"] * 2,
            "resource.labels.container_name": ["server"] * 2,
            "resource.labels.pod_name": ["adservice-fb7bcb498-ph7hk"] * 2,
            "metadata.system_labels.top_level_controller_name": ["adservice"]
            * 2,
            "metadata.system_labels.top_level_controller_type": ["Deployment"]
            * 2,
            "metadata.system_labels.state": ["ACTIVE"] * 2,
        }

        self.valid_df = pd.DataFrame(self.valid_data)
        self.config = Config()



    def test_build_filter_query_with_all_conditions(self):
        """Test filter query with all conditions provided."""
        metric_param = MetricRequestParameter(
            metric="kubernetes.io/container/cpu/core_usage_time",
            per_series_aligner="ALIGN_RATE",
            cross_series_reducer="REDUCE_MEAN",
        )
        config = Config()
        expected_filter_query = (
            'metric.type = "kubernetes.io/container/cpu/core_usage_time" '
            'AND resource.type = "k8s_container" '
            "AND resource.labels.project_id = "
            f'"{self.workload_details.project_id}" '
            "AND resource.labels.location = "
            f'"{self.workload_details.location}" '
            "AND resource.labels.cluster_name = "
            f'"{self.workload_details.cluster_name}" '
            "AND resource.labels.namespace_name = "
            f'"{self.workload_details.namespace}" '
            "AND metadata.system_labels.top_level_controller_name = "
            f'"{self.workload_details.controller_name}" '
            "AND metadata.system_labels.top_level_controller_type = "
            f'"{self.workload_details.controller_type}" '
            "AND resource.labels.container_name = "
            f'"{self.workload_details.container_name}" '
            'AND NOT resource.labels.namespace_name = "kube-system" '
            'AND NOT resource.labels.namespace_name = "istio-system" '
            'AND NOT resource.labels.namespace_name = "gatekeeper-system" '
            'AND NOT resource.labels.namespace_name = "gke-system" '
            'AND NOT resource.labels.namespace_name = "gmp-system" '
            'AND NOT resource.labels.namespace_name = "gke-gmp-system" '
            "AND NOT resource.labels.namespace_name = "
            '"gke-managed-filestorecsi" '
            'AND NOT resource.labels.namespace_name = "gke-mcs"'
        )
        result = _build_workload_filter_query(
            config,
            metric_param,
            self.workload_details)
        self.assertEqual(result, expected_filter_query)

    def test_build_filter_query_with_memory_metric(self):
        """Test filter query with a memory metric."""
        metric_param = MetricRequestParameter(
            metric="kubernetes.io/container/memory/used_bytes",
            per_series_aligner="ALIGN_MAX",
            cross_series_reducer="REDUCE_MAX",
        )
        config = Config()
        expected_filter_query = (
            'metric.type = "kubernetes.io/container/memory/used_bytes" '
            'AND resource.type = "k8s_container" '
            'AND metric.label.memory_type = "non-evictable" '
            "AND resource.labels.project_id = "
            f'"{self.workload_details.project_id}" '
            "AND resource.labels.location = "
            f'"{self.workload_details.location}" '
            "AND resource.labels.cluster_name = "
            f'"{self.workload_details.cluster_name}" '
            "AND resource.labels.namespace_name = "
            f'"{self.workload_details.namespace}" '
            "AND metadata.system_labels.top_level_controller_name = "
            f'"{self.workload_details.controller_name}" '
            "AND metadata.system_labels.top_level_controller_type = "
            f'"{self.workload_details.controller_type}" '
            "AND resource.labels.container_name = "
            f'"{self.workload_details.container_name}" '
            'AND NOT resource.labels.namespace_name = "kube-system" '
            'AND NOT resource.labels.namespace_name = "istio-system" '
            'AND NOT resource.labels.namespace_name = "gatekeeper-system" '
            'AND NOT resource.labels.namespace_name = "gke-system" '
            'AND NOT resource.labels.namespace_name = "gmp-system" '
            'AND NOT resource.labels.namespace_name = "gke-gmp-system" '
            "AND NOT resource.labels.namespace_name = "
            '"gke-managed-filestorecsi" '
            'AND NOT resource.labels.namespace_name = "gke-mcs"'
        )

        result = _build_workload_filter_query(
            config,
            metric_param,
            self.workload_details)
        self.assertEqual(result, expected_filter_query)

    def test_build_filter_query_with_missing_values(self):
        """Test filter query with some missing values in the workload."""
        metric_param = MetricRequestParameter(
            metric="kubernetes.io/container/cpu/core_usage_time",
            per_series_aligner="ALIGN_RATE",
            cross_series_reducer="REDUCE_MEAN",
        )
        config = Config()
        workload_details = self.missing_container_workload_details
        expected_filter_query = (
            'metric.type = "kubernetes.io/container/cpu/core_usage_time" '
            'AND resource.type = "k8s_container" '
            f'AND resource.labels.project_id = "{workload_details.project_id}" '
            f'AND resource.labels.location = "{workload_details.location}" '
            "AND resource.labels.cluster_name = "
            f'"{workload_details.cluster_name}" '
            "AND resource.labels.namespace_name = "
            f'"{workload_details.namespace}" '
            "AND metadata.system_labels.top_level_controller_name = "
            f'"{workload_details.controller_name}" '
            "AND metadata.system_labels.top_level_controller_type = "
            f'"{workload_details.controller_type}" '
            'AND NOT resource.labels.namespace_name = "kube-system" '
            'AND NOT resource.labels.namespace_name = "istio-system" '
            'AND NOT resource.labels.namespace_name = "gatekeeper-system" '
            'AND NOT resource.labels.namespace_name = "gke-system" '
            'AND NOT resource.labels.namespace_name = "gmp-system" '
            'AND NOT resource.labels.namespace_name = "gke-gmp-system" '
            "AND NOT resource.labels.namespace_name = "
            '"gke-managed-filestorecsi" '
            'AND NOT resource.labels.namespace_name = "gke-mcs"'
        )
        result = _build_workload_filter_query(
            config,
            metric_param,
            workload_details)
        self.assertEqual(result, expected_filter_query)

    def test_invalid_datetime_input_start(self):
        # Invalid start_datetime (string instead of datetime)
        invalid_start = "2024-11-05 12:00:00"
        config = Config()
        # Call the function with an invalid start_datetime
        result_df = get_workload_agg_timeseries(
            config,
            self.workload_details,
            invalid_start,
            self.valid_end)

        # Verify the function returns an empty DataFrame
        self.assertIsInstance(result_df, pd.DataFrame)
        self.assertTrue(result_df.empty)

    def test_invalid_datetime_input_end(self):
        # Invalid end_datetime (integer instead of datetime)
        invalid_end = 1234567890
        config = Config()
        # Call the function with an invalid end_datetime
        result_df = get_workload_agg_timeseries(
            config,
            self.workload_details,
            self.valid_start,
            invalid_end)

        # Verify the function returns an empty DataFrame
        self.assertIsInstance(result_df, pd.DataFrame)
        self.assertTrue(result_df.empty)

if __name__ == "__main__":
    unittest.main(argv=[""], exit=False)
