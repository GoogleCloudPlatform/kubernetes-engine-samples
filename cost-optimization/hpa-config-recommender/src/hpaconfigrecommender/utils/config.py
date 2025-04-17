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

""" Config settings for HPA, CA USER """
USER_AGENT = "cloud-solutions/gke-wa-hpa-recommender-v1"
class Config:
    """
    Configuration settings for HPA, CA, and other constants.
    Allows dynamic updates to the values.
    """
    
    # === Time & Processing Settings ===
    DISTANCE_BETWEEN_POINTS_SECONDS = 60
    DEFAULT_POD_STARTUPTIME = 60
    DEFAULT_HPA_PROCESSING_TIME = 45
    DEFAULT_CLUSTER_AUTOSCALER_STARTUP_TIME = 75
    
    # === HPA Simulation & Scaling ===
    HPA_SCALE_LIMIT = 2.3
    HPA_TARGET_BUFFER = 0.10
    HPA_SCALE_DOWN_DEFAULT_BEHAVIOUR_STEPS = 10
    EXTRA_HPA_BUFFER_FOR_MAX_REPLICAS = 1.00
    EXTRA_HPA_BUFFER_FOR_MEMORY_RECOMMENDATION = 1.05
    EXTRA_HPA_BUFFER_FOR_CPU_USAGE_CAPACITY = 1.05
    
    # === VPA Scaling ===
    EXTRA_VPA_BUFFER_FOR_MEMORY_RECOMMENDATION = 1.05
    EXTRA_VPA_BUFFER_FOR_CPU_USAGE_CAPACITY = 1.001
    
    # === CPU & Resource Limits ===
    MIN_CPU_CORE_PROPOSED_VALUE = 0.010
    COST_OF_GB_IN_CPUS = 7.5
    MCPU_ROUNDING = 3
    MIN_HPA_TARGET_CPU = 0.40
    MAX_HPA_TARGET_CPU = 1.00
    UNDERPROVISIONED_CPU_USAGE_THRESHOLD = 0.9
    
    # === Replica & Scaling Thresholds ===
    CPU_CLASH_COUNT_THRESHOLD = 0
    MIN_REC_REPLICAS = 3
    REPLICA_THRESHOLD = 50
    MIN_MAX_RATIO = 0.01  # The ratio of min/max replicas (1%)
    
    # === DCR (Dynamic Compute Resource) Settings ===
    MIN_DCR_PERCENTILE_VALUE = 10
    MAX_DCR_PERCENTILE_VALUE = 100
    
    # === Excluded Namespaces ===
    EXCLUDED_NAMESPACES = [
        "kube-system",
        "istio-system",
        "gatekeeper-system",
        "gke-system",
        "gmp-system",
        "gke-gmp-system",
        "gke-managed-filestorecsi",
        "gke-mcs",
    ]

    @classmethod
    def set_value(cls, name: str, value):
        """
        Set the value of a class variable.

        Args:
            name (str): The name of the class variable to update.
            value: The new value for the variable.
        """
        if hasattr(cls, name):
            setattr(cls, name, value)
        else:
            raise AttributeError(f"{name} is not a valid configuration option.")

    @classmethod
    def get_value(cls, name: str):
        """
        Get the value of a class variable.

        Args:
            name (str): The name of the class variable.

        Returns:
            The value of the class variable.
        """
        if hasattr(cls, name):
            return getattr(cls, name)
        else:
            raise AttributeError(f"{name} is not a valid configuration option.")

    @classmethod
    def log_all_constants(cls) -> str:
        """
        Returns all constants as a formatted string.

        Returns:
            str: A string containing all constants with their names and values.
        """
        constants_list = []
        constants_list.append("===== Configs =====\n")
        for name in dir(cls):
            if name.isupper():  # Filter only constants (uppercase variables)
                value = getattr(cls, name)
                constants_list.append(f"{name}: {value}")
        return "\n".join(constants_list)

    @classmethod
    def add_excluded_namespaces(cls, namespaces: str):
        """
        Adds namespaces to the EXCLUDED_NAMESPACES list.
        Takes a comma-separated string and adds each namespace if it doesn't
        already exist.

        Args:
            namespaces (str): A comma-separated string of namespaces to add to
            the exclusion list.
        """
        for namespace in namespaces.split(","):
            namespace = namespace.strip()
            if namespace and namespace not in cls.EXCLUDED_NAMESPACES:
                cls.EXCLUDED_NAMESPACES.append(namespace)
            elif namespace in cls.EXCLUDED_NAMESPACES:
                print(f"'{namespace}' is already in the exclusion list.")
