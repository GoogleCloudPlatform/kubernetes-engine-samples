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

	appsV1 "k8s.io/api/apps/v1"
)

//decodeStatefulSet reads k8s StatefulSet yaml and trasform to StatefulSet object - mostly used by tests
func decodeStatefulSet(data []byte, conf CostimatorConfig) (StatefulSet, error) {
	obj, groupVersionKind, err := decode(data)
	if err != nil {
		return StatefulSet{}, fmt.Errorf("Error Decoding. Check if your GroupVersionKind is defined in api/k8s_decoder.go. Root cause %+v", err)
	}
	return buildStatefulSet(obj, groupVersionKind, conf)
}

//buildStatefulSet reads k8s StatefulSet object and trasform to StatefulSet object
func buildStatefulSet(obj interface{}, groupVersionKind GroupVersionKind, conf CostimatorConfig) (StatefulSet, error) {
	switch obj.(type) {
	default:
		return StatefulSet{}, fmt.Errorf("APIVersion and Kind not Implemented: %+v", groupVersionKind)
	case *appsV1.StatefulSet:
		return buildStatefulSetV1(obj.(*appsV1.StatefulSet), conf)
	}
}

func buildStatefulSetV1(statefulset *appsV1.StatefulSet, conf CostimatorConfig) (StatefulSet, error) {
	conf = populateConfigNotProvided(conf)
	containers := buildContainers(statefulset.Spec.Template.Spec.Containers, conf)
	var replicas int32 = 1
	if statefulset.Spec.Replicas != (*int32)(nil) {
		replicas = *statefulset.Spec.Replicas
	}

	volumeClaims := []*VolumeClaim{}
	for _, vct := range statefulset.Spec.VolumeClaimTemplates {
		groupVersionKind := GroupVersionKind{Kind: VolumeClaimKind}
		pvc, err := buildVolumeClaim(&vct, groupVersionKind, conf)
		if err != nil {
			return StatefulSet{}, err
		}
		volumeClaims = append(volumeClaims, &pvc)
	}

	return StatefulSet{
		APIVersionKindName: buildAPIVersionKindName(statefulset.APIVersion, statefulset.Kind, statefulset.GetNamespace(), statefulset.GetName()),
		Replicas:           replicas,
		Containers:         containers,
		VolumeClaims:       volumeClaims,
	}, nil
}
