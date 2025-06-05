## Modules and Public Functions

### `get_workload_startup_time`

Calculates the total workload startup time, including processing time and
cluster autoscaler delays.

**Parameters:**

-   `_config`: Configuration object with run parameters.
-   `workload`: A `WorkloadDetails` object.

**Returns:** A `StartupTime` object representing startup time in seconds.

---

### `get_workload_agg_timeseries`

Fetches CPU and memory usage metrics for a GKE workload and returns them
as a grouped DataFrame.

**Parameters:**

-   `_config`: Configuration object.
-   `workload`: A `WorkloadDetails` object.
-   `start_datetime`: Start of the analysis period.
-   `end_datetime`: End of the analysis period.

**Returns:** A pandas DataFrame containing timeseries metrics.

---

### `get_simulation_plans`

Generates HPA or VPA recommendations using DMR and DCR algorithms.

**Parameters:**

-   `workload_df`: Timeseries DataFrame.
-   `workload_details`: Details of the GKE workload.

**Returns:** A list of `HPAWorkloadPlan` objects representing resource scaling
recommendations.

---

### `run_simulation_plan`

Runs the simulation based on the provided scaling plans.

**Parameters:**

-   `workload_df`: Timeseries DataFrame.
-   `workload_details`: Details of the workload.
-   `_plans`: List of `HPAWorkloadPlan` objects.

**Returns:** A tuple containing an analysis DataFrame and a
`RecommendationsSummary` object.

---

## Data Classes

### `WorkloadDetails`

Holds resource labels for querying Kubernetes workload assets.

**Attributes:**

-   `project_id`: GCP Project ID.
-   `cluster_name`: Kubernetes cluster name.
-   `location`: Cluster location (region or zone).
-   `namespace`: Namespace of the workload.
-   `controller_name`: Controller managing the workload.

---

### `HPAWorkloadPlan`

Represents simulation results and recommendations.

**Attributes:**

-   `method`: Recommendation algorithm (DMR or DCR).
-   `recommended_cpu_request`: Recommended CPU request.
-   `recommended_mem_request_and_limits_mi`: Recommended memory in MiB.
-   `recommended_min_replicas`: Minimum replicas.
-   `recommended_max_replicas`: Maximum replicas.
-   `recommended_target_cpu`: Target CPU utilization.

---

### `WorkloadRecommendations`

Summarizes simulation results, including cost savings.

**Attributes:**

-   `analysis_period_start`: Start of the analysis period.
-   `analysis_period_end`: End of the analysis period.
-   `recommendation`: Recommended configuration.
-   `min_replicas`: Minimum replicas observed.
-   `max_replicas`: Maximum replicas observed.
-   `avg_saving_in_cpus_1d_mean`: Average CPU savings per day.
