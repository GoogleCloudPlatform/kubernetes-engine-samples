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

	"github.com/fernandorubbo/k8s-cost-estimator/util"
	log "github.com/sirupsen/logrus"
	"gopkg.in/yaml.v2"
	coreV1 "k8s.io/api/core/v1"
)

const (
	// HPAKind just to avoid mispeling
	HPAKind = "HorizontalPodAutoscaler"
	// DeploymentKind is just to avoid mispeling
	DeploymentKind = "Deployment"
	// ReplicaSetKind is just to avoid mispeling
	ReplicaSetKind = "ReplicaSet"
	// StatefulSetKind is just to avoid mispeling
	StatefulSetKind = "StatefulSet"
	// DaemonSetKind is just to avoid mispeling
	DaemonSetKind = "DaemonSet"
	// VolumeClaimKind is just to avoid mispeling
	VolumeClaimKind = "PersistentVolumeClaim"
)

// SupportedKinds groups all supported kinds
var SupportedKinds = []string{HPAKind, DeploymentKind, ReplicaSetKind, StatefulSetKind, DaemonSetKind, VolumeClaimKind}

// GroupVersionKind is the reprsentation of k8s type
// This object is used to to avoid sprawl of dependent library (eg. apimachinary) across the code
// This will allow easy migration to others library (eg. kyaml) in the future once the dependency is all encapulated into k8s_decoder.go
type GroupVersionKind struct {
	Group   string
	Version string
	Kind    string
}

// HPA is the simplified reprsentation of k8s HPA
// Client doesn't need to handle different version and the complexity of k8s.io package
type HPA struct {
	APIVersionKindName  string
	TargetRef           string
	MinReplicas         int32
	MaxReplicas         int32
	TargetCPUPercentage int32
}

// HorizontalScalableResource is a Horizontal Scalable Resource
// Implemented by Deployment, ReplicaSet and StatefulSet
type HorizontalScalableResource interface {
	getContainers() []Container
	getReplicas() int32
	hasHPA() bool
	getHPA() HPA
}

// Deployment is the simplified reprsentation of k8s deployment
// Client doesn't need to handle different version and the complexity of k8s.io package
type Deployment struct {
	APIVersionKindName string
	Replicas           int32
	Containers         []Container
	hpa                HPA
}

func (d *Deployment) estimateCost(rp ResourcePrice) CostRange {
	return estimateCost(DeploymentKind, d, rp)
}

func (d *Deployment) getKindName() string {
	return buildKindName(d.APIVersionKindName)
}

func (d *Deployment) getContainers() []Container {
	return d.Containers
}

func (d *Deployment) getReplicas() int32 {
	return d.Replicas
}

func (d *Deployment) hasHPA() bool {
	return d.hpa.APIVersionKindName != ""
}

func (d *Deployment) getHPA() HPA {
	return d.hpa
}

// ReplicaSet is the simplified reprsentation of k8s replicaset
// Client doesn't need to handle different version and the complexity of k8s.io package
type ReplicaSet struct {
	APIVersionKindName string
	Replicas           int32
	Containers         []Container
	hpa                HPA
}

func (r *ReplicaSet) estimateCost(rp ResourcePrice) CostRange {
	return estimateCost(ReplicaSetKind, r, rp)
}

func (r *ReplicaSet) getKindName() string {
	return buildKindName(r.APIVersionKindName)
}

func (r *ReplicaSet) getContainers() []Container {
	return r.Containers
}

func (r *ReplicaSet) getReplicas() int32 {
	return r.Replicas
}

func (r *ReplicaSet) hasHPA() bool {
	return r.hpa.APIVersionKindName != ""
}

func (r *ReplicaSet) getHPA() HPA {
	return r.hpa
}

// StatefulSet is the simplified reprsentation of k8s StatefulSet
// Client doesn't need to handle different version and the complexity of k8s.io package
type StatefulSet struct {
	APIVersionKindName string
	Replicas           int32
	Containers         []Container
	hpa                HPA
	VolumeClaims       []*VolumeClaim
}

func (s *StatefulSet) estimateCost(rp ResourcePrice) CostRange {
	return estimateCost(StatefulSetKind, s, rp)
}

func (s *StatefulSet) getKindName() string {
	return buildKindName(s.APIVersionKindName)
}

func (s *StatefulSet) getContainers() []Container {
	return s.Containers
}

func (s *StatefulSet) getReplicas() int32 {
	return s.Replicas
}

func (s *StatefulSet) hasHPA() bool {
	return s.hpa.APIVersionKindName != ""
}

func (s *StatefulSet) getHPA() HPA {
	return s.hpa
}

// DaemonSet is the simplified reprsentation of k8s DaemonSet
// Client doesn't need to handle different version and the complexity of k8s.io package
type DaemonSet struct {
	APIVersionKindName string
	NodesCount         int32
	Containers         []Container
}

func (d *DaemonSet) estimateCost(rp ResourcePrice) CostRange {
	cost := CostRange{Kind: DaemonSetKind}
	cpuReq, cpuLim, memReq, memLim := totalContainers(d.Containers)

	var cpuMonthlyPrice = float64(rp.CPUMonthlyPrice())
	var memoryMonthlyPrice = float64(rp.MemoryMonthlyPrice())

	nodesCount := float64(d.NodesCount)
	cost.MinRequested = (nodesCount * cpuReq * cpuMonthlyPrice) + (nodesCount * memReq * memoryMonthlyPrice)
	cost.MaxRequested = cost.MinRequested
	cost.HPABuffer = cost.MinRequested
	cost.MinLimited = (nodesCount * cpuLim * cpuMonthlyPrice) + (nodesCount * memLim * memoryMonthlyPrice)
	cost.MaxLimited = cost.MinLimited

	return postProcessCost(cost)
}

// VolumeClaim is the simplified reprsentation of k8s VolumeClaim
// Client doesn't need to handle different version and the complexity of k8s.io package
type VolumeClaim struct {
	APIVersionKindName string
	StorageClass       string
	Requests           Resource
	Limits             Resource
}

func (v *VolumeClaim) estimateCost(sp StoragePrice) CostRange {
	storageMonthlyPrice := float64(sp.PdStandardMonthlyPrice())
	storageClass := v.StorageClass
	if storageClass != storageClassStandard {
		log.Infof("Estimation for StorageClass '%s' not implemented for PersistentVolumeClaim. Using standard (GCE Regional Persistent Disk) instead", storageClass)
		storageMonthlyPrice = float64(sp.PdStandardMonthlyPrice())
	}

	cost := CostRange{Kind: VolumeClaimKind}
	cost.MinRequested = (float64(v.Requests.Storage) * storageMonthlyPrice)
	cost.MaxRequested = cost.MinRequested
	cost.HPABuffer = cost.MinRequested
	cost.MinLimited = (float64(v.Limits.Storage) * storageMonthlyPrice)
	cost.MaxLimited = cost.MinLimited

	return postProcessCost(cost)
}

// Container is the simplified representation of k8s Container
// Client doesn't need to handle different version and the complexity of k8s.io package
type Container struct {
	Requests Resource
	Limits   Resource
}

// Resource is the simplified reprsentation of k8s Resource
// Client doesn't need to handle different version and the complexity of k8s.io package
type Resource struct {
	CPU     int64
	Memory  int64
	Storage int64
}

// -------- Price Catalog ---------

//ResourcePrice interface
type ResourcePrice interface {
	CPUMonthlyPrice() float32
	MemoryMonthlyPrice() float32
}

//StoragePrice interface
type StoragePrice interface {
	PdStandardMonthlyPrice() float32
}

//GCPPriceCatalog implementation to make call to GCP CloudCatalog
type GCPPriceCatalog struct {
	cpuPrice        float32
	memoryPrice     float32
	pdStandardPrice float32
}

// CPUMonthlyPrice returns the GCP CPU price in USD
func (pc *GCPPriceCatalog) CPUMonthlyPrice() float32 {
	return pc.cpuPrice
}

// MemoryMonthlyPrice returns the GCP Memory price in USD
func (pc *GCPPriceCatalog) MemoryMonthlyPrice() float32 {
	return pc.memoryPrice
}

// PdStandardMonthlyPrice returns the GCP Storage PD price in USD
func (pc *GCPPriceCatalog) PdStandardMonthlyPrice() float32 {
	return pc.pdStandardPrice
}

// --- utility functions ---

func buildAPIVersionKindName(apiVersion, kind, ns, name string) string {
	namespace := "default"
	if ns != "" {
		namespace = ns
	}
	return fmt.Sprintf("%s|%s|%s|%s", apiVersion, kind, namespace, name)
}

func buildKindName(apiVersionKindName string) string {
	index := strings.Index(apiVersionKindName, "|")
	return apiVersionKindName[index:]
}

func estimateCost(kind string, r HorizontalScalableResource, rp ResourcePrice) CostRange {
	cost := CostRange{Kind: kind}
	cpuReq, cpuLim, memReq, memLim := totalContainers(r.getContainers())

	var cpuMonthlyPrice = float64(rp.CPUMonthlyPrice())
	var memoryMonthlyPrice = float64(rp.MemoryMonthlyPrice())

	if r.hasHPA() {
		hpa := r.getHPA()
		targetCPUPercentage := hpa.TargetCPUPercentage
		minReplicas := float64(hpa.MinReplicas)
		maxReplicas := float64(hpa.MaxReplicas)

		cost.MinRequested = (minReplicas * cpuReq * cpuMonthlyPrice) + (minReplicas * memReq * memoryMonthlyPrice)
		cost.MaxRequested = (maxReplicas * cpuReq * cpuMonthlyPrice) + (maxReplicas * memReq * memoryMonthlyPrice)

		cpuBuffer := minReplicas
		if targetCPUPercentage > 0 {
			buff := float64(100-targetCPUPercentage) / 100
			cpuBuffer = minReplicas + (buff * minReplicas)
		}
		cost.HPABuffer = (cpuBuffer * cpuReq * cpuMonthlyPrice) + (cpuBuffer * memReq * memoryMonthlyPrice)

		cost.MinLimited = (minReplicas * cpuLim * cpuMonthlyPrice) + (minReplicas * memLim * memoryMonthlyPrice)
		cost.MaxLimited = (maxReplicas * cpuLim * cpuMonthlyPrice) + (maxReplicas * memLim * memoryMonthlyPrice)

	} else {
		replicas := float64(r.getReplicas())
		cost.MinRequested = (replicas * cpuReq * cpuMonthlyPrice) + (replicas * memReq * memoryMonthlyPrice)
		cost.MaxRequested = cost.MinRequested
		cost.HPABuffer = cost.MinRequested
		cost.MinLimited = (replicas * cpuLim * cpuMonthlyPrice) + (replicas * memLim * memoryMonthlyPrice)
		cost.MaxLimited = cost.MinLimited
	}

	return postProcessCost(cost)
}

func postProcessCost(cost CostRange) CostRange {
	// just to make sure limit will not be smaller than requested
	if cost.MinLimited < cost.MinRequested {
		cost.MinLimited = cost.MinRequested
	}
	if cost.MaxLimited < cost.MaxRequested {
		cost.MaxLimited = cost.MaxRequested
	}
	return cost
}

func buildContainers(cont []coreV1.Container, conf CostimatorConfig) []Container {
	containers := []Container{}
	for i := 0; i < len(cont); i++ {
		requests := cont[i].Resources.Requests
		requestsCPU := requests[coreV1.ResourceCPU]
		requestsMemory := requests[coreV1.ResourceMemory]
		limits := cont[i].Resources.Limits
		limitsCPU := limits[coreV1.ResourceCPU]
		limitsMemory := limits[coreV1.ResourceMemory]

		requestsCPUinMilli := requestsCPU.MilliValue()
		requestsMemoryinMilli := requestsMemory.Value()
		limitsCPUinMilli := limitsCPU.MilliValue()
		limitsMemoryinMilli := limitsMemory.Value()
		// If Requests is omitted for a container, it defaults to Limits if that is explicitly specified
		if requestsCPUinMilli == 0 {
			requestsCPUinMilli = limitsCPUinMilli
		}
		if requestsMemoryinMilli == 0 {
			requestsMemoryinMilli = limitsMemoryinMilli
		}
		// otherwise to an config-defined value.
		if requestsCPUinMilli == 0 {
			requestsCPUinMilli = conf.ResourceConf.DefaultCPUinMillis
		}
		if requestsMemoryinMilli == 0 {
			requestsMemoryinMilli = conf.ResourceConf.DefaultMemoryinBytes
		}
		// Give a percentage increase for umbounded resources
		if limitsCPUinMilli == 0 {
			limitsCPUinMilli = requestsCPUinMilli + (conf.ResourceConf.PercentageIncreaseForUnboundedRerouces * requestsCPUinMilli / 100)
		}
		if limitsMemoryinMilli == 0 {
			limitsMemoryinMilli = requestsMemoryinMilli + (conf.ResourceConf.PercentageIncreaseForUnboundedRerouces * requestsMemoryinMilli / 100)
		}

		container := Container{
			Requests: Resource{
				CPU:    requestsCPUinMilli,
				Memory: requestsMemoryinMilli,
			},
			Limits: Resource{
				CPU:    limitsCPUinMilli,
				Memory: limitsMemoryinMilli,
			},
		}
		containers = append(containers, container)
	}
	return containers
}

func totalContainers(containers []Container) (cpuReq float64, cpuLim float64, memReq float64, memLim float64) {
	for _, container := range containers {
		cpuReq = cpuReq + float64(container.Requests.CPU)
		cpuLim = cpuLim + float64(container.Limits.CPU)
		memReq = memReq + float64(container.Requests.Memory) // bytes
		memLim = memLim + float64(container.Limits.Memory)   // bytes
	}
	cpuReq = cpuReq / 1000 // from milis to # of cores
	cpuLim = cpuLim / 1000 // from milis to # of cores
	return
}

func isObjectSupported(data []byte) (string, bool) {
	ak := struct {
		APIVersion string `yaml:"apiVersion,omitempty"`
		Kind       string `yaml:"kind,omitempty"`
	}{}
	err := yaml.Unmarshal(data, &ak)
	if err != nil {
		return fmt.Sprintf("%+v", ak), false
	}
	return fmt.Sprintf("%+v", ak), isKindSupported(ak.Kind)
}

func isKindSupported(kind string) bool {
	return util.Contains(SupportedKinds, kind)
}
