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

import "testing"

func TestDeploymentGetKindName(t *testing.T) {
	d := Deployment{APIVersionKindName: "version|kind|namespace|name"}
	want := "|kind|namespace|name"
	if got := d.getKindName(); got != want {
		t.Errorf("Deployment.getKindName() = %v, want %v", got, want)
	}
}

func TestDeploymentEstimateCostWithoutHPA(t *testing.T) {
	rp := &GCPPriceCatalog{
		cpuPrice:    4,
		memoryPrice: 2,
	}
	deploy := Deployment{
		Replicas: 2,
		Containers: []Container{
			{
				Requests: Resource{
					CPU:    1000,  // 1 vCPU
					Memory: 10000, // bytes
				},
				Limits: Resource{
					CPU:    2000,  // 2 vCPU
					Memory: 20000, // bytes
				},
			},
		},
		hpa: HPA{},
	}
	cr := deploy.estimateCost(rp)

	want := DeploymentKind
	if got := cr.Kind; got != want {
		t.Errorf("Kind is %v, want %v", got, want)
	}

	cost := (4.0 + 20000.0) * 2
	if got := cr.MinRequested; got != cost {
		t.Errorf("MinRequested is %v, want %v", got, cost)
	}
	if got := cr.MaxRequested; got != cost {
		t.Errorf("MaxRequested is %v, want %v", got, cost)
	}
	if got := cr.HPABuffer; got != cost {
		t.Errorf("HPABuffer is %v, want %v", got, cost)
	}

	cost = (8.0 + 40000.0) * 2
	if got := cr.MinLimited; got != cost {
		t.Errorf("MinLimited is %v, want %v", got, cost)
	}
	if got := cr.MaxLimited; got != cost {
		t.Errorf("MaxLimited is %v, want %v", got, cost)
	}
}

func TestDeploymentEstimateCostWithoutHpaNoLimits(t *testing.T) {
	rp := &GCPPriceCatalog{
		cpuPrice:    4,
		memoryPrice: 2,
	}
	deploy := Deployment{
		Replicas: 2,
		Containers: []Container{
			{
				Requests: Resource{
					CPU:    1000,  // 1 vCPU
					Memory: 10000, // bytes
				},
				Limits: Resource{
					CPU:    0, // 0 vCPU
					Memory: 0, // bytes
				},
			},
		},
		hpa: HPA{},
	}
	cr := deploy.estimateCost(rp)

	want := DeploymentKind
	if got := cr.Kind; got != want {
		t.Errorf("Kind is %v, want %v", got, want)
	}

	cost := (4.0 + 20000.0) * 2
	if got := cr.MinRequested; got != cost {
		t.Errorf("MinRequested is %v, want %v", got, cost)
	}
	if got := cr.MaxRequested; got != cost {
		t.Errorf("MaxRequested is %v, want %v", got, cost)
	}
	if got := cr.HPABuffer; got != cost {
		t.Errorf("HPABuffer is %v, want %v", got, cost)
	}
	if got := cr.MinLimited; got != cost {
		t.Errorf("MinLimited is %v, want %v", got, cost)
	}
	if got := cr.MaxLimited; got != cost {
		t.Errorf("MaxLimited is %v, want %v", got, cost)
	}
}
func TestDeploymentEstimateCostWithHPA(t *testing.T) {
	rp := &GCPPriceCatalog{
		cpuPrice:    4,
		memoryPrice: 2,
	}
	deploy := Deployment{
		Replicas: 2,
		Containers: []Container{
			{
				Requests: Resource{
					CPU:    1000,  // 1 vCPU
					Memory: 10000, // bytes
				},
				Limits: Resource{
					CPU:    2000,  // 2 vCPU
					Memory: 20000, // bytes
				},
			},
		},
		hpa: HPA{
			APIVersionKindName:  "HPA",
			MinReplicas:         1,
			MaxReplicas:         3,
			TargetCPUPercentage: 60},
	}
	cr := deploy.estimateCost(rp)

	want := DeploymentKind
	if got := cr.Kind; got != want {
		t.Errorf("Kind is %v, want %v", got, want)
	}

	minRequested := 4.0 + 20000.0
	if got := cr.MinRequested; got != minRequested {
		t.Errorf("MinRequested is %v, want %v", got, minRequested)
	}
	maxRequested := (4.0 + 20000.0) * 3
	if got := cr.MaxRequested; got != maxRequested {
		t.Errorf("MaxRequested is %v, want %v", got, maxRequested)
	}
	hpaBuffer := cr.MinRequested + (cr.MinRequested * 0.4)
	if got := cr.HPABuffer; got != hpaBuffer {
		t.Errorf("HPABuffer is %v, want %v", got, hpaBuffer)
	}

	minLimited := 8.0 + 40000.0
	if got := cr.MinLimited; got != minLimited {
		t.Errorf("MinLimited is %v, want %v", got, minLimited)
	}
	maxLimited := (8.0 + 40000.0) * 3.0
	if got := cr.MaxLimited; got != maxLimited {
		t.Errorf("MaxLimited is %v, want %v", got, maxLimited)
	}
}

func TestStatefulSetGetKindName(t *testing.T) {
	s := StatefulSet{APIVersionKindName: "version|kind|namespace|name"}
	want := "|kind|namespace|name"
	if got := s.getKindName(); got != want {
		t.Errorf("StatefulSet.getKindName() = %v, want %v", got, want)
	}
}

func TestStatefulEstimateCostWithoutHPA(t *testing.T) {
	rp := &GCPPriceCatalog{
		cpuPrice:    4,
		memoryPrice: 2,
	}
	statefulset := StatefulSet{
		Replicas: 2,
		Containers: []Container{
			{
				Requests: Resource{
					CPU:    1000,  // 1 vCPU
					Memory: 10000, // bytes
				},
				Limits: Resource{
					CPU:    2000,  // 2 vCPU
					Memory: 20000, // bytes
				},
			},
		},
		hpa: HPA{},
	}
	cr := statefulset.estimateCost(rp)

	want := StatefulSetKind
	if got := cr.Kind; got != want {
		t.Errorf("Kind is %v, want %v", got, want)
	}

	cost := (4.0 + 20000.0) * 2
	if got := cr.MinRequested; got != cost {
		t.Errorf("MinRequested is %v, want %v", got, cost)
	}
	if got := cr.MaxRequested; got != cost {
		t.Errorf("MaxRequested is %v, want %v", got, cost)
	}
	if got := cr.HPABuffer; got != cost {
		t.Errorf("HPABuffer is %v, want %v", got, cost)
	}

	cost = (8.0 + 40000.0) * 2
	if got := cr.MinLimited; got != cost {
		t.Errorf("MinLimited is %v, want %v", got, cost)
	}
	if got := cr.MaxLimited; got != cost {
		t.Errorf("MaxLimited is %v, want %v", got, cost)
	}
}

func TestStatefulEstimateCostWithHPA(t *testing.T) {
	rp := &GCPPriceCatalog{
		cpuPrice:    4,
		memoryPrice: 2,
	}
	statefulset := StatefulSet{
		Replicas: 2,
		Containers: []Container{
			{
				Requests: Resource{
					CPU:    1000,  // 1 vCPU
					Memory: 10000, // bytes
				},
				Limits: Resource{
					CPU:    2000,  // 2 vCPU
					Memory: 20000, // bytes
				},
			},
		},
		hpa: HPA{},
	}
	cr := statefulset.estimateCost(rp)

	want := StatefulSetKind
	if got := cr.Kind; got != want {
		t.Errorf("Kind is %v, want %v", got, want)
	}

	cost := (4.0 + 20000.0) * 2
	if got := cr.MinRequested; got != cost {
		t.Errorf("MinRequested is %v, want %v", got, cost)
	}
	if got := cr.MaxRequested; got != cost {
		t.Errorf("MaxRequested is %v, want %v", got, cost)
	}
	if got := cr.HPABuffer; got != cost {
		t.Errorf("HPABuffer is %v, want %v", got, cost)
	}

	cost = (8.0 + 40000.0) * 2
	if got := cr.MinLimited; got != cost {
		t.Errorf("MinLimited is %v, want %v", got, cost)
	}
	if got := cr.MaxLimited; got != cost {
		t.Errorf("MaxLimited is %v, want %v", got, cost)
	}
}

func TestDaemonSetEstimateCost(t *testing.T) {
	rp := &GCPPriceCatalog{
		cpuPrice:    4,
		memoryPrice: 2,
	}
	daemonset := DaemonSet{
		NodesCount: 3,
		Containers: []Container{
			{
				Requests: Resource{
					CPU:    1000,  // 1 vCPU
					Memory: 10000, // bytes
				},
				Limits: Resource{
					CPU:    2000,  // 2 vCPU
					Memory: 20000, // bytes
				},
			},
		},
	}
	cr := daemonset.estimateCost(rp)

	want := DaemonSetKind
	if got := cr.Kind; got != want {
		t.Errorf("Kind is %v, want %v", got, want)
	}

	cost := (4.0 + 20000.0) * 3
	if got := cr.MinRequested; got != cost {
		t.Errorf("MinRequested is %v, want %v", got, cost)
	}
	if got := cr.MaxRequested; got != cost {
		t.Errorf("MaxRequested is %v, want %v", got, cost)
	}
	if got := cr.HPABuffer; got != cost {
		t.Errorf("HPABuffer is %v, want %v", got, cost)
	}

	cost = (8.0 + 40000.0) * 3
	if got := cr.MinLimited; got != cost {
		t.Errorf("MinLimited is %v, want %v", got, cost)
	}
	if got := cr.MaxLimited; got != cost {
		t.Errorf("MaxLimited is %v, want %v", got, cost)
	}
}

func TestVolumeClaimEstimateCost(t *testing.T) {
	rp := &GCPPriceCatalog{
		pdStandardPrice: 2,
	}
	volume := VolumeClaim{
		StorageClass: storageClassStandard,
		Requests: Resource{
			Storage: 10000, // bytes
		},
		Limits: Resource{
			Storage: 0, // bytes
		},
	}
	cr := volume.estimateCost(rp)

	want := VolumeClaimKind
	if got := cr.Kind; got != want {
		t.Errorf("Kind is %v, want %v", got, want)
	}

	cost := 20000.0
	if got := cr.MinRequested; got != cost {
		t.Errorf("MinRequested is %v, want %v", got, cost)
	}
	if got := cr.MaxRequested; got != cost {
		t.Errorf("MaxRequested is %v, want %v", got, cost)
	}
	if got := cr.HPABuffer; got != cost {
		t.Errorf("HPABuffer is %v, want %v", got, cost)
	}
	if got := cr.MinLimited; got != cost {
		t.Errorf("MinLimited is %v, want %v", got, cost)
	}
	if got := cr.MaxLimited; got != cost {
		t.Errorf("MaxLimited is %v, want %v", got, cost)
	}
}
