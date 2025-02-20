# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

""" Unit test for reading workload start time"""
import unittest
from unittest.mock import patch, Mock
from google.api_core.exceptions import GoogleAPIError
import pandas as pd

from hpaconfigrecommender.read_workload_startuptime import (
    get_workload_startup_time,
    _extract_pod_times,
    _fetch_workload_pods_details,
)
from hpaconfigrecommender.utils.models import WorkloadDetails

from hpaconfigrecommender.utils.config import Config

class TestWorkloadStartupTime(unittest.TestCase):
    """Test case for workload startup time."""

    def setUp(self):
        """Set up mock data for the tests."""
        self.config = Config()
        self.workload_details = WorkloadDetails(
            config=self.config,
            project_id="test-project",
            cluster_name="test-cluster",
            location="us-central1",
            namespace="test-namespace",
            controller_name="test-controller",
            controller_type="Deployment",
            container_name="server",
        )

        # Mock DataFrame to simulate pod details
        self.mock_pod_details = pd.DataFrame(
            {
                "name": ["test-pod-1", "test-pod-2"],
                "namespace": ["test-namespace", "test-namespace"],
                "has_readiness_probe": [True, True],
                "pod_scheduled_time": [
                    pd.Timestamp("2024-09-01T00:00:00Z"),
                    pd.Timestamp("2024-09-01T00:01:00Z"),
                ],
                "ready_time": [
                    pd.Timestamp("2024-09-01T00:02:00Z"),
                    pd.Timestamp("2024-09-01T00:03:00Z"),
                ],
                "time_difference_seconds": [120.0, 120.0],
            }
        )
        # Mock DataFrame for quartile testing
        self.mock_quartile_pods = pd.DataFrame(
            {
                "name": [
                    "test-pod-1",
                    "test-pod-2",
                    "test-pod-3",
                    "test-pod-4",
                ],
                "time_difference_seconds": [50.0, 100.0, 200.0, 300.0],
            }
        )
        self.config = Config()

    def test_extract_both_pod_scheduled_and_ready(self):
        """Test with both PodScheduled and Ready conditions."""
        pod_status = {
            "conditions": [
                {
                    "type": "PodScheduled",
                    "lastTransitionTime": "2024-09-01T00:00:00Z",
                },
                {"type": "Ready", "lastTransitionTime": "2024-09-01T00:02:00Z"},
            ]
        }
        pod_scheduled_time, ready_time = _extract_pod_times(pod_status)

        self.assertEqual(
            pod_scheduled_time, pd.Timestamp("2024-09-01T00:00:00Z")
        )
        self.assertEqual(ready_time, pd.Timestamp("2024-09-01T00:02:00Z"))

    def test_extract_pod_scheduled_only(self):
        """Test with only PodScheduled condition present."""
        pod_status = {
            "conditions": [
                {
                    "type": "PodScheduled",
                    "lastTransitionTime": "2024-09-01T00:00:00Z",
                }
            ]
        }
        pod_scheduled_time, ready_time = _extract_pod_times(pod_status)

        self.assertEqual(
            pod_scheduled_time, pd.Timestamp("2024-09-01T00:00:00Z")
        )
        self.assertIsNone(ready_time)

    def test_extract_ready_only(self):
        """Test with only Ready condition present."""
        pod_status = {
            "conditions": [
                {"type": "Ready", "lastTransitionTime": "2024-09-01T00:02:00Z"}
            ]
        }
        pod_scheduled_time, ready_time = _extract_pod_times(pod_status)

        self.assertIsNone(pod_scheduled_time)
        self.assertEqual(ready_time, pd.Timestamp("2024-09-01T00:02:00Z"))

    def test_extract_no_conditions(self):
        """Test with no conditions present."""
        pod_status = {"conditions": []}
        pod_scheduled_time, ready_time = _extract_pod_times(pod_status)

        self.assertIsNone(pod_scheduled_time)
        self.assertIsNone(ready_time)

    def test_extract_missing_last_transition_time(self):
        """Test when lastTransitionTime is missing."""
        pod_status = {
            "conditions": [
                {
                    "type": "PodScheduled"
                    # lastTransitionTime is missing
                },
                {
                    "type": "Ready"
                    # lastTransitionTime is missing
                },
            ]
        }
        pod_scheduled_time, ready_time = _extract_pod_times(pod_status)

        self.assertIsNone(pod_scheduled_time)
        self.assertIsNone(ready_time)

    @patch(
        "hpaconfigrecommender.read_workload_startuptime"
        "._fetch_workload_pods_details"
    )
    def test_get_workload_startup_time(self, mock_fetch_pods):
        """Test startup time calculation."""
        # Mock response to return mock DataFrame
        mock_fetch_pods.return_value = self.mock_pod_details
        config = Config()
        # Call the function
        startup_time = get_workload_startup_time(
            config, self.workload_details )

        # Validate the results
        self.assertEqual(startup_time.scheduled_to_ready_seconds, 120)
        self.assertEqual(
            startup_time.total_startup_seconds, 240
        )  # 120 + 45 + 75

    @patch(
        "hpaconfigrecommender.read_workload_startuptime."
        "_fetch_workload_pods_details"
    )
    def test_get_workload_startup_time_empty(self, mock_fetch_pods):
        """Test when no pods are returned."""
        mock_fetch_pods.return_value = pd.DataFrame()
        # Call the function
        startup_time = get_workload_startup_time(
            self.config,
            self.workload_details)

        # Check that the startup time is zero
        self.assertEqual(
            startup_time.scheduled_to_ready_seconds,
            self.config.DEFAULT_POD_STARTUPTIME)


    @patch(
        "hpaconfigrecommender.read_workload_startuptime"
        "._fetch_workload_pods_details"
    )
    def test_quartile_calculation(self, mock_fetch_pods):
        """Test quartile and IQR filtering."""
        mock_fetch_pods.return_value = self.mock_quartile_pods

        # Call the function
        startup_time = get_workload_startup_time(
            self.config,
            self.workload_details)

        # Expected quartiles and IQR
        expected_first_quartile = 87.5
        expected_third_quartile = 225.0
        expected_iqr = 137.5

        # Validate quartile and IQR
        actual_first_quartile = self.mock_quartile_pods[
            "time_difference_seconds"
        ].quantile(0.25)
        actual_third_quartile = self.mock_quartile_pods[
            "time_difference_seconds"
        ].quantile(0.75)
        actual_iqr = actual_third_quartile - actual_first_quartile

        self.assertAlmostEqual(
            actual_first_quartile, expected_first_quartile, places=1
        )
        self.assertAlmostEqual(
            actual_third_quartile, expected_third_quartile, places=1
        )
        self.assertAlmostEqual(actual_iqr, expected_iqr, places=1)

        # Filter the data based on IQR
        filtered_df = self.mock_quartile_pods[
            (
                self.mock_quartile_pods["time_difference_seconds"]
                >= (actual_first_quartile - 1.5 * actual_iqr)
            )
            & (
                self.mock_quartile_pods["time_difference_seconds"]
                <= (actual_third_quartile + 1.5 * actual_iqr)
            )
        ]

        # Ensure no data points were filtered out
        self.assertEqual(len(filtered_df), 4)

        # Validate the startup time calculation
        self.assertEqual(startup_time.scheduled_to_ready_seconds, 300.0)
        self.assertEqual(
            startup_time.total_startup_seconds,
            300.0
            + self.config.get_value("DEFAULT_HPA_PROCESSING_TIME")
            + self.config.get_value(
                "DEFAULT_CLUSTER_AUTOSCALER_STARTUP_TIME")
        )

    @patch("google.auth.default")
    def test_fetch_workload_pods_details_no_credentials(self, mock_auth):
        """
        Test handling of missing credentials for fetching pod details.
        It should raise a RuntimeError.
        """
        mock_auth.return_value = (None, None)

        with self.assertRaises(RuntimeError) as context:
            _fetch_workload_pods_details(self.workload_details)

        self.assertIn("Credentials missing or invalid", str(context.exception))

    @patch("google.auth.default")
    @patch("google.cloud.asset_v1.AssetServiceClient")
    def test_fetch_workload_pods_details_api_error(
        self, mock_asset_client, mock_auth
    ):
        """
        Test API error handling when fetching workload pod details.
        The system should exit upon encountering an API error.
        """
        mock_auth.return_value = (Mock(), "test-project-id")
        mock_asset_client.return_value.search_all_resources.side_effect = (
            GoogleAPIError("API error")
        )

        with self.assertRaises(GoogleAPIError):
            _fetch_workload_pods_details(self.workload_details)


if __name__ == "__main__":
    unittest.main()
