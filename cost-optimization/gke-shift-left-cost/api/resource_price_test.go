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
	"io/ioutil"
	"testing"
)

func TestResourcePrice(t *testing.T) {
	credentials, err := ioutil.ReadFile("./testdata/credentials.json")
	if err != nil {
		t.Logf("No credentials found in ./testdata/credentials.json, using default service account.")
	}

	rp, err := NewGCPPriceCatalog(credentials, CostimatorConfig{})
	if err != nil || rp.CPUMonthlyPrice() == 0 || rp.MemoryMonthlyPrice() == 0 || rp.PdStandardMonthlyPrice() == 0 {
		t.Errorf("Error calling GCP. Make sure you have download your service account to ./testdata/credentials.json "+
			"or run 'gcloud auth application-default login; gcloud services enable cloudbilling.googleapis.com' prior "+
			"executing this specific test. Note enabling billing api can take some time. Cause: %+v", err)
	}
}
