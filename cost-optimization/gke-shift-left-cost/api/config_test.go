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

func TestPopulateDaemonSetConfigNotProvided(t *testing.T) {
	defaults := ConfigDefaults()
	populated := populateConfigNotProvided(CostimatorConfig{})
	if !cmp.Equal(defaults, populated) {
		t.Errorf("Config should be equal, expected: %+v, got: %+v", defaults, populated)
	}

	expected := CostimatorConfig{
		ResourceConf: ResourceConfig{
			MachineFamily:                          N1,
			Region:                                 "us-central2",
			DefaultCPUinMillis:                     300,
			DefaultMemoryinBytes:                   65000000,
			PercentageIncreaseForUnboundedRerouces: 100,
		},
		ClusterConf: ClusterConfig{
			NodesCount: 5,
		},
	}

	populated = populateConfigNotProvided(expected)
	if !cmp.Equal(expected, populated) {
		t.Errorf("Config should be equal, expected: %+v, got: %+v", expected, populated)
	}
}
