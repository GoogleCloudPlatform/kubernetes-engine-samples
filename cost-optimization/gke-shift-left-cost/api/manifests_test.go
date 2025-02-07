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
	"testing"

	"github.com/google/go-cmp/cmp"
)

func TestManifests(t *testing.T) {
	data := `apiVersion: autoscaling/v2beta2
kind: HorizontalPodAutoscaler
metadata:
  name: php-apache
spec:
  maxReplicas: 20
  minReplicas: 10
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: php-apache
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 60
---
apiVersion: apps/v1beta1
kind: Deployment
metadata:
  name: my-nginx
spec:
  template:
    metadata:
      labels:
        run: my-nginx
    spec:
      containers:
      - name: my-nginx
      image: nginx
      ports:
        - containerPort: 80
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: my-config
---
anythingelse: not-a-k8s-object`

	manifests := Manifests{}
	manifests.LoadObjects([]byte(data), CostimatorConfig{})

	if len(manifests.Deployments) != 1 || len(manifests.hpas) != 1 {
		t.Errorf("Incorrect number of objectx")
	}
}

func TestPrepareForCostEstimation(t *testing.T) {
	data := `apiVersion: autoscaling/v2beta2
kind: HorizontalPodAutoscaler
metadata:
  name: my-nginx
spec:
  maxReplicas: 20
  minReplicas: 10
  scaleTargetRef:
    kind: Deployment
    name: my-nginx
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 60
---
apiVersion: apps/v1beta1
kind: Deployment
metadata:
  name: my-nginx
spec:
  template:
    metadata:
      labels:
        run: my-nginx
    spec:
      containers:
      - name: my-nginx
      image: nginx
      ports:
        - containerPort: 80`

	manifests := Manifests{}
	manifests.LoadObjects([]byte(data), CostimatorConfig{})
	manifests.prepareForCostEstimation()

	deploy := *manifests.Deployments[0]
	if deploy.hpa.TargetCPUPercentage != 60 {
		t.Errorf("Should have linked HPA to Deployment")
	}
}

func TestLoadObjectsFromPath(t *testing.T) {
	manifests := Manifests{}
	manifests.LoadObjectsFromPath("./testdata/manifests/", CostimatorConfig{})
	if len(manifests.Deployments) != 2 || len(manifests.hpas) != 1 {
		t.Errorf("Incorrect number of objectx")
	}
}

func TestEstimateCost(t *testing.T) {
	data := `apiVersion: autoscaling/v2beta2
kind: HorizontalPodAutoscaler
metadata:
  name: my-nginx
spec:
  maxReplicas: 20
  minReplicas: 10
  scaleTargetRef:
    kind: Deployment
    name: my-nginx
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 60
---
apiVersion: apps/v1beta1
kind: Deployment
metadata:
  name: my-nginx
spec:
  template:
    metadata:
      labels:
        run: my-nginx
    spec:
      containers:
      - name: my-nginx
        image: nginx
        ports:
        - containerPort: 80
        resources:
          requests:
            memory: "8Gi"
            cpu: "2"`

	manifests := Manifests{}
	err := manifests.LoadObjects([]byte(data), CostimatorConfig{})
	if err != nil {
		t.Errorf("Error loading objects: %+v", err)
	}

	mock := GCPPriceCatalog{cpuPrice: 16.227823, memoryPrice: 2.0257258e-09}
	cost := manifests.EstimateCost(mock)

	actualTotal := cost.MonthlyTotal()
	expectedTotal := CostRange{
		Kind:         "MonthlyTotal",
		MinRequested: 498.5649871826172,
		MaxRequested: 997.1299743652344,
		HPABuffer:    697.9909820556641,
		MinLimited:   1495.6949615478516,
		MaxLimited:   2991.389923095703,
	}
	if !cmp.Equal(actualTotal, expectedTotal) {
		t.Errorf("MonthlyTotal should be equal, expected: %+v, got: %+v", expectedTotal, actualTotal)
	}
}

func TestEstimateCostWithoutTargetUtilizaiton(t *testing.T) {
	data := `apiVersion: autoscaling/v2beta2
kind: HorizontalPodAutoscaler
metadata:
  name: my-nginx
spec:
  maxReplicas: 20
  minReplicas: 10
  scaleTargetRef:
    kind: Deployment
    name: my-nginx
---
apiVersion: apps/v1beta1
kind: Deployment
metadata:
  name: my-nginx
spec:
  template:
    metadata:
      labels:
        run: my-nginx
    spec:
      containers:
      - name: my-nginx
        image: nginx
        ports:
        - containerPort: 80
        resources:
          requests:
            memory: "8Gi"
            cpu: "2"`

	manifests := Manifests{}
	err := manifests.LoadObjects([]byte(data), CostimatorConfig{})
	if err != nil {
		t.Errorf("Error loading objects: %+v", err)
	}

	mock := GCPPriceCatalog{cpuPrice: 16.227823, memoryPrice: 2.0257258e-09}
	cost := manifests.EstimateCost(mock)

	actualTotal := cost.MonthlyTotal()
	expectedTotal := CostRange{
		Kind:         "MonthlyTotal",
		MinRequested: 498.5649871826172,
		MaxRequested: 997.1299743652344,
		HPABuffer:    498.5649871826172,
		MinLimited:   1495.6949615478516,
		MaxLimited:   2991.389923095703,
	}
	if !cmp.Equal(actualTotal, expectedTotal) {
		t.Errorf("MonthlyTotal should be equal, expected: %+v, got: %+v", expectedTotal, actualTotal)
	}
}

func TestEstimateCostManyDeployments(t *testing.T) {
	data := `apiVersion: autoscaling/v2beta2
kind: HorizontalPodAutoscaler
metadata:
  name: my-nginx
spec:
  maxReplicas: 20
  minReplicas: 10
  scaleTargetRef:
    kind: Deployment
    name: my-nginx
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 60
---
apiVersion: apps/v1beta1
kind: Deployment
metadata:
  name: my-nginx
spec:
  template:
    metadata:
      labels:
        run: my-nginx
    spec:
      containers:
      - name: my-nginx
        image: nginx
        ports:
        - containerPort: 80
        resources:
          requests:
            memory: "8Gi"
            cpu: "2"
---
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
        image: gcr.io/google_samples/gb-frontend:v3
        resources:
          requests:
            memory: "8Gi"
            cpu: "2"`

	manifests := Manifests{}
	err := manifests.LoadObjects([]byte(data), CostimatorConfig{})
	if err != nil {
		t.Errorf("Error loading objects: %+v", err)
	}

	mock := GCPPriceCatalog{cpuPrice: 16.227823, memoryPrice: 2.0257258e-09}
	cost := manifests.EstimateCost(mock)

	actualTotal := cost.MonthlyTotal()
	expectedTotal := CostRange{
		Kind:         "MonthlyTotal",
		MinRequested: 498.5649871826172 + 49.85649871826172,
		MaxRequested: 997.1299743652344 + 49.85649871826172,
		HPABuffer:    697.9909820556641 + 49.85649871826172,
		MinLimited:   1495.6949615478516 + (49.85649871826172 * 3),
		MaxLimited:   2991.389923095703 + (49.85649871826172 * 3),
	}
	if !cmp.Equal(actualTotal, expectedTotal) {
		t.Errorf("MonthlyTotal should be equal, expected: %+v, got: %+v", expectedTotal, actualTotal)
	}
}
