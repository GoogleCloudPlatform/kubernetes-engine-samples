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

func TestDaemonSetAPINotImplemented(t *testing.T) {
	yaml := `
apiVersion: apps/v1234
kind: DaemonSet
metadata:
  name: fluentd-elasticsearch
  namespace: kube-system
  labels:
    k8s-app: fluentd-logging
spec:
  selector:
    matchLabels:
      name: fluentd-elasticsearch
  template:
    metadata:
      labels:
        name: fluentd-elasticsearch
    spec:
      tolerations:
      # this toleration is to have the daemonset runnable on master nodes
      # remove it if your masters can't run pods
      - key: node-role.kubernetes.io/master
        effect: NoSchedule
      containers:
      - name: fluentd-elasticsearch
        image: quay.io/fluentd_elasticsearch/fluentd:v2.5.2
        resources:
          limits:
            memory: 200Mi
          requests:
            cpu: 100m
            memory: 200Mi
        volumeMounts:
        - name: varlog
          mountPath: /var/log
        - name: varlibdockercontainers
          mountPath: /var/lib/docker/containers
          readOnly: true
      terminationGracePeriodSeconds: 30
      volumes:
      - name: varlog
        hostPath:
          path: /var/log
      - name: varlibdockercontainers
        hostPath:
          path: /var/lib/docker/containers`

	_, err := decodeDaemonSet([]byte(yaml), CostimatorConfig{})
	if err == nil || !strings.HasPrefix(err.Error(), "Error Decoding.") {
		t.Error(fmt.Errorf("Should have return an APIVersion error, but returned '%+v'", err))
	}
}

func TestDaemonSetBasicV1(t *testing.T) {
	yaml := `
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: fluentd-elasticsearch
  namespace: kube-system
  labels:
    k8s-app: fluentd-logging
spec:
  selector:
    matchLabels:
      name: fluentd-elasticsearch
  template:
    metadata:
      labels:
        name: fluentd-elasticsearch
    spec:
      tolerations:
      # this toleration is to have the daemonset runnable on master nodes
      # remove it if your masters can't run pods
      - key: node-role.kubernetes.io/master
        effect: NoSchedule
      containers:
      - name: fluentd-elasticsearch
        image: quay.io/fluentd_elasticsearch/fluentd:v2.5.2
        resources:
          requests:
            memory: "64Mi"
            cpu: "250m"
          limits:
            memory: "64M"
            cpu: 1
        volumeMounts:
        - name: varlog
          mountPath: /var/log
        - name: varlibdockercontainers
          mountPath: /var/lib/docker/containers
          readOnly: true
      terminationGracePeriodSeconds: 30
      volumes:
      - name: varlog
        hostPath:
          path: /var/log
      - name: varlibdockercontainers
        hostPath:
          path: /var/lib/docker/containers`

	daemonset, err := decodeDaemonSet([]byte(yaml), CostimatorConfig{})
	if err != nil {
		t.Error(err)
		return
	}

	expectedAPIVersionKindName := "apps/v1|DaemonSet|kube-system|fluentd-elasticsearch"
	if got := daemonset.APIVersionKindName; got != expectedAPIVersionKindName {
		t.Errorf("Expected APIVersionKindName %+v, got %+v", expectedAPIVersionKindName, got)
	}

	expected := int32(3)
	if got := daemonset.NodesCount; got != expected {
		t.Errorf("Expected NodesCount %+v, got %+v", expected, got)
	}

	expectedRequestsCPU := int64(250)
	expectedRequestsMemory := int64(67108864)
	container := daemonset.Containers[0]
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

func TestDaemonSetBasicV1Beta1(t *testing.T) {
	yaml := `
apiVersion: apps/v1beta1
kind: DaemonSet
metadata:
  name: fluentd-elasticsearch
  namespace: kube-system
  labels:
    k8s-app: fluentd-logging
spec:
  selector:
    matchLabels:
      name: fluentd-elasticsearch
  template:
    metadata:
      labels:
        name: fluentd-elasticsearch
    spec:
      tolerations:
      # this toleration is to have the daemonset runnable on master nodes
      # remove it if your masters can't run pods
      - key: node-role.kubernetes.io/master
        effect: NoSchedule
      containers:
      - name: fluentd-elasticsearch
        image: quay.io/fluentd_elasticsearch/fluentd:v2.5.2
        resources:
          requests:
            memory: "64Mi"
            cpu: "250m"
          limits:
            memory: "64M"
            cpu: 1
        volumeMounts:
        - name: varlog
          mountPath: /var/log
        - name: varlibdockercontainers
          mountPath: /var/lib/docker/containers
          readOnly: true
      terminationGracePeriodSeconds: 30
      volumes:
      - name: varlog
        hostPath:
          path: /var/log
      - name: varlibdockercontainers
        hostPath:
          path: /var/lib/docker/containers`

	daemonset, err := decodeDaemonSet([]byte(yaml), CostimatorConfig{})
	if err != nil {
		t.Error(err)
		return
	}

	expectedAPIVersionKindName := "apps/v1beta1|DaemonSet|kube-system|fluentd-elasticsearch"
	if got := daemonset.APIVersionKindName; got != expectedAPIVersionKindName {
		t.Errorf("Expected APIVersionKindName %+v, got %+v", expectedAPIVersionKindName, got)
	}

	expected := int32(3)
	if got := daemonset.NodesCount; got != expected {
		t.Errorf("Expected NodesCount %+v, got %+v", expected, got)
	}

	expectedRequestsCPU := int64(250)
	expectedRequestsMemory := int64(67108864)
	container := daemonset.Containers[0]
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

func TestDaemonSetBasicV1Beta2(t *testing.T) {
	yaml := `
apiVersion: apps/v1beta2
kind: DaemonSet
metadata:
  name: fluentd-elasticsearch
  namespace: kube-system
  labels:
    k8s-app: fluentd-logging
spec:
  selector:
    matchLabels:
      name: fluentd-elasticsearch
  template:
    metadata:
      labels:
        name: fluentd-elasticsearch
    spec:
      tolerations:
      # this toleration is to have the daemonset runnable on master nodes
      # remove it if your masters can't run pods
      - key: node-role.kubernetes.io/master
        effect: NoSchedule
      containers:
      - name: fluentd-elasticsearch
        image: quay.io/fluentd_elasticsearch/fluentd:v2.5.2
        resources:
          requests:
            memory: "64Mi"
            cpu: "250m"
          limits:
            memory: "64M"
            cpu: 1
        volumeMounts:
        - name: varlog
          mountPath: /var/log
        - name: varlibdockercontainers
          mountPath: /var/lib/docker/containers
          readOnly: true
      terminationGracePeriodSeconds: 30
      volumes:
      - name: varlog
        hostPath:
          path: /var/log
      - name: varlibdockercontainers
        hostPath:
          path: /var/lib/docker/containers`

	daemonset, err := decodeDaemonSet([]byte(yaml), CostimatorConfig{})
	if err != nil {
		t.Error(err)
		return
	}

	expectedAPIVersionKindName := "apps/v1beta2|DaemonSet|kube-system|fluentd-elasticsearch"
	if got := daemonset.APIVersionKindName; got != expectedAPIVersionKindName {
		t.Errorf("Expected APIVersionKindName %+v, got %+v", expectedAPIVersionKindName, got)
	}

	expected := int32(3)
	if got := daemonset.NodesCount; got != expected {
		t.Errorf("Expected NodesCount %+v, got %+v", expected, got)
	}

	expectedRequestsCPU := int64(250)
	expectedRequestsMemory := int64(67108864)
	container := daemonset.Containers[0]
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

func TestDaemonSetNoResources(t *testing.T) {
	yaml := `
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: fluentd-elasticsearch
  namespace: kube-system
  labels:
    k8s-app: fluentd-logging
spec:
  selector:
    matchLabels:
      name: fluentd-elasticsearch
  template:
    metadata:
      labels:
        name: fluentd-elasticsearch
    spec:
      tolerations:
      # this toleration is to have the daemonset runnable on master nodes
      # remove it if your masters can't run pods
      - key: node-role.kubernetes.io/master
        effect: NoSchedule
      containers:
      - name: fluentd-elasticsearch
        image: quay.io/fluentd_elasticsearch/fluentd:v2.5.2
        volumeMounts:
        - name: varlog
          mountPath: /var/log
        - name: varlibdockercontainers
          mountPath: /var/lib/docker/containers
          readOnly: true
      terminationGracePeriodSeconds: 30
      volumes:
      - name: varlog
        hostPath:
          path: /var/log
      - name: varlibdockercontainers
        hostPath:
          path: /var/lib/docker/containers`

	daemonset, err := decodeDaemonSet([]byte(yaml), CostimatorConfig{})
	if err != nil {
		t.Error(err)
		return
	}

	expectedKey := "apps/v1|DaemonSet|kube-system|fluentd-elasticsearch"
	if got := daemonset.APIVersionKindName; got != expectedKey {
		t.Errorf("Expected Key %+v, got %+v", expectedKey, got)
	}

	expectedReplicas := int32(3)
	if got := daemonset.NodesCount; got != expectedReplicas {
		t.Errorf("Expected Replicas %+v, got %+v", expectedReplicas, got)
	}

	container := daemonset.Containers[0]
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

func TestDaemonSetNoLimits(t *testing.T) {
	yaml := `
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: fluentd-elasticsearch
  namespace: kube-system
  labels:
    k8s-app: fluentd-logging
spec:
  selector:
    matchLabels:
      name: fluentd-elasticsearch
  template:
    metadata:
      labels:
        name: fluentd-elasticsearch
    spec:
      tolerations:
      # this toleration is to have the daemonset runnable on master nodes
      # remove it if your masters can't run pods
      - key: node-role.kubernetes.io/master
        effect: NoSchedule
      containers:
      - name: fluentd-elasticsearch
        image: quay.io/fluentd_elasticsearch/fluentd:v2.5.2
        resources:
          requests:
            memory: "64M"
            cpu: "500m"
        volumeMounts:
        - name: varlog
          mountPath: /var/log
        - name: varlibdockercontainers
          mountPath: /var/lib/docker/containers
          readOnly: true
      terminationGracePeriodSeconds: 30
      volumes:
      - name: varlog
        hostPath:
          path: /var/log
      - name: varlibdockercontainers
        hostPath:
          path: /var/lib/docker/containers`

	daemonset, err := decodeDaemonSet([]byte(yaml), CostimatorConfig{})
	if err != nil {
		t.Error(err)
		return
	}

	expectedKey := "apps/v1|DaemonSet|kube-system|fluentd-elasticsearch"
	if got := daemonset.APIVersionKindName; got != expectedKey {
		t.Errorf("Expected Key %+v, got %+v", expectedKey, got)
	}

	container := daemonset.Containers[0]

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

func TestDaemonSetNoRequests(t *testing.T) {
	yaml := `
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: fluentd-elasticsearch
  namespace: kube-system
  labels:
    k8s-app: fluentd-logging
spec:
  selector:
    matchLabels:
      name: fluentd-elasticsearch
  template:
    metadata:
      labels:
        name: fluentd-elasticsearch
    spec:
      tolerations:
      # this toleration is to have the daemonset runnable on master nodes
      # remove it if your masters can't run pods
      - key: node-role.kubernetes.io/master
        effect: NoSchedule
      containers:
      - name: fluentd-elasticsearch
        image: quay.io/fluentd_elasticsearch/fluentd:v2.5.2
        resources:
          limits:
            memory: "64M"
            cpu: "500m"
        volumeMounts:
        - name: varlog
          mountPath: /var/log
        - name: varlibdockercontainers
          mountPath: /var/lib/docker/containers
          readOnly: true
      terminationGracePeriodSeconds: 30
      volumes:
      - name: varlog
        hostPath:
          path: /var/log
      - name: varlibdockercontainers
        hostPath:
          path: /var/lib/docker/containers`

	daemonset, err := decodeDaemonSet([]byte(yaml), CostimatorConfig{})
	if err != nil {
		t.Error(err)
		return
	}

	container := daemonset.Containers[0]
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

func TestDaemonSetManyContainers(t *testing.T) {
	yaml := `
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: fluentd-elasticsearch
  namespace: kube-system
  labels:
    k8s-app: fluentd-logging
spec:
  selector:
    matchLabels:
      name: fluentd-elasticsearch
  template:
    metadata:
      labels:
        name: fluentd-elasticsearch
    spec:
      tolerations:
      # this toleration is to have the daemonset runnable on master nodes
      # remove it if your masters can't run pods
      - key: node-role.kubernetes.io/master
        effect: NoSchedule
      containers:
      - name: kube-system|fluentd-elasticsearch
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
            cpu: "250m"
      terminationGracePeriodSeconds: 30
      volumes:
      - name: varlog
        hostPath:
          path: /var/log
      - name: varlibdockercontainers
        hostPath:
          path: /var/lib/docker/containers`

	daemonset, err := decodeDaemonSet([]byte(yaml), CostimatorConfig{})
	if err != nil {
		t.Error(err)
		return
	}

	if len(daemonset.Containers) != 2 {
		t.Errorf("Should have ignored initContainers")
	}

	expectedRequestsCPU := float64(0.5)
	expectedRequestsMemory := float64(134217728)
	cpuReq, _, memReq, _ := totalContainers(daemonset.Containers)
	if cpuReq != expectedRequestsCPU {
		t.Errorf("Expected Requests CPU %+v, got %+v", expectedRequestsCPU, cpuReq)
	}
	if memReq != expectedRequestsMemory {
		t.Errorf("Expected Requests Memory %+v, got %+v", expectedRequestsMemory, memReq)
	}
}
