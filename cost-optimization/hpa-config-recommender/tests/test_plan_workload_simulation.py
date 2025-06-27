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

""" Unit test for HPA simulation plan """

import unittest
import pandas as pd
import numpy as np
from hpaconfigrecommender.utils.models import (
    WorkloadDetails
)
from hpaconfigrecommender.plan_workload_simulation import (
    get_simulation_plans,
    _is_workload_balanced,
    _calculate_recommended_max_cpu_capacity,
    _calculate_max_usage_slope_up_ratio,
    get_min_replicas,
    convert_data_types,
    _get_proposed_memory_recommendation
)
from hpaconfigrecommender.utils.config import Config

class TestHPASimulationPlan(unittest.TestCase):
    """Unit tests for HPA simulation algorithms."""

    def setUp(self):
        """Load test data from file."""
        self.workload_df = pd.read_csv(
            "tests/test_files/test_workload_data.csv"
        )
        self.config = Config
        # Create a workload details object
        self.workload_details = WorkloadDetails(
            config = self.config,
            project_id="gtools-koptimize",
            cluster_name="online-boutique-cluster",
            location="us-central1",
            namespace="default",
            controller_name="frontend",
            controller_type="Deployment",
            container_name="server"
        )
        self.workload_details.scheduled_to_ready_seconds=21.0
    def test_get_hpa_simulation_plans_empty_df(self):
        result, reason = get_simulation_plans(
            workload_details=self.workload_details,
            workload_df=pd.DataFrame())
        print(result, reason)
        self.assertEqual(result, [])

    def test_get_workload_balance_csv(self):
        """Test _is_workload_balanced."""
        result = _is_workload_balanced(workload_df=self.workload_df)
        self.assertFalse(result)

    def test_calculate_recommended_max_cpu_capacity(self):
        """Test _calculate_recommended_max_cpu_capacity"""
        config = Config()
        result = _calculate_recommended_max_cpu_capacity(
            config, self.workload_df
            )
        self.assertEqual(result, 10.0)

    def test_get_min_replicas_empty(self):
        """Test with an empty DataFrame."""
        config = Config()
        config.set_value(name="MIN_REC_REPLICAS", value = 2)
        workload_df = pd.DataFrame(
            columns=["num_replicas_at_usage_window"]
        )
        self.assertEqual(get_min_replicas(workload_df, config), 2)

    def test_get_min_replicas_1(self):
        """Test with a DataFrame containing data."""
        config = Config()
        workload_df = pd.DataFrame(
            {"num_replicas_at_usage_window": [1, 2, 3, 1, 2, 1, 5, 1]}
        )
        self.assertEqual(get_min_replicas(workload_df, config), 1)

    def test_get_min_replicas_2(self):
        """Test with a DataFrame containing zero in  num_replicas."""
        config = Config()
        workload_df = pd.DataFrame(
            {"num_replicas_at_usage_window":
             [2, 2, 3, 2, 2, 1, 2, 2, 2, 2, 3, 2,0]}
        )
        self.assertEqual(get_min_replicas(workload_df,config), 2)

    def test_calculate_max_usage_slope_up_ratio(self):
        # Test data

        data = {
            "avg_container_cpu_usage": [50.0, 50.0, 20.0, 20.0],
            "max_containers_mem_usage_mi": [150, 300, 200, 100],
        }
        workload_df = pd.DataFrame(data)
        workload_e2e_startup_latency_rows = 2

        # Execute function
        workload_df = _calculate_max_usage_slope_up_ratio(
            workload_df,workload_e2e_startup_latency_rows )
        expected_max_slope_ratio = [2.0, 1.0, 1.0, 0.0]
        actual_max_slope_ratio = (
            workload_df["max_usage_slope_up_ratio"].to_list()
        )

        # Assertions
        self.assertEqual(expected_max_slope_ratio, actual_max_slope_ratio)


    def test_convert_data_types(self):
        """Test if convert_data_types correctly converts column data types."""
        sample_data = pd.DataFrame({
            "window_begin": (
                ["2024-01-01 12:00:00", "2024-01-02 13:00:00", None]),
            "num_replicas_at_usage_window": [1, "2", "non-numeric"],
            "avg_container_cpu_usage": [0.5, "0.3", "non-numeric"],
            "stddev_containers_cpu_usage": [0.1, "0.2", None],
            "sum_containers_cpu_request": [100, 200, "invalid"],
            "sum_containers_cpu_usage": [80, 150, "250"],
            "sum_containers_mem_request_mi": [256, 512, None],
            "sum_containers_mem_usage_mi": [128, "256", "non-numeric"]
        })
        # Expected column data types after conversion
        expected_dtypes = {
            "window_begin": "datetime64[s]",
            "num_replicas_at_usage_window": "Int16",
            "avg_container_cpu_usage": "float16",
            "stddev_containers_cpu_usage": "float16",
            "sum_containers_cpu_request": "float16",
            "sum_containers_cpu_usage": "float16",
            "sum_containers_mem_request_mi": "float32",
            "sum_containers_mem_usage_mi": "float32"
        }

        # Apply the conversion function
        converted_df = convert_data_types(sample_data)

        # Check if each column"s data type matches the expected data type
        for column, expected_dtype in expected_dtypes.items():
            with self.subTest(column=column):
                self.assertEqual(
                    converted_df[column].dtype, expected_dtype,
                                 f"Column '{column}' has dtype "
                                 f"{converted_df[column].dtype}, "
                                f"expected {expected_dtype}")

        # Check for NaN values for invalid data
        self.assertTrue(
            pd.isna(
                converted_df["num_replicas_at_usage_window"].iloc[2]),
                "Non-numeric entry in 'num_replicas_at_usage_window' "
                "not converted to NaN")
        self.assertTrue(pd.isna(
            converted_df["avg_container_cpu_usage"].iloc[2]),
                "Non-numeric entry in 'avg_container_cpu_usage' "
                "not converted to NaN")
        self.assertTrue(pd.isna(
            converted_df["sum_containers_mem_usage_mi"].iloc[2]),
                        "Non-numeric entry in 'sum_containers_mem_usage_mi' "
                        "not converted to NaN")

    def test_get_proposed_memory_recommendation(self):
        """Test _get_proposed_memory_recommendation"""

        # Mock Config
        config = Config()
        config.set_value("MIN_REC_REPLICAS", 3)

        # Mock DataFrame
        workload_df = pd.DataFrame({
            "sum_containers_mem_usage_mi": [1000, 2000, 3000, 4000],
            "avg_container_mem_usage_mi": [250, 300, 350, 400]
        })

        # Test case 1: Normal case
        proposed_min_replicas = 3

        expected = np.ceil(342.0)
        self.assertEqual(_get_proposed_memory_recommendation(
            config, workload_df, proposed_min_replicas
            ), expected)

        # Test case 2: proposed_min_replicas less than MIN_REC_REPLICAS
        proposed_min_replicas = 1

        expected = np.ceil(342.0)
        self.assertEqual(_get_proposed_memory_recommendation(
            config, workload_df, proposed_min_replicas
            ), expected)

        # Test case 3: proposed_min_replicas more than MIN_REC_REPLICAS
        proposed_min_replicas = 5

        expected = np.ceil(342.0)
        self.assertEqual(_get_proposed_memory_recommendation(
            config, workload_df, proposed_min_replicas
            ), expected)

if __name__ == "__main__":
    unittest.main()
