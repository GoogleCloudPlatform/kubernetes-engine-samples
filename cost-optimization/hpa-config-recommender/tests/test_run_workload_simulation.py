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

""" Unit test for HPA simulation run code """
import unittest
from pathlib import Path
import pandas as pd
import numpy as np
from hpaconfigrecommender.utils.config import Config
from hpaconfigrecommender.utils.models import (
    WorkloadDetails,
    WorkloadPlan,
    WorkloadRecommendation
)
from hpaconfigrecommender.run_workload_simulation import (
    plan_and_run_simulation
)


class TestPlanAndRunHPASimulation(unittest.TestCase):
    """Unit tests for `plan_and_run_simulation`."""

    def setUp(self):
        self.config = Config()

        self.workload_details = WorkloadDetails(
            config=self.config,
            project_id="test_project",
            cluster_name="test_cluster",
            location="test_location",
            namespace="test_namespace",
            controller_name="test_controller",
            controller_type="Deployment",
            container_name="test_container",
        )
        self.workload_details.scheduled_to_ready_seconds=20.0

    def run_test_for_id(self, test_id: str,
                        expected_rec: WorkloadRecommendation,
                        config: Config):
        """Helper method to run individual tests by `test_id`."""
        self.workload_details.config = config
        TEST_DIR = Path(__file__).parent
        TEST_FILE_PATH = (TEST_DIR / "test_files" /
                          f"test_id_{test_id}_dataframe.csv")
        workload_df_path = (
            TEST_FILE_PATH
        )

        workload_df = pd.read_csv(workload_df_path)

        _, summary, _, _ = plan_and_run_simulation(
            self.workload_details,
            workload_df
        )

        # Ensure `summary` has a valid `WorkloadRecommendation` instance
        self.assertIsNotNone(summary, f"No summary for test ID {test_id}")
        self.assertIsInstance(
            summary,
            WorkloadRecommendation,
            f"Expected WorkloadRecommendation for test ID {test_id}",
        )

        # Extract actual recommendation from summary
        actual_rec = summary

        # Debug logging for assertion checkpoints
        print("Checking forecast CPU savings...")
        self.assertEqual(
            np.ceil(actual_rec.forecast_cpu_saving),
            np.ceil(expected_rec.forecast_cpu_saving),
            msg=f"Forecast CPU savings mismatch for test ID {test_id}",
        )

        print("Checking forecast memory savings...")
        self.assertAlmostEqual(
            actual_rec.forecast_mem_saving_mi,
            expected_rec.forecast_mem_saving_mi,
            delta=100,
            msg=f"Forecast memory savings mismatch for test ID {test_id}",
        )

        print("Checking recommended CPU request...")
        self.assertAlmostEqual(
            actual_rec.plan.recommended_cpu_request,
            expected_rec.plan.recommended_cpu_request,
            delta=0.100,
            msg=f"Recommended CPU request mismatch for test ID {test_id}",
        )

        print("Checking recommended memory request and limits...")
        self.assertAlmostEqual(
            actual_rec.plan.recommended_mem_request_and_limits_mi,
            expected_rec.plan.recommended_mem_request_and_limits_mi,
            places=1,
            msg=f"Recommended memory mismatch for test ID {test_id}",
        )

        print("Checking recommended CPU limit or unbounded...")
        self.assertAlmostEqual(
            actual_rec.plan.recommended_cpu_limit_or_unbounded,
            expected_rec.plan.recommended_cpu_limit_or_unbounded,
            places=2,
            msg=f"Recommended CPU limit  mismatch for test ID {test_id}",
        )

        print("Checking recommended HPA minimum replicas...")
        self.assertEqual(
            actual_rec.plan.recommended_min_replicas,
            expected_rec.plan.recommended_min_replicas,
            f"Recommended HPA minimum replicas mismatch for test ID {test_id}",
        )

        print("Checking recommended HPA maximum replicas...")
        self.assertEqual(
            actual_rec.plan.recommended_max_replicas,
            expected_rec.plan.recommended_max_replicas,
            f"Recommended HPA maximum replicas mismatch for test ID {test_id}",
        )

        print("Checking recommended HPA target CPU...")
        self.assertAlmostEqual(
            actual_rec.plan.recommended_hpa_target_cpu,
            expected_rec.plan.recommended_hpa_target_cpu,
            places=2,
            msg=f"Recommended HPA target CPU mismatch for test ID {test_id}",
        )

    def test_hpa_simulation_1(self):
        config = self.workload_details.config
 
        config.set_value("DISTANCE_BETWEEN_POINTS_SECONDS",30)
        expected_rec = WorkloadRecommendation(
            workload_details = self.workload_details,
            plan= WorkloadPlan(
                recommended_cpu_request=0.081,
                recommended_mem_request_and_limits_mi=14.0,
                recommended_cpu_limit_or_unbounded=1.0,
                recommended_min_replicas=20,
                recommended_max_replicas=20,
                recommended_hpa_target_cpu=1.0
            ),
            forecast_mem_saving_mi = 937.0,
            forecast_cpu_saving = 8.262,
        )
        self.run_test_for_id("1", expected_rec, config)

    def test_hpa_simulation_2(self):
        config = self.workload_details.config
        config.set_value("EXTRA_HPA_BUFFER_FOR_MEMORY_RECOMMENDATION",1.1)
        config.set_value("EXTRA_VPA_BUFFER_FOR_MEMORY_RECOMMENDATION",1.1)
        config.set_value("DISTANCE_BETWEEN_POINTS_SECONDS",30)
        config.set_value("EXTRA_HPA_BUFFER_FOR_CPU_USAGE_CAPACITY",1.20)
        config.set_value("EXTRA_HPA_BUFFER_FOR_MAX_REPLICAS",1.05)
        config.set_value("HPA_TARGET_BUFFER", 0.2)
        expected_rec = WorkloadRecommendation(
            workload_details = self.workload_details,
            plan= WorkloadPlan(
                method="DCR-78",
                recommended_cpu_request=0.169,
                recommended_mem_request_and_limits_mi=20.0,
                recommended_cpu_limit_or_unbounded=1.0,
                recommended_min_replicas=5,
                recommended_max_replicas=5,
                recommended_hpa_target_cpu=1.0
            ),
            forecast_mem_saving_mi = 174.0,
            forecast_cpu_saving = 1.258
        )
        self.run_test_for_id("2", expected_rec, config)

    def test_hpa_simulation_3(self):
        config = self.workload_details.config
        config.set_value("EXTRA_HPA_BUFFER_FOR_MEMORY_RECOMMENDATION",1.2)
        config.set_value("DISTANCE_BETWEEN_POINTS_SECONDS",30)
        config.set_value("EXTRA_HPA_BUFFER_FOR_CPU_USAGE_CAPACITY",1.20)
        config.set_value("EXTRA_HPA_BUFFER_FOR_MAX_REPLICAS",1.05)
        config.set_value("HPA_TARGET_BUFFER", 0.2)
        expected_rec = WorkloadRecommendation(
            workload_details = self.workload_details,
            plan= WorkloadPlan(
                method="DCR-78",
                recommended_cpu_request=0.04,
                recommended_mem_request_and_limits_mi=14.0,
                recommended_cpu_limit_or_unbounded=1.0,
                recommended_min_replicas=20,
                recommended_max_replicas=263,
                recommended_hpa_target_cpu=0.64
            ),
            forecast_mem_saving_mi = 861.0,
            forecast_cpu_saving = 8.802
        )
        self.run_test_for_id("3", expected_rec, config)

    def test_hpa_simulation_4(self):
        config = self.workload_details.config
        config.set_value("EXTRA_HPA_BUFFER_FOR_MEMORY_RECOMMENDATION", 1.1)
        config.set_value("EXTRA_VPA_BUFFER_FOR_MEMORY_RECOMMENDATION",2.00)
        config.set_value("EXTRA_HPA_BUFFER_FOR_CPU_USAGE_CAPACITY",2.2)
        config.set_value("DISTANCE_BETWEEN_POINTS_SECONDS",30)
        expected_rec = WorkloadRecommendation(
            workload_details = self.workload_details,
            plan= WorkloadPlan(
                method="DCR-98",
                recommended_cpu_request=0.29,
                recommended_mem_request_and_limits_mi=20.0,
                recommended_cpu_limit_or_unbounded=1.0,
                recommended_min_replicas=3,
                recommended_max_replicas=9,
                recommended_hpa_target_cpu=0.65
        ),
        forecast_mem_saving_mi = 42.0,
        forecast_cpu_saving = -1.0
        )
        self.run_test_for_id("4", expected_rec, config)

    def test_hpa_simulation_5(self):
        config = self.workload_details.config
        config.set_value("EXTRA_HPA_BUFFER_FOR_MEMORY_RECOMMENDATION", 1.1)
        config.set_value("EXTRA_VPA_BUFFER_FOR_MEMORY_RECOMMENDATION",1.1)
        config.set_value("DISTANCE_BETWEEN_POINTS_SECONDS",30)
        config.set_value("EXTRA_HPA_BUFFER_FOR_CPU_USAGE_CAPACITY",1.20)
        config.set_value("EXTRA_HPA_BUFFER_FOR_MAX_REPLICAS",1.05)
        config.set_value("HPA_TARGET_BUFFER", 0.2)
        expected_rec = WorkloadRecommendation(
            workload_details = self.workload_details,
            plan= WorkloadPlan(
            method="DCR-89",
            recommended_cpu_request=0.25,
            recommended_mem_request_and_limits_mi=16.0,
            recommended_cpu_limit_or_unbounded=1.0,
            recommended_min_replicas=5,
            recommended_max_replicas=7,
            recommended_hpa_target_cpu=0.74
        ),
        forecast_mem_saving_mi = -108.0,
        forecast_cpu_saving = -1.434
        )
        self.run_test_for_id("5", expected_rec, config)

    def test_hpa_simulation_5b(self):
        config = self.workload_details.config
        config.set_value("EXTRA_HPA_BUFFER_FOR_MEMORY_RECOMMENDATION", 1.1)
        config.set_value("DISTANCE_BETWEEN_POINTS_SECONDS",30)
        config.set_value("EXTRA_HPA_BUFFER_FOR_CPU_USAGE_CAPACITY",1.20)
        config.set_value("EXTRA_HPA_BUFFER_FOR_MAX_REPLICAS",1.05)
        config.set_value("HPA_TARGET_BUFFER", 0.2)
        expected_rec = WorkloadRecommendation(
            workload_details = self.workload_details,
            plan= WorkloadPlan(
            method="DCR-96",
            recommended_cpu_request=0.242,
            recommended_mem_request_and_limits_mi=16.0,
            recommended_cpu_limit_or_unbounded=1.0,
            recommended_min_replicas=5,
            recommended_max_replicas=10,
            recommended_hpa_target_cpu=0.57
        ),
        forecast_mem_saving_mi = -129.0,
        forecast_cpu_saving = -1.424
        )
        self.run_test_for_id("5b", expected_rec, config)

    def test_hpa_simulation_6(self):
        config = self.workload_details.config
        config.set_value("EXTRA_HPA_BUFFER_FOR_MEMORY_RECOMMENDATION", 1.1)
        config.set_value("EXTRA_VPA_BUFFER_FOR_MEMORY_RECOMMENDATION", 1.05)
        config.set_value("DISTANCE_BETWEEN_POINTS_SECONDS",30)
        config.set_value("EXTRA_HPA_BUFFER_FOR_CPU_USAGE_CAPACITY",1.20)
        config.set_value("EXTRA_VPA_BUFFER_FOR_CPU_USAGE_CAPACITY",1.00)
        config.set_value("EXTRA_HPA_BUFFER_FOR_MAX_REPLICAS",1.05)
        config.set_value("HPA_TARGET_BUFFER", 0.2)
        expected_rec = WorkloadRecommendation(
            workload_details = self.workload_details,
            plan= WorkloadPlan(
            method="DCR-94",
            recommended_cpu_request=0.08,
            recommended_mem_request_and_limits_mi=14.0,
            recommended_cpu_limit_or_unbounded=1.0,
            recommended_min_replicas=20,
            recommended_max_replicas=132,
            recommended_hpa_target_cpu=0.78
        ),
        forecast_mem_saving_mi = 947.0,
        forecast_cpu_saving = 8.221
        )
        self.run_test_for_id("6", expected_rec, config)

    def test_hpa_simulation_7(self):
        config = self.workload_details.config
        config.set_value("EXTRA_HPA_BUFFER_FOR_MEMORY_RECOMMENDATION", 1.1)
        config.set_value("DISTANCE_BETWEEN_POINTS_SECONDS",30)
        config.set_value("EXTRA_HPA_BUFFER_FOR_CPU_USAGE_CAPACITY",1.20)
        config.set_value("EXTRA_HPA_BUFFER_FOR_MAX_REPLICAS",1.05)
        config.set_value("HPA_TARGET_BUFFER", 0.2)
        expected_rec = WorkloadRecommendation(
            workload_details = self.workload_details,
            plan= WorkloadPlan(
            method="DCR-90",
            recommended_cpu_request=0.179,
            recommended_mem_request_and_limits_mi=8.0,
            recommended_cpu_limit_or_unbounded=1.0,
            recommended_min_replicas=7,
            recommended_max_replicas=9,
            recommended_hpa_target_cpu=0.48
        ),
        forecast_mem_saving_mi = 103.0,
        forecast_cpu_saving = 0.164
        )
        self.run_test_for_id("7", expected_rec, config)

    def test_hpa_simulation_7b(self):
        config = self.workload_details.config
        config.set_value("DISTANCE_BETWEEN_POINTS_SECONDS",30)
        expected_rec = WorkloadRecommendation(
            workload_details = self.workload_details,
            plan= WorkloadPlan(
            method="DCR-90",
            recommended_cpu_request=0.056,
            recommended_mem_request_and_limits_mi=13.0,
            recommended_cpu_limit_or_unbounded=1.0,
            recommended_min_replicas=30,
            recommended_max_replicas=48,
            recommended_hpa_target_cpu=0.68
        ),
        forecast_mem_saving_mi = 1518.0,
        forecast_cpu_saving = -0.513
        )
        self.run_test_for_id("7b", expected_rec, config)

    def test_hpa_simulation_7c(self):
        config = self.workload_details.config
        config.set_value("EXTRA_HPA_BUFFER_FOR_MEMORY_RECOMMENDATION", 1.1)
        config.set_value("DISTANCE_BETWEEN_POINTS_SECONDS",30)
        config.set_value("EXTRA_HPA_BUFFER_FOR_CPU_USAGE_CAPACITY",1.20)
        config.set_value("EXTRA_HPA_BUFFER_FOR_MAX_REPLICAS",1.05)
        config.set_value("HPA_TARGET_BUFFER", 0.2)
        expected_rec = WorkloadRecommendation(
            workload_details = self.workload_details,
            plan= WorkloadPlan(
            method="DCR-98",
            recommended_cpu_request=0.339,
            recommended_mem_request_and_limits_mi=28.0,
            recommended_cpu_limit_or_unbounded=1.0,
            recommended_min_replicas=3,
            recommended_max_replicas=3,
            recommended_hpa_target_cpu=1.0
        ),
        forecast_mem_saving_mi = 93.0,
        forecast_cpu_saving = 0.332
        )
        self.run_test_for_id("7c", expected_rec, config)

    def test_hpa_simulation_8(self):
        config = self.workload_details.config
        config.set_value("EXTRA_HPA_BUFFER_FOR_MEMORY_RECOMMENDATION", 1.2)
        config.set_value("DISTANCE_BETWEEN_POINTS_SECONDS",30)
        config.set_value("EXTRA_HPA_BUFFER_FOR_CPU_USAGE_CAPACITY",1.20)
        config.set_value("EXTRA_VPA_BUFFER_FOR_CPU_USAGE_CAPACITY",1.01)
        config.set_value("EXTRA_HPA_BUFFER_FOR_MAX_REPLICAS",1.05)
        config.set_value("HPA_TARGET_BUFFER", 0.2)
        expected_rec = WorkloadRecommendation(
            workload_details = self.workload_details,
            plan= WorkloadPlan(
            method="DCR-74",
            recommended_cpu_request=0.051,
            recommended_mem_request_and_limits_mi=14.0,
            recommended_cpu_limit_or_unbounded=1.0,
            recommended_min_replicas=30,
            recommended_max_replicas=62,
            recommended_hpa_target_cpu=0.52
        ),
        forecast_mem_saving_mi = 1193.0,
        forecast_cpu_saving = 0.331
        )
        self.run_test_for_id("8", expected_rec, config)

    def test_hpa_simulation_9(self):
        config = self.workload_details.config
        config.set_value("EXTRA_HPA_BUFFER_FOR_MEMORY_RECOMMENDATION", 1.2)
        config.set_value("DISTANCE_BETWEEN_POINTS_SECONDS",30)
        config.set_value("EXTRA_HPA_BUFFER_FOR_CPU_USAGE_CAPACITY",1.20)
        config.set_value("EXTRA_HPA_BUFFER_FOR_MAX_REPLICAS",1.05)
        config.set_value("HPA_TARGET_BUFFER", 0.2)
        expected_rec = WorkloadRecommendation(
            workload_details = self.workload_details,
            plan= WorkloadPlan(
            method="DCR-86",
            recommended_cpu_request=0.043,
            recommended_mem_request_and_limits_mi=14.0,
            recommended_cpu_limit_or_unbounded=1.0,
            recommended_min_replicas=20,
            recommended_max_replicas=489,
            recommended_hpa_target_cpu=0.67
        ),
        forecast_mem_saving_mi = 873.0,
        forecast_cpu_saving = 18.832
        )
        self.run_test_for_id("9", expected_rec, config)

    def test_hpa_simulation_10(self):
        config = self.workload_details.config
        config.set_value("EXTRA_HPA_BUFFER_FOR_MEMORY_RECOMMENDATION", 1.2)
        config.set_value("DISTANCE_BETWEEN_POINTS_SECONDS",30)
        config.set_value("EXTRA_HPA_BUFFER_FOR_CPU_USAGE_CAPACITY",1.20)
        config.set_value("EXTRA_HPA_BUFFER_FOR_MAX_REPLICAS",1.05)
        config.set_value("HPA_TARGET_BUFFER", 0.2)
        expected_rec = WorkloadRecommendation(
            workload_details = self.workload_details,
            plan= WorkloadPlan(
            method="DCR-95",
            recommended_cpu_request=0.06,
            recommended_mem_request_and_limits_mi=15.0,
            recommended_cpu_limit_or_unbounded=1.0,
            recommended_min_replicas=30,
            recommended_max_replicas=263,
            recommended_hpa_target_cpu=0.79
        ),
        forecast_mem_saving_mi = 1354.0,
        forecast_cpu_saving = 13.0
        )
        self.run_test_for_id("10", expected_rec, config)

    def test_hpa_simulation_11(self):
        config = self.workload_details.config
        config.set_value("EXTRA_HPA_BUFFER_FOR_MEMORY_RECOMMENDATION", 1.2)
        config.set_value("DISTANCE_BETWEEN_POINTS_SECONDS",30)
        config.set_value("EXTRA_HPA_BUFFER_FOR_CPU_USAGE_CAPACITY",1.20)
        config.set_value("EXTRA_HPA_BUFFER_FOR_MAX_REPLICAS",1.05)
        config.set_value("HPA_TARGET_BUFFER", 0.2)
        expected_rec = WorkloadRecommendation(
            workload_details = self.workload_details,
            plan= WorkloadPlan(
            method="DMR_max-loop_28",
            recommended_cpu_request=0.053,
            recommended_mem_request_and_limits_mi=15.0,
            recommended_cpu_limit_or_unbounded=1.0,
            recommended_min_replicas=30,
            recommended_max_replicas=630,
            recommended_hpa_target_cpu=0.77
        ),
        forecast_mem_saving_mi = 203.0,
        forecast_cpu_saving = 28.289
        )
        self.run_test_for_id("11", expected_rec, config)

    def test_hpa_simulation_12(self):
        config = self.workload_details.config
        config.set_value("EXTRA_HPA_BUFFER_FOR_MEMORY_RECOMMENDATION", 1.2)
        config.set_value("DISTANCE_BETWEEN_POINTS_SECONDS",30)
        config.set_value("EXTRA_HPA_BUFFER_FOR_CPU_USAGE_CAPACITY",1.20)
        config.set_value("EXTRA_HPA_BUFFER_FOR_MAX_REPLICAS",1.05)
        config.set_value("HPA_TARGET_BUFFER", 0.2)
        expected_rec = WorkloadRecommendation(
            workload_details = self.workload_details,
            plan= WorkloadPlan(
            method="DCR-65",
            recommended_cpu_request=0.048,
            recommended_mem_request_and_limits_mi=14.0,
            recommended_cpu_limit_or_unbounded=1.0,
            recommended_min_replicas=30,
            recommended_max_replicas=66,
            recommended_hpa_target_cpu=0.63
        ),
        forecast_mem_saving_mi = 1205.0,
        forecast_cpu_saving = 0.712
        )
        self.run_test_for_id("12", expected_rec, config)

    def test_hpa_simulation_13(self):
        config = self.workload_details.config
        config.set_value("EXTRA_HPA_BUFFER_FOR_MEMORY_RECOMMENDATION", 1.2)
        config.set_value("DISTANCE_BETWEEN_POINTS_SECONDS",60)
        config.set_value("EXTRA_HPA_BUFFER_FOR_CPU_USAGE_CAPACITY",1.00)
        #config.set_value("EXTRA_HPA_BUFFER_FOR_MAX_REPLICAS",1.05)
        config.set_value("HPA_TARGET_BUFFER", 0.0)
        expected_rec = WorkloadRecommendation(
            workload_details = self.workload_details,
            plan= WorkloadPlan(
            recommended_cpu_request=0.528,
            recommended_mem_request_and_limits_mi=42.0,
            recommended_cpu_limit_or_unbounded=1.0,
            recommended_min_replicas=5,
            recommended_max_replicas=5,
            recommended_hpa_target_cpu=1.0
        ),
        forecast_mem_saving_mi = 249.0,
        forecast_cpu_saving = 1.0
        )
        self.run_test_for_id("13", expected_rec, config)

    def test_hpa_simulation_14(self):
        config = self.workload_details.config
        config.set_value("EXTRA_HPA_BUFFER_FOR_MEMORY_RECOMMENDATION", 1.2)
        config.set_value("DISTANCE_BETWEEN_POINTS_SECONDS",60)
        config.set_value("EXTRA_HPA_BUFFER_FOR_CPU_USAGE_CAPACITY",1.20)
        config.set_value("EXTRA_HPA_BUFFER_FOR_MAX_REPLICAS",1.05)
        config.set_value("HPA_TARGET_BUFFER", 0.1)
        expected_rec = WorkloadRecommendation(
            workload_details = self.workload_details,
            plan= WorkloadPlan(
            recommended_cpu_request=0.097,
            recommended_mem_request_and_limits_mi=21.0,
            recommended_cpu_limit_or_unbounded=1.0,
            recommended_min_replicas=7,
            recommended_max_replicas=40,
            recommended_hpa_target_cpu=0.71
        ),
        forecast_mem_saving_mi = -66.0,
        forecast_cpu_saving = 1.242
        )
        self.run_test_for_id("14", expected_rec, config)

    def test_hpa_simulation_15(self):
        config = self.workload_details.config
        config.set_value("EXTRA_HPA_BUFFER_FOR_MEMORY_RECOMMENDATION", 1.2)
        config.set_value("DISTANCE_BETWEEN_POINTS_SECONDS",60)
        config.set_value("EXTRA_HPA_BUFFER_FOR_CPU_USAGE_CAPACITY",1.20)
        config.set_value("EXTRA_HPA_BUFFER_FOR_MAX_REPLICAS",1.05)
        config.set_value("HPA_TARGET_BUFFER", 0.2)
        expected_rec = WorkloadRecommendation(
            workload_details = self.workload_details,
            plan= WorkloadPlan(
            recommended_cpu_request=0.072,
            recommended_mem_request_and_limits_mi=15.0,
            recommended_cpu_limit_or_unbounded=1.0,
            recommended_min_replicas=20,
            recommended_max_replicas=146,
            recommended_hpa_target_cpu=0.79
        ),
        forecast_mem_saving_mi = 893.0,
        forecast_cpu_saving = 8.256
        )
        self.run_test_for_id("15", expected_rec, config)


if __name__ == "__main__":
    unittest.main()
