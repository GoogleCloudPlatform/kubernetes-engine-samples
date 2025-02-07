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
	"bytes"
	"fmt"
	"io/ioutil"
	"strings"
	"testing"
)

func TestHPAAPINotImplemented(t *testing.T) {
	yaml := `apiVersion: autoscaling/V10000
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
        averageUtilization: 60`

	_, err := decodeHPA([]byte(yaml))
	if err == nil || !strings.HasPrefix(err.Error(), "Error Decoding.") {
		t.Error(fmt.Errorf("Should have return an APIVersion error, but returned '%+v'", err))
	}
}

func TestHPABasicV2beta2(t *testing.T) {
	yaml := `apiVersion: autoscaling/v2beta2
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
        averageUtilization: 60`

	hpa, err := decodeHPA([]byte(yaml))
	if err != nil {
		t.Error(err)
		return
	}

	expectedKey := "autoscaling/v2beta2|HorizontalPodAutoscaler|default|php-apache"
	if got := hpa.APIVersionKindName; got != expectedKey {
		t.Errorf("Expected Key %+v, got %+v", expectedKey, got)
	}

	expectedRef := "apps/v1|Deployment|default|php-apache"
	if got := hpa.TargetRef; got != expectedRef {
		t.Errorf("Expected Target referency %+v, got %+v", expectedRef, got)
	}

	expectedMinReplicas := int32(10)
	if got := hpa.MinReplicas; got != expectedMinReplicas {
		t.Errorf("Expected Min Replicas %+v, got %+v", expectedMinReplicas, got)
	}

	expectedMaxReplicas := int32(20)
	if got := hpa.MaxReplicas; got != expectedMaxReplicas {
		t.Errorf("Expected Max Replicas %+v, got %+v", expectedMaxReplicas, got)
	}

	expectedCPU := int32(60)
	if got := hpa.TargetCPUPercentage; got != expectedCPU {
		t.Errorf("Expected target CPU %+v, got %+v", expectedCPU, got)
	}
}

func TestHPANoMinReplicasV2beta2(t *testing.T) {
	yaml := `apiVersion: autoscaling/v2beta2
kind: HorizontalPodAutoscaler
metadata:
  name: php-apache
spec:
  maxReplicas: 20
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
        averageUtilization: 60`

	hpa, err := decodeHPA([]byte(yaml))
	if err != nil {
		t.Error(err)
		return
	}

	expectedMinReplicas := int32(1)
	if got := hpa.MinReplicas; got != expectedMinReplicas {
		t.Errorf("Expected Min Replicas %+v, got %+v", expectedMinReplicas, got)
	}
}

func TestHPANoTargetCPUV2beta2(t *testing.T) {
	yaml := `apiVersion: autoscaling/v2beta2
kind: HorizontalPodAutoscaler
metadata:
  name: php-apache
spec:
  maxReplicas: 20
  minReplicas: 10
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: php-apache`

	hpa, _ := decodeHPA([]byte(yaml))
	if hpa.TargetCPUPercentage != 0 {
		t.Error("Target CPU should be zero")
	}
}

func TestHPABasicV2beta1(t *testing.T) {
	yaml := `
apiVersion: autoscaling/v2beta1
kind: HorizontalPodAutoscaler
metadata:
  name: frontend-scaler
spec:
  scaleTargetRef:
    kind: Deployment
    name: frobinator-frontend
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      targetAverageUtilization: 80`

	hpa, err := decodeHPA([]byte(yaml))
	if err != nil {
		t.Error(err)
		return
	}

	expectedKey := "autoscaling/v2beta1|HorizontalPodAutoscaler|default|frontend-scaler"
	if got := hpa.APIVersionKindName; got != expectedKey {
		t.Errorf("Expected Key %+v, got %+v", expectedKey, got)
	}

	expectedRef := "|Deployment|default|frobinator-frontend"
	if got := hpa.TargetRef; got != expectedRef {
		t.Errorf("Expected Target referency %+v, got %+v", expectedRef, got)
	}

	expectedMinReplicas := int32(2)
	if got := hpa.MinReplicas; got != expectedMinReplicas {
		t.Errorf("Expected Min Replicas %+v, got %+v", expectedMinReplicas, got)
	}

	expectedMaxReplicas := int32(10)
	if got := hpa.MaxReplicas; got != expectedMaxReplicas {
		t.Errorf("Expected Max Replicas %+v, got %+v", expectedMaxReplicas, got)
	}

	expectedCPU := int32(80)
	if got := hpa.TargetCPUPercentage; got != expectedCPU {
		t.Errorf("Expected target CPU %+v, got %+v", expectedCPU, got)
	}
}

func TestHPANoMinReplicasV2beta1(t *testing.T) {
	yaml := `apiVersion: autoscaling/v2beta1
kind: HorizontalPodAutoscaler
metadata:
  name: php-apache
spec:
  maxReplicas: 20
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: php-apache
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        targetAverageUtilization: 80`

	hpa, err := decodeHPA([]byte(yaml))
	if err != nil {
		t.Error(err)
		return
	}

	expectedMinReplicas := int32(1)
	if got := hpa.MinReplicas; got != expectedMinReplicas {
		t.Errorf("Expected Min Replicas %+v, got %+v", expectedMinReplicas, got)
	}
}

func TestHPANoTargetCPUVV2Beta1(t *testing.T) {
	yaml := `apiVersion: autoscaling/v2beta1
kind: HorizontalPodAutoscaler
metadata:
  name: php-apache
spec:
  maxReplicas: 20
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: php-apache
  maxReplicas: 10`

	hpa, _ := decodeHPA([]byte(yaml))
	if hpa.TargetCPUPercentage != 0 {
		t.Error("Target CPU should be zero")
	}
}

func TestHPABasicV1(t *testing.T) {
	yaml := `
apiVersion: autoscaling/v1
kind: HorizontalPodAutoscaler
metadata:
  labels:
    app: adservice
  name: adservice
spec:
  minReplicas: 5
  maxReplicas: 20
  scaleTargetRef:
    kind: Deployment
    name: adservice
  targetCPUUtilizationPercentage: 80`

	hpa, err := decodeHPA([]byte(yaml))
	if err != nil {
		t.Error(err)
		return
	}

	expectedKey := "autoscaling/v1|HorizontalPodAutoscaler|default|adservice"
	if got := hpa.APIVersionKindName; got != expectedKey {
		t.Errorf("Expected Key %+v, got %+v", expectedKey, got)
	}

	expectedRef := "|Deployment|default|adservice"
	if got := hpa.TargetRef; got != expectedRef {
		t.Errorf("Expected Target referency %+v, got %+v", expectedRef, got)
	}

	expectedMinReplicas := int32(5)
	if got := hpa.MinReplicas; got != expectedMinReplicas {
		t.Errorf("Expected Min Replicas %+v, got %+v", expectedMinReplicas, got)
	}

	expectedMaxReplicas := int32(20)
	if got := hpa.MaxReplicas; got != expectedMaxReplicas {
		t.Errorf("Expected Max Replicas %+v, got %+v", expectedMaxReplicas, got)
	}

	expectedCPU := int32(80)
	if got := hpa.TargetCPUPercentage; got != expectedCPU {
		t.Errorf("Expected target CPU %+v, got %+v", expectedCPU, got)
	}
}

func TestHPANoMinReplicasV1(t *testing.T) {
	yaml := `
apiVersion: autoscaling/v1
kind: HorizontalPodAutoscaler
metadata:
  labels:
    app: adservice
  name: adservice
spec:
  maxReplicas: 20
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: adservice
  targetCPUUtilizationPercentage: 80`

	hpa, err := decodeHPA([]byte(yaml))
	if err != nil {
		t.Error(err)
		return
	}

	expectedKey := "autoscaling/v1|HorizontalPodAutoscaler|default|adservice"
	if got := hpa.APIVersionKindName; got != expectedKey {
		t.Errorf("Expected Key %+v, got %+v", expectedKey, got)
	}

	expectedMinReplicas := int32(1)
	if got := hpa.MinReplicas; got != expectedMinReplicas {
		t.Errorf("Expected Min Replicas %+v, got %+v", expectedMinReplicas, got)
	}

	expectedMaxReplicas := int32(20)
	if got := hpa.MaxReplicas; got != expectedMaxReplicas {
		t.Errorf("Expected Max Replicas %+v, got %+v", expectedMaxReplicas, got)
	}

	expectedCPU := int32(80)
	if got := hpa.TargetCPUPercentage; got != expectedCPU {
		t.Errorf("Expected target CPU %+v, got %+v", expectedCPU, got)
	}
}

func TestHPANoTargetCPUVV1(t *testing.T) {
	yaml := `
apiVersion: autoscaling/v1
kind: HorizontalPodAutoscaler
metadata:
  labels:
    app: adservice
  name: adservice
spec:
  maxReplicas: 20
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: adservice`

	hpa, _ := decodeHPA([]byte(yaml))
	if hpa.TargetCPUPercentage != 0 {
		t.Error("Target CPU should be zero")
	}
}

func TestHPADecodeListV2Beta2(t *testing.T) {
	hpas := readHPAsFromFile("./testdata/hpa/hpa-v2beta2.yaml", t)
	for _, hpa := range hpas {
		if hpa.APIVersionKindName != "autoscaling/v2beta2|HorizontalPodAutoscaler|default|cartservice-memory-hpa" &&
			hpa.TargetCPUPercentage == 0 {
			t.Errorf("HPA should have resource cpu utilization: %+v", hpa)
		}
	}
}

func TestHPADecodeListV2Beta1(t *testing.T) {
	hpas := readHPAsFromFile("./testdata/hpa/hpa-v2beta1.yaml", t)
	for _, hpa := range hpas {
		if hpa.APIVersionKindName != "autoscaling/v2beta1|HorizontalPodAutoscaler|default|cartservice-memory-hpa" &&
			hpa.TargetCPUPercentage == 0 {
			t.Errorf("HPA should have resource cpu utilization: %+v", hpa)
		}
	}
}

func TestHPADecodeListV1(t *testing.T) {
	hpas := readHPAsFromFile("./testdata/hpa/hpa-v1.yaml", t)
	noUtilizationDefined := 0
	for _, hpa := range hpas {
		if hpa.TargetCPUPercentage == 0 {
			noUtilizationDefined++
		}
	}
	if noUtilizationDefined != 1 {
		t.Errorf("HPA should have resource cpu utilization for all but one")
	}
}

func readHPAsFromFile(file string, t *testing.T) []HPA {
	data, err := ioutil.ReadFile(file)
	if err != nil {
		t.Errorf("Error reading file: %+v", err)
	}

	hpas := []HPA{}
	objects := bytes.Split(data, []byte("---"))
	for _, object := range objects {
		hpa, err := decodeHPA(object)
		if err != nil {
			t.Errorf("Error decoding file: %+v", err)
		}
		hpas = append(hpas, hpa)
	}
	return hpas
}
