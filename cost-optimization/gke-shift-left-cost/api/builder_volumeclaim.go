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

	coreV1 "k8s.io/api/core/v1"
)

const storageClassStandard = "standard"

//decodeVolumeClaim reads k8s PersistentVolumeClaim yaml and trasform to VolumeClaim object - mostly used by tests
func decodeVolumeClaim(data []byte, conf CostimatorConfig) (VolumeClaim, error) {
	obj, groupVersionKind, err := decode(data)
	if err != nil {
		return VolumeClaim{}, fmt.Errorf("Error Decoding. Check if your GroupVersionKind is defined in api/k8s_decoder.go. Root cause %+v", err)
	}
	return buildVolumeClaim(obj, groupVersionKind, conf)
}

//buildVolumeClaim reads k8s PersistentVolumeClaim object and trasform to VolumeClaim object
func buildVolumeClaim(obj interface{}, groupVersionKind GroupVersionKind, conf CostimatorConfig) (VolumeClaim, error) {
	switch obj.(type) {
	default:
		return VolumeClaim{}, fmt.Errorf("APIVersion and Kind not Implemented: %+v", groupVersionKind)
	case *coreV1.PersistentVolumeClaim:
		return buildVolumeClaimV1(obj.(*coreV1.PersistentVolumeClaim), conf), nil
	}
}

func buildVolumeClaimV1(volume *coreV1.PersistentVolumeClaim, conf CostimatorConfig) VolumeClaim {
	conf = populateConfigNotProvided(conf)
	storageClass := storageClassStandard
	if volume.Spec.StorageClassName != (*string)(nil) && *volume.Spec.StorageClassName != "" {
		storageClass = *volume.Spec.StorageClassName
	}
	res := volume.Spec.Resources
	requests := res.Requests.Storage().Value()
	limits := res.Limits.Storage().Value()
	// If Requests is omitted for a container, it defaults to Limits if that is explicitly specified
	if requests == 0 {
		requests = limits
	}
	if limits == 0 {
		limits = requests
	}
	return VolumeClaim{
		APIVersionKindName: buildAPIVersionKindName(volume.APIVersion, VolumeClaimKind, volume.GetNamespace(), volume.GetName()),
		StorageClass:       storageClass,
		Requests:           Resource{Storage: requests},
		Limits:             Resource{Storage: limits},
	}
}
