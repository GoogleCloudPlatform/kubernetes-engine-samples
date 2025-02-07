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

func TestStatefulSetAPINotImplemented(t *testing.T) {
	yaml := `
apiVersion: apps/v1222
kind: StatefulSet
metadata:
  name: my-nginx
spec:
  selector:
    matchLabels:
      app: nginx # has to match .spec.template.metadata.labels
  serviceName: "nginx"
  replicas: 3 # by default is 1
  template:
    metadata:
      labels:
        app: nginx # has to match .spec.selector.matchLabels
    spec:
      terminationGracePeriodSeconds: 10
      containers:
      - name: nginx
        image: k8s.gcr.io/nginx-slim:0.8
        ports:
        - containerPort: 80
          name: my-nginx
        volumeMounts:
        - name: www
          mountPath: /usr/share/nginx/html
  volumeClaimTemplates:
  - metadata:
      name: www
    spec:
      accessModes: [ "ReadWriteOnce" ]
      storageClassName: "my-storage-class"
      resources:
        requests:
          storage: 1Gi`

	_, err := decodeStatefulSet([]byte(yaml), CostimatorConfig{})
	if err == nil || !strings.HasPrefix(err.Error(), "Error Decoding.") {
		t.Error(fmt.Errorf("Should have return an APIVersion error, but returned '%+v'", err))
	}
}

func TestStatefulSetBasicV1(t *testing.T) {
	yaml := `
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: my-nginx
spec:
  selector:
    matchLabels:
      app: nginx # has to match .spec.template.metadata.labels
  serviceName: "nginx"
  replicas: 4 # by default is 1
  template:
    metadata:
      labels:
        app: nginx # has to match .spec.selector.matchLabels
    spec:
      terminationGracePeriodSeconds: 10
      containers:
      - name: nginx
        image: k8s.gcr.io/nginx-slim:0.8
        ports:
        - containerPort: 80
          name: my-nginx
        volumeMounts:
        - name: www
          mountPath: /usr/share/nginx/html
        resources:
          requests:
            memory: "64Mi"
            cpu: "250m"
          limits:
            memory: "64M"
            cpu: 1          
  volumeClaimTemplates:
  - metadata:
      name: www
    spec:
      accessModes: [ "ReadWriteOnce" ]
      storageClassName: "my-storage-class"
      resources:
        requests:
          storage: 1Gi`

	deploy, err := decodeStatefulSet([]byte(yaml), CostimatorConfig{})
	if err != nil {
		t.Error(err)
		return
	}

	expectedAPIVersionKindName := "apps/v1|StatefulSet|default|my-nginx"
	if got := deploy.APIVersionKindName; got != expectedAPIVersionKindName {
		t.Errorf("Expected APIVersionKindName %+v, got %+v", expectedAPIVersionKindName, got)
	}

	expectedKindName := "|StatefulSet|default|my-nginx"
	if got := deploy.getKindName(); got != expectedKindName {
		t.Errorf("Expected KindName %+v, got %+v", expectedKindName, got)
	}

	expected := int32(4)
	if got := deploy.Replicas; got != expected {
		t.Errorf("Expected Replicas %+v, got %+v", expected, got)
	}

	expectedRequestsCPU := int64(250)
	expectedRequestsMemory := int64(67108864)
	container := deploy.Containers[0]
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

func TestStatefulSetBasicV1beta1(t *testing.T) {
	yaml := `
apiVersion: apps/v1beta1
kind: StatefulSet
metadata:
  name: my-nginx
spec:
  selector:
    matchLabels:
      app: nginx # has to match .spec.template.metadata.labels
  serviceName: "nginx"
  replicas: 4 # by default is 1
  template:
    metadata:
      labels:
        app: nginx # has to match .spec.selector.matchLabels
    spec:
      terminationGracePeriodSeconds: 10
      containers:
      - name: nginx
        image: k8s.gcr.io/nginx-slim:0.8
        ports:
        - containerPort: 80
          name: my-nginx
        volumeMounts:
        - name: www
          mountPath: /usr/share/nginx/html
        resources:
          requests:
            memory: "64Mi"
            cpu: "250m"
          limits:
            memory: "64M"
            cpu: 1          
  volumeClaimTemplates:
  - metadata:
      name: www
    spec:
      accessModes: [ "ReadWriteOnce" ]
      storageClassName: "my-storage-class"
      resources:
        requests:
          storage: 1Gi`

	deploy, err := decodeStatefulSet([]byte(yaml), CostimatorConfig{})
	if err != nil {
		t.Error(err)
		return
	}

	expectedAPIVersionKindName := "apps/v1beta1|StatefulSet|default|my-nginx"
	if got := deploy.APIVersionKindName; got != expectedAPIVersionKindName {
		t.Errorf("Expected APIVersionKindName %+v, got %+v", expectedAPIVersionKindName, got)
	}

	expectedKindName := "|StatefulSet|default|my-nginx"
	if got := deploy.getKindName(); got != expectedKindName {
		t.Errorf("Expected KindName %+v, got %+v", expectedKindName, got)
	}

	expected := int32(4)
	if got := deploy.Replicas; got != expected {
		t.Errorf("Expected Replicas %+v, got %+v", expected, got)
	}

	expectedRequestsCPU := int64(250)
	expectedRequestsMemory := int64(67108864)
	container := deploy.Containers[0]
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

func TestStatefulSetBasicV1beta2(t *testing.T) {
	yaml := `
apiVersion: apps/v1beta2
kind: StatefulSet
metadata:
  name: my-nginx
spec:
  selector:
    matchLabels:
      app: nginx # has to match .spec.template.metadata.labels
  serviceName: "nginx"
  replicas: 4 # by default is 1
  template:
    metadata:
      labels:
        app: nginx # has to match .spec.selector.matchLabels
    spec:
      terminationGracePeriodSeconds: 10
      containers:
      - name: nginx
        image: k8s.gcr.io/nginx-slim:0.8
        ports:
        - containerPort: 80
          name: my-nginx
        volumeMounts:
        - name: www
          mountPath: /usr/share/nginx/html
        resources:
          requests:
            memory: "64Mi"
            cpu: "250m"
          limits:
            memory: "64M"
            cpu: 1          
  volumeClaimTemplates:
  - metadata:
      name: www
    spec:
      accessModes: [ "ReadWriteOnce" ]
      storageClassName: "my-storage-class"
      resources:
        requests:
          storage: 1Gi`

	deploy, err := decodeStatefulSet([]byte(yaml), CostimatorConfig{})
	if err != nil {
		t.Error(err)
		return
	}

	expectedAPIVersionKindName := "apps/v1beta2|StatefulSet|default|my-nginx"
	if got := deploy.APIVersionKindName; got != expectedAPIVersionKindName {
		t.Errorf("Expected APIVersionKindName %+v, got %+v", expectedAPIVersionKindName, got)
	}

	expectedKindName := "|StatefulSet|default|my-nginx"
	if got := deploy.getKindName(); got != expectedKindName {
		t.Errorf("Expected KindName %+v, got %+v", expectedKindName, got)
	}

	expected := int32(4)
	if got := deploy.Replicas; got != expected {
		t.Errorf("Expected Replicas %+v, got %+v", expected, got)
	}

	expectedRequestsCPU := int64(250)
	expectedRequestsMemory := int64(67108864)
	container := deploy.Containers[0]
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

func TestStatefulSetNoReplicas(t *testing.T) {
	yaml := `
apiVersion: apps/v1beta1
kind: StatefulSet
metadata:
  name: my-nginx
spec:
  selector:
    matchLabels:
      app: nginx # has to match .spec.template.metadata.labels
  serviceName: "nginx"
  template:
    metadata:
      labels:
        app: nginx # has to match .spec.selector.matchLabels
    spec:
      terminationGracePeriodSeconds: 10
      containers:
      - name: nginx
        image: k8s.gcr.io/nginx-slim:0.8
        ports:
        - containerPort: 80
          name: my-nginx
        volumeMounts:
        - name: www
          mountPath: /usr/share/nginx/html
        resources:
          requests:
            memory: "64Mi"
            cpu: "250m"
          limits:
            memory: "64M"
            cpu: 1          
  volumeClaimTemplates:
  - metadata:
      name: www
    spec:
      accessModes: [ "ReadWriteOnce" ]
      storageClassName: "my-storage-class"
      resources:
        requests:
          storage: 1Gi`

	deploy, err := decodeStatefulSet([]byte(yaml), CostimatorConfig{})
	if err != nil {
		t.Error(err)
		return
	}

	if got := deploy.Replicas; got != 1 {
		t.Errorf("Expected 1 Replicas, got %+v", got)
	}
}

func TestStatefulSetNoResources(t *testing.T) {
	yaml := `
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: my-nginx
spec:
  selector:
    matchLabels:
      app: nginx # has to match .spec.template.metadata.labels
  serviceName: "nginx"
  replicas: 2 # by default is 1
  template:
    metadata:
      labels:
        app: nginx # has to match .spec.selector.matchLabels
    spec:
      terminationGracePeriodSeconds: 10
      containers:
      - name: nginx
        image: k8s.gcr.io/nginx-slim:0.8
        ports:
        - containerPort: 80
          name: my-nginx
        volumeMounts:
        - name: www
          mountPath: /usr/share/nginx/html        
  volumeClaimTemplates:
  - metadata:
      name: www
    spec:
      accessModes: [ "ReadWriteOnce" ]
      storageClassName: "my-storage-class"
      resources:
        requests:
          storage: 1Gi`

	deploy, err := decodeStatefulSet([]byte(yaml), CostimatorConfig{})
	if err != nil {
		t.Error(err)
		return
	}

	expectedKey := "apps/v1|StatefulSet|default|my-nginx"
	if got := deploy.APIVersionKindName; got != expectedKey {
		t.Errorf("Expected Key %+v, got %+v", expectedKey, got)
	}

	expectedReplicas := int32(2)
	if got := deploy.Replicas; got != expectedReplicas {
		t.Errorf("Expected Replicas %+v, got %+v", expectedReplicas, got)
	}

	container := deploy.Containers[0]
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

func TestStatefulSetNoLimits(t *testing.T) {
	yaml := `
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: my-nginx
spec:
  selector:
    matchLabels:
      app: nginx # has to match .spec.template.metadata.labels
  serviceName: "nginx"
  replicas: 2 # by default is 1
  template:
    metadata:
      labels:
        app: nginx # has to match .spec.selector.matchLabels
    spec:
      terminationGracePeriodSeconds: 10
      containers:
      - name: nginx
        image: k8s.gcr.io/nginx-slim:0.8
        ports:
        - containerPort: 80
          name: my-nginx
        volumeMounts:
        - name: www
          mountPath: /usr/share/nginx/html
        resources:
          requests:
            memory: "64M"
            cpu: "500m"         
  volumeClaimTemplates:
  - metadata:
      name: www
    spec:
      accessModes: [ "ReadWriteOnce" ]
      storageClassName: "my-storage-class"
      resources:
        requests:
          storage: 1Gi`

	deploy, err := decodeStatefulSet([]byte(yaml), CostimatorConfig{})
	if err != nil {
		t.Error(err)
		return
	}

	expectedKey := "apps/v1|StatefulSet|default|my-nginx"
	if got := deploy.APIVersionKindName; got != expectedKey {
		t.Errorf("Expected Key %+v, got %+v", expectedKey, got)
	}

	expectedReplicas := int32(2)
	if got := deploy.Replicas; got != expectedReplicas {
		t.Errorf("Expected Replicas %+v, got %+v", expectedReplicas, got)
	}

	container := deploy.Containers[0]

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

func TestStatefulSetNoRequests(t *testing.T) {
	yaml := `
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: my-nginx
spec:
  selector:
    matchLabels:
      app: nginx # has to match .spec.template.metadata.labels
  serviceName: "nginx"
  replicas: 2 # by default is 1
  template:
    metadata:
      labels:
        app: nginx # has to match .spec.selector.matchLabels
    spec:
      terminationGracePeriodSeconds: 10
      containers:
      - name: nginx
        image: k8s.gcr.io/nginx-slim:0.8
        ports:
        - containerPort: 80
          name: my-nginx
        volumeMounts:
        - name: www
          mountPath: /usr/share/nginx/html
        resources:
          limits:
            memory: "64M"
            cpu: "500m"         
  volumeClaimTemplates:
  - metadata:
      name: www
    spec:
      accessModes: [ "ReadWriteOnce" ]
      storageClassName: "my-storage-class"
      resources:
        requests:
          storage: 1Gi`

	deploy, err := decodeStatefulSet([]byte(yaml), CostimatorConfig{})
	if err != nil {
		t.Error(err)
		return
	}

	container := deploy.Containers[0]
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

func TestStatefulSetManyContainers(t *testing.T) {
	yaml := `
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: my-nginx
spec:
  selector:
    matchLabels:
      app: nginx # has to match .spec.template.metadata.labels
  serviceName: "nginx"
  replicas: 3 # by default is 1
  template:
    metadata:
      labels:
        app: nginx # has to match .spec.selector.matchLabels
    spec:
      terminationGracePeriodSeconds: 10
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
            cpu: "250m"       
  volumeClaimTemplates:
  - metadata:
      name: www
    spec:
      accessModes: [ "ReadWriteOnce" ]
      storageClassName: "my-storage-class"
      resources:
        requests:
          storage: 1Gi`

	deploy, err := decodeStatefulSet([]byte(yaml), CostimatorConfig{})
	if err != nil {
		t.Error(err)
		return
	}

	if len(deploy.Containers) != 2 {
		t.Errorf("Should have ignored initContainers")
	}

	expectedRequestsCPU := float64(0.5)
	expectedRequestsMemory := float64(134217728)
	cpuReq, _, memReq, _ := totalContainers(deploy.Containers)
	if cpuReq != expectedRequestsCPU {
		t.Errorf("Expected Requests CPU %+v, got %+v", expectedRequestsCPU, cpuReq)
	}
	if memReq != expectedRequestsMemory {
		t.Errorf("Expected Requests Memory %+v, got %+v", expectedRequestsMemory, memReq)
	}
}

func TestStatefulSetVolumeClaimTemplates(t *testing.T) {
	yaml := `
  apiVersion: apps/v1
  kind: StatefulSet
  metadata:
    name: mysql
  spec:
    selector:
      matchLabels:
        app: mysql
    serviceName: mysql
    replicas: 3
    template:
      metadata:
        labels:
          app: mysql
      spec:
        containers:
        - name: mysql
          image: mysql:5.7          
          volumeMounts:
          - name: data
            mountPath: /var/lib/mysql
            subPath: mysql
          - name: conf
            mountPath: /etc/mysql/conf.d
          resources:
            requests:
              cpu: 100m
              memory: 100Mi
        volumes:
        - name: conf
          emptyDir: {}
        - name: config-map
          configMap:
            name: mysql
    volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: ["ReadWriteOnce"]
        resources:
          requests:
            storage: 10Gi
  `

	deploy, err := decodeStatefulSet([]byte(yaml), CostimatorConfig{})
	if err != nil {
		t.Error(err)
		return
	}

	volume := deploy.VolumeClaims[0]

	expectedAPIVersionKindName := "|PersistentVolumeClaim|default|data"
	if got := volume.APIVersionKindName; got != expectedAPIVersionKindName {
		t.Errorf("Expected APIVersionKindName %+v, got %+v", expectedAPIVersionKindName, got)
	}

	if got := volume.StorageClass; got != storageClassStandard {
		t.Errorf("Expected StorageClassName %+v, got %+v", storageClassStandard, got)
	}

	expectedStorage := int64(10737418240)
	requests := volume.Requests
	if got := requests.Storage; got != expectedStorage {
		t.Errorf("Expected Requests Storage %+v, got %+v", expectedStorage, got)
	}
	limits := volume.Limits
	if got := limits.Storage; got != expectedStorage {
		t.Errorf("Expected Limits Storage %+v, got %+v", expectedStorage, got)
	}
}
