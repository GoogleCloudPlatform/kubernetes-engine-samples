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

func TestVolumeClaimAPINotImplemented(t *testing.T) {
	yaml := `
  kind: PersistentVolumeClaim
  apiVersion: v2222
  metadata:
    name: my-volumeclaim
  spec:
    accessModes:
    - ReadWriteOnce
    resources:
      requests:
        storage: 360Gi`

	_, err := decodeVolumeClaim([]byte(yaml), CostimatorConfig{})
	if err == nil || !strings.HasPrefix(err.Error(), "Error Decoding.") {
		t.Error(fmt.Errorf("Should have return an APIVersion error, but returned '%+v'", err))
	}
}

func TestVolumeClaimBasicV1(t *testing.T) {
	yaml := `
  kind: PersistentVolumeClaim
  apiVersion: v1
  metadata:
    name: my-volumeclaim
  spec:
    accessModes:
    - ReadWriteOnce
    resources:
      requests:
        storage: 360Gi`

	volume, err := decodeVolumeClaim([]byte(yaml), CostimatorConfig{})
	if err != nil {
		t.Error(err)
		return
	}

	expectedAPIVersionKindName := "v1|PersistentVolumeClaim|default|my-volumeclaim"
	if got := volume.APIVersionKindName; got != expectedAPIVersionKindName {
		t.Errorf("Expected APIVersionKindName %+v, got %+v", expectedAPIVersionKindName, got)
	}

	if got := volume.StorageClass; got != storageClassStandard {
		t.Errorf("Expected StorageClassName %+v, got %+v", storageClassStandard, got)
	}

	expectedStorage := int64(386547056640)
	requests := volume.Requests
	if got := requests.Storage; got != expectedStorage {
		t.Errorf("Expected Requests Storage %+v, got %+v", expectedStorage, got)
	}
	limits := volume.Limits
	if got := limits.Storage; got != expectedStorage {
		t.Errorf("Expected Limits Storage %+v, got %+v", expectedStorage, got)
	}
}

func TestVolumeClaimCustomStorageClass(t *testing.T) {
	yaml := `
  kind: PersistentVolumeClaim
  apiVersion: v1
  metadata:
    name: my-volumeclaim
  spec:
    storageClassName: my-storage-class
    accessModes:
    - ReadWriteOnce
    resources:
      requests:
        storage: 360Gi`

	volume, err := decodeVolumeClaim([]byte(yaml), CostimatorConfig{})
	if err != nil {
		t.Error(err)
		return
	}

	storageClass := "my-storage-class"
	if got := volume.StorageClass; got != storageClass {
		t.Errorf("Expected StorageClassName %+v, got %+v", storageClass, got)
	}
}
