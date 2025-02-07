// Copyright 2021 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package api

import (
	"fmt"
	"strings"
	"testing"
)

func TestReplicaSetAPINotImplemented(t *testing.T) {
	yaml := `
  apiVersion: apps/v1222
  kind: ReplicaSet
  metadata:
    name: frontend
  spec:
    replicas: 3
    selector:
      matchLabels:
        tier: frontend
    template:
      metadata:
        labels:
          tier: frontend
      spec:
        containers:
        - name: php-redis
          image: gcr.io/google_samples/gb-frontend:v3`

	_, err := decodeReplicaSet([]byte(yaml), CostimatorConfig{})
	if err == nil || !strings.HasPrefix(err.Error(), "Error Decoding.") {
		t.Error(fmt.Errorf("Should have return an APIVersion error, but returned '%+v'", err))
	}
}

func TestReplicaSetBasicV1(t *testing.T) {
	yaml := `
  apiVersion: apps/v1
  kind: ReplicaSet
  metadata:
    name: frontend
  spec:
    replicas: 3
    selector:
      matchLabels:
        tier: frontend
    template:
      metadata:
        labels:
          tier: frontend
      spec:
        containers:
        - name: php-redis
          image: gcr.io/google_samples/gb-frontend:v3
          resources:
            requests:
              memory: "64Mi"
              cpu: "250m"
            limits:
              memory: "64M"
              cpu: 1`

	replicaset, err := decodeReplicaSet([]byte(yaml), CostimatorConfig{})
	if err != nil {
		t.Error(err)
		return
	}

	expectedAPIVersionKindName := "apps/v1|ReplicaSet|default|frontend"
	if got := replicaset.APIVersionKindName; got != expectedAPIVersionKindName {
		t.Errorf("Expected APIVersionKindName %+v, got %+v", expectedAPIVersionKindName, got)
	}

	expectedKindName := "|ReplicaSet|default|frontend"
	if got := replicaset.getKindName(); got != expectedKindName {
		t.Errorf("Expected KindName %+v, got %+v", expectedKindName, got)
	}

	expected := int32(3)
	if got := replicaset.Replicas; got != expected {
		t.Errorf("Expected Replicas %+v, got %+v", expected, got)
	}

	expectedRequestsCPU := int64(250)
	expectedRequestsMemory := int64(67108864)
	container := replicaset.Containers[0]
	requests := container.Requests
	if requests.CPU != expectedRequestsCPU {
		t.Errorf("Expected Requests CPU %+v, got %+v", expectedRequestsCPU, requests.CPU)
	}
	if requests.Memory != expectedRequestsMemory {
		t.Errorf("Expected Requests Memory %+v, got %+v", expectedRequestsMemory, requests.Memory)
	}

	expectedLimitsCPU := int64(1000)
	expectedLimitsMemory := int64(64000000)
	limits := container.Limits
	if limits.CPU != expectedLimitsCPU {
		t.Errorf("Expected Limits CPU %+v, got %+v", expectedLimitsCPU, limits.CPU)
	}
	if limits.Memory != expectedLimitsMemory {
		t.Errorf("Expected Limits Memory %+v, got %+v", expectedLimitsMemory, limits.Memory)
	}

}

func TestReplicaSetBasicV1beta1(t *testing.T) {
	yaml := `
apiVersion: apps/v1beta1
kind: ReplicaSet
metadata:
  name: frontend
spec:
  replicas: 3
  selector:
    matchLabels:
      tier: frontend
  template:
    metadata:
      labels:
        tier: frontend
    spec:
      containers:
      - name: php-redis
        image: gcr.io/google_samples/gb-frontend:v3
        resources:
          requests:
            memory: "64Mi"
            cpu: "250m"
          limits:
            memory: "64M"
            cpu: 1`

	replicaset, err := decodeReplicaSet([]byte(yaml), CostimatorConfig{})
	if err != nil {
		t.Error(err)
		return
	}

	expectedAPIVersionKindName := "apps/v1beta1|ReplicaSet|default|frontend"
	if got := replicaset.APIVersionKindName; got != expectedAPIVersionKindName {
		t.Errorf("Expected APIVersionKindName %+v, got %+v", expectedAPIVersionKindName, got)
	}

	expectedKindName := "|ReplicaSet|default|frontend"
	if got := replicaset.getKindName(); got != expectedKindName {
		t.Errorf("Expected KindName %+v, got %+v", expectedKindName, got)
	}

	expected := int32(3)
	if got := replicaset.Replicas; got != expected {
		t.Errorf("Expected Replicas %+v, got %+v", expected, got)
	}

	expectedRequestsCPU := int64(250)
	expectedRequestsMemory := int64(67108864)
	container := replicaset.Containers[0]
	requests := container.Requests
	if requests.CPU != expectedRequestsCPU {
		t.Errorf("Expected Requests CPU %+v, got %+v", expectedRequestsCPU, requests.CPU)
	}
	if requests.Memory != expectedRequestsMemory {
		t.Errorf("Expected Requests Memory %+v, got %+v", expectedRequestsMemory, requests.Memory)
	}

	expectedLimitsCPU := int64(1000)
	expectedLimitsMemory := int64(64000000)
	limits := container.Limits
	if limits.CPU != expectedLimitsCPU {
		t.Errorf("Expected Limits CPU %+v, got %+v", expectedLimitsCPU, limits.CPU)
	}
	if limits.Memory != expectedLimitsMemory {
		t.Errorf("Expected Limits Memory %+v, got %+v", expectedLimitsMemory, limits.Memory)
	}

}

func TestReplicaSetBasicV1beta2(t *testing.T) {
	yaml := `
apiVersion: apps/v1beta2
kind: ReplicaSet
metadata:
  name: frontend
spec:
  replicas: 3
  selector:
    matchLabels:
      tier: frontend
  template:
    metadata:
      labels:
        tier: frontend
    spec:
      containers:
      - name: php-redis
        image: gcr.io/google_samples/gb-frontend:v3
        resources:
          requests:
            memory: "64Mi"
            cpu: "250m"
          limits:
            memory: "64M"
            cpu: 1`

	replicaset, err := decodeReplicaSet([]byte(yaml), CostimatorConfig{})
	if err != nil {
		t.Error(err)
		return
	}

	expectedAPIVersionKindName := "apps/v1beta2|ReplicaSet|default|frontend"
	if got := replicaset.APIVersionKindName; got != expectedAPIVersionKindName {
		t.Errorf("Expected APIVersionKindName %+v, got %+v", expectedAPIVersionKindName, got)
	}

	expectedKindName := "|ReplicaSet|default|frontend"
	if got := replicaset.getKindName(); got != expectedKindName {
		t.Errorf("Expected KindName %+v, got %+v", expectedKindName, got)
	}

	expected := int32(3)
	if got := replicaset.Replicas; got != expected {
		t.Errorf("Expected Replicas %+v, got %+v", expected, got)
	}

	expectedRequestsCPU := int64(250)
	expectedRequestsMemory := int64(67108864)
	container := replicaset.Containers[0]
	requests := container.Requests
	if requests.CPU != expectedRequestsCPU {
		t.Errorf("Expected Requests CPU %+v, got %+v", expectedRequestsCPU, requests.CPU)
	}
	if requests.Memory != expectedRequestsMemory {
		t.Errorf("Expected Requests Memory %+v, got %+v", expectedRequestsMemory, requests.Memory)
	}

	expectedLimitsCPU := int64(1000)
	expectedLimitsMemory := int64(64000000)
	limits := container.Limits
	if limits.CPU != expectedLimitsCPU {
		t.Errorf("Expected Limits CPU %+v, got %+v", expectedLimitsCPU, limits.CPU)
	}
	if limits.Memory != expectedLimitsMemory {
		t.Errorf("Expected Limits Memory %+v, got %+v", expectedLimitsMemory, limits.Memory)
	}

}

func TestReplicaSetNoReplicas(t *testing.T) {
	yaml := `
apiVersion: apps/v1
kind: ReplicaSet
metadata:
  name: frontend
spec:
  selector:
    matchLabels:
      tier: frontend
  template:
    metadata:
      labels:
        tier: frontend
    spec:
      containers:
      - name: php-redis
        image: gcr.io/google_samples/gb-frontend:v3`

	replicaset, err := decodeReplicaSet([]byte(yaml), CostimatorConfig{})
	if err != nil {
		t.Error(err)
		return
	}

	if got := replicaset.Replicas; got != 1 {
		t.Errorf("Expected 1 Replicas, got %+v", got)
	}
}

func TestReplicaSetNoResources(t *testing.T) {
	yaml := `
apiVersion: apps/v1
kind: ReplicaSet
metadata:
  name: frontend
spec:
  replicas: 3
  selector:
    matchLabels:
      tier: frontend
  template:
    metadata:
      labels:
        tier: frontend
    spec:
      containers:
      - name: php-redis
        image: gcr.io/google_samples/gb-frontend:v3`

	replicaset, err := decodeReplicaSet([]byte(yaml), CostimatorConfig{})
	if err != nil {
		t.Error(err)
		return
	}

	expectedKey := "apps/v1|ReplicaSet|default|frontend"
	if got := replicaset.APIVersionKindName; got != expectedKey {
		t.Errorf("Expected Key %+v, got %+v", expectedKey, got)
	}

	expectedReplicas := int32(3)
	if got := replicaset.Replicas; got != expectedReplicas {
		t.Errorf("Expected Replicas %+v, got %+v", expectedReplicas, got)
	}

	container := replicaset.Containers[0]
	defaults := ConfigDefaults()

	expectedRequestsCPU := defaults.ResourceConf.DefaultCPUinMillis
	expectedRequestsMemory := defaults.ResourceConf.DefaultMemoryinBytes
	requests := container.Requests
	if requests.CPU != expectedRequestsCPU {
		t.Errorf("Expected Requests CPU %+v, got %+v", expectedRequestsCPU, requests.CPU)
	}
	if requests.Memory != expectedRequestsMemory {
		t.Errorf("Expected Requests Memory %+v, got %+v", expectedRequestsMemory, requests.Memory)
	}

	expectedLimitsCPU := defaults.ResourceConf.DefaultCPUinMillis * 3
	expectedLimitsMemory := defaults.ResourceConf.DefaultMemoryinBytes * 3
	limits := container.Limits
	if limits.CPU != expectedLimitsCPU {
		t.Errorf("Expected Limits CPU %+v, got %+v", expectedLimitsCPU, limits.CPU)
	}
	if limits.Memory != expectedLimitsMemory {
		t.Errorf("Expected Limits Memory %+v, got %+v", expectedLimitsMemory, limits.Memory)
	}
}

func TestReplicaSetNoLimits(t *testing.T) {
	yaml := `
apiVersion: apps/v1
kind: ReplicaSet
metadata:
  name: frontend
spec:
  replicas: 3
  selector:
    matchLabels:
      tier: frontend
  template:
    metadata:
      labels:
        tier: frontend
    spec:
      containers:
      - name: php-redis
        image: gcr.io/google_samples/gb-frontend:v3
        resources:
          requests:
            memory: "64M"
            cpu: "500m"`

	replicaset, err := decodeReplicaSet([]byte(yaml), CostimatorConfig{})
	if err != nil {
		t.Error(err)
		return
	}

	container := replicaset.Containers[0]

	expectedRequestsCPU := int64(500)
	expectedRequestsMemory := int64(64000000)
	requests := container.Requests
	if requests.CPU != expectedRequestsCPU {
		t.Errorf("Expected Requests CPU %+v, got %+v", expectedRequestsCPU, requests.CPU)
	}
	if requests.Memory != expectedRequestsMemory {
		t.Errorf("Expected Requests Memory %+v, got %+v", expectedRequestsMemory, requests.Memory)
	}

	expectedLimitsCPU := expectedRequestsCPU * 3
	expectedLimitsMemory := expectedRequestsMemory * 3
	limits := container.Limits
	if limits.CPU != expectedLimitsCPU {
		t.Errorf("Expected Limits CPU %+v, got %+v", expectedLimitsCPU, limits.CPU)
	}
	if limits.Memory != expectedLimitsMemory {
		t.Errorf("Expected Limits Memory %+v, got %+v", expectedLimitsMemory, limits.Memory)
	}
}

func TestReplicaSetNoRequests(t *testing.T) {
	yaml := `
apiVersion: apps/v1
kind: ReplicaSet
metadata:
  name: frontend
spec:
  replicas: 3
  selector:
    matchLabels:
      tier: frontend
  template:
    metadata:
      labels:
        tier: frontend
    spec:
      containers:
      - name: php-redis
        image: gcr.io/google_samples/gb-frontend:v3
        resources:
          limits:
            memory: "64M"
            cpu: "500m"`

	replicaset, err := decodeReplicaSet([]byte(yaml), CostimatorConfig{})
	if err != nil {
		t.Error(err)
		return
	}

	container := replicaset.Containers[0]
	requests := container.Requests
	limits := container.Limits

	expectedLimitsCPU := int64(500)
	expectedLimitsMemory := int64(64000000)
	if requests.CPU != expectedLimitsCPU {
		t.Errorf("Expected Requests CPU %+v, got %+v", expectedLimitsCPU, requests.CPU)
	}
	if requests.Memory != expectedLimitsMemory {
		t.Errorf("Expected Requests Memory %+v, got %+v", expectedLimitsMemory, requests.Memory)
	}
	if limits.CPU != expectedLimitsCPU {
		t.Errorf("Expected Limits CPU %+v, got %+v", expectedLimitsCPU, limits.CPU)
	}
	if limits.Memory != expectedLimitsMemory {
		t.Errorf("Expected Limits Memory %+v, got %+v", expectedLimitsMemory, limits.Memory)
	}
}

func TestReplicaSetManyContainers(t *testing.T) {
	yaml := `
apiVersion: apps/v1
kind: ReplicaSet
metadata:
  name: frontend
spec:
  replicas: 3
  selector:
    matchLabels:
      tier: frontend
  template:
    metadata:
      labels:
        tier: frontend
    spec:
      containers:
      - name: my-nginx
        image: nginx
        resources:
          requests:
            memory: "64Mi"
            cpu: "250m"
      - name: busybox
        image: busybox
        resources:
          requests:
            memory: "64Mi"
            cpu: "250m"
      initContainers:
      - name: busybox
        image: busybox
        resources:
          requests:
            memory: "64Mi"
            cpu: "250m"`

	replicaset, err := decodeReplicaSet([]byte(yaml), CostimatorConfig{})
	if err != nil {
		t.Error(err)
		return
	}

	if len(replicaset.Containers) != 2 {
		t.Errorf("Should have ignored initContainers")
	}

	expectedRequestsCPU := float64(0.5)
	expectedRequestsMemory := float64(134217728)
	cpuReq, _, memReq, _ := totalContainers(replicaset.Containers)
	if cpuReq != expectedRequestsCPU {
		t.Errorf("Expected Requests CPU %+v, got %+v", expectedRequestsCPU, cpuReq)
	}
	if memReq != expectedRequestsMemory {
		t.Errorf("Expected Requests Memory %+v, got %+v", expectedRequestsMemory, memReq)
	}
}
