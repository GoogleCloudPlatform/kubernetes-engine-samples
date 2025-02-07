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
	"os"
	"path/filepath"
	"strings"

	log "github.com/sirupsen/logrus"
)

// Manifests holds all deployments and executes cost estimation
type Manifests struct {
	Deployments     []*Deployment
	deploymentsRef  map[string]*Deployment
	ReplicaSets     []*ReplicaSet
	replicaSetsRef  map[string]*ReplicaSet
	StatefulSets    []*StatefulSet
	statefulsetsRef map[string]*StatefulSet
	DaemonSets      []*DaemonSet
	VolumeClaims    []*VolumeClaim
	hpas            []HPA
}

// LoadObjectsFromPath loads all files from folder and subfolder finishing with yaml or yml
func (m *Manifests) LoadObjectsFromPath(path string, conf CostimatorConfig) error {
	err := filepath.Walk(path, func(path string, f os.FileInfo, err error) error {
		if !f.IsDir() {
			if strings.HasSuffix(path, ".yaml") || strings.HasSuffix(path, ".yml") {
				data, err := ioutil.ReadFile(path)
				if err != nil {
					return err
				}
				log.Tracef("Loading yaml file '%s'", path)
				return m.LoadObjects(data, conf)
			}
			log.Tracef("Skipping non yaml file '%s'", path)
		}
		return nil
	})

	if err != nil {
		return err
	}
	return nil
}

// LoadObjects allow you to decode and load into Manifests your k8s objects
// For now, it only understands Deployment and HPA
func (m *Manifests) LoadObjects(data []byte, conf CostimatorConfig) error {
	objects := bytes.Split(data, []byte("---"))
	for _, object := range objects {
		err := m.loadObject(object, conf)
		if err != nil {
			return err
		}
	}
	return nil
}

// EstimateCost loop through all resources and group it by kind
func (m *Manifests) EstimateCost(pc GCPPriceCatalog) Cost {
	m.prepareForCostEstimation()

	monthlyRanges := []CostRange{}
	if len(m.Deployments) > 0 {
		monthlyRanges = append(monthlyRanges, m.estimateDeploymentCost(&pc))
	}
	if len(m.ReplicaSets) > 0 {
		monthlyRanges = append(monthlyRanges, m.estimateReplicaSetCost(&pc))
	}
	if len(m.StatefulSets) > 0 {
		monthlyRanges = append(monthlyRanges, m.estimateStatefulSetCost(&pc))
	}
	if len(m.DaemonSets) > 0 {
		monthlyRanges = append(monthlyRanges, m.estimateDaemonSetCost(&pc))
	}
	if len(m.VolumeClaims) > 0 {
		monthlyRanges = append(monthlyRanges, m.estimateVolumeClaimCost(&pc))
	}

	return Cost{
		MonthlyRanges: monthlyRanges,
	}
}

func (m *Manifests) estimateDeploymentCost(rp ResourcePrice) CostRange {
	deploymentRange := CostRange{Kind: DeploymentKind}
	for _, deploy := range m.Deployments {
		deploymentRange = deploymentRange.Add(deploy.estimateCost(rp))
	}
	return deploymentRange
}

func (m *Manifests) estimateReplicaSetCost(rp ResourcePrice) CostRange {
	replicasetRange := CostRange{Kind: ReplicaSetKind}
	for _, replicaset := range m.ReplicaSets {
		replicasetRange = replicasetRange.Add(replicaset.estimateCost(rp))
	}
	return replicasetRange
}

func (m *Manifests) estimateStatefulSetCost(rp ResourcePrice) CostRange {
	statefulsetRange := CostRange{Kind: StatefulSetKind}
	for _, statefulset := range m.StatefulSets {
		statefulsetRange = statefulsetRange.Add(statefulset.estimateCost(rp))
	}
	return statefulsetRange
}

func (m *Manifests) estimateDaemonSetCost(rp ResourcePrice) CostRange {
	daemonsetRange := CostRange{Kind: DaemonSetKind}
	for _, daemonset := range m.DaemonSets {
		daemonsetRange = daemonsetRange.Add(daemonset.estimateCost(rp))
	}
	return daemonsetRange
}

func (m *Manifests) estimateVolumeClaimCost(sp StoragePrice) CostRange {
	volumeClaimRange := CostRange{Kind: VolumeClaimKind}
	for _, volumeClaim := range m.VolumeClaims {
		volumeClaimRange = volumeClaimRange.Add(volumeClaim.estimateCost(sp))
	}
	return volumeClaimRange
}

func (m *Manifests) prepareForCostEstimation() {
	for _, hpa := range m.hpas {
		key := hpa.TargetRef
		if deploy, ok := m.deploymentsRef[key]; ok {
			deploy.hpa = hpa
		}
		if replicaset, ok := m.replicaSetsRef[key]; ok {
			replicaset.hpa = hpa
		}
		if statefulset, ok := m.statefulsetsRef[key]; ok {
			statefulset.hpa = hpa
		}
	}
}

func (m *Manifests) loadObject(data []byte, conf CostimatorConfig) error {
	if ak, bol := isObjectSupported(data); !bol {
		log.Debugf("Skipping unsupported k8s object: %+v", ak)
		return nil
	}

	obj, groupVersionKind, err := decode(data)
	if err != nil {
		return fmt.Errorf("Error Decoding. Check if your GroupVersionKind is defined in api/k8s_decoder.go. Root cause %+v", err)
	}

	switch groupVersionKind.Kind {
	case HPAKind:
		hpa, err := buildHPA(obj, groupVersionKind)
		if err != nil {
			return err
		}
		m.hpas = append(m.hpas, hpa)
	case DeploymentKind:
		deploy, err := buildDeployment(obj, groupVersionKind, conf)
		if err != nil {
			return err
		}
		m.Deployments = append(m.Deployments, &deploy)
		if m.deploymentsRef == nil {
			m.deploymentsRef = make(map[string]*Deployment)
		}
		m.deploymentsRef[deploy.APIVersionKindName] = &deploy
		m.deploymentsRef[deploy.getKindName()] = &deploy
	case ReplicaSetKind:
		replicaset, err := buildReplicaSet(obj, groupVersionKind, conf)
		if err != nil {
			return err
		}
		m.ReplicaSets = append(m.ReplicaSets, &replicaset)
		if m.replicaSetsRef == nil {
			m.replicaSetsRef = make(map[string]*ReplicaSet)
		}
		m.replicaSetsRef[replicaset.APIVersionKindName] = &replicaset
		m.replicaSetsRef[replicaset.getKindName()] = &replicaset
	case StatefulSetKind:
		statefulset, err := buildStatefulSet(obj, groupVersionKind, conf)
		if err != nil {
			return err
		}
		m.StatefulSets = append(m.StatefulSets, &statefulset)
		if m.statefulsetsRef == nil {
			m.statefulsetsRef = make(map[string]*StatefulSet)
		}
		m.statefulsetsRef[statefulset.APIVersionKindName] = &statefulset
		m.statefulsetsRef[statefulset.getKindName()] = &statefulset

		if len(statefulset.VolumeClaims) > 0 {
			m.VolumeClaims = append(m.VolumeClaims, statefulset.VolumeClaims...)
		}
	case DaemonSetKind:
		daemonset, err := buildDaemonSet(obj, groupVersionKind, conf)
		if err != nil {
			return err
		}
		m.DaemonSets = append(m.DaemonSets, &daemonset)
	case VolumeClaimKind:
		volume, err := buildVolumeClaim(obj, groupVersionKind, conf)
		if err != nil {
			return err
		}
		m.VolumeClaims = append(m.VolumeClaims, &volume)
	}

	return nil
}
