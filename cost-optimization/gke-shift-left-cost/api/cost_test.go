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
	"encoding/json"
	"math"
	"strings"
	"testing"
)

func costWithKind(kind string, minRequested, maxRequested, hpaBuffer, minLimited, maxLimited float64) Cost {
	return Cost{
		MonthlyRanges: []CostRange{
			{
				Kind:         kind,
				MinRequested: minRequested,
				MaxRequested: maxRequested,
				HPABuffer:    hpaBuffer,
				MinLimited:   minLimited,
				MaxLimited:   maxLimited,
			},
		},
	}
}

// The current manifests can end up with no cpu/memory cost at all, for example
// when the workloads of a folder were removed and only a PersistentVolumeClaim
// is left. The percentage used to be diff/current, which is a division by zero
// and produced -Inf, and the .diff json file could not be written anymore.
func TestCostSubtractWithoutCurrentCostIsFinite(t *testing.T) {
	previous := costWithKind(DeploymentKind, 5, 5, 5, 5, 5)
	current := costWithKind(VolumeClaimKind, 0, 0, 0, 10, 12)

	diffRange := current.Subtract(previous).MonthlyDiffRange
	percentages := map[string]float64{
		"MinRequested": diffRange.DiffPercentage.MinRequested,
		"MaxRequested": diffRange.DiffPercentage.MaxRequested,
		"HPABuffer":    diffRange.DiffPercentage.HPABuffer,
		"MinLimited":   diffRange.DiffPercentage.MinLimited,
		"MaxLimited":   diffRange.DiffPercentage.MaxLimited,
	}
	for name, value := range percentages {
		if math.IsInf(value, 0) || math.IsNaN(value) {
			t.Errorf("DiffPercentage.%s is %v, want a finite value", name, value)
		}
	}

	if _, err := json.Marshal(diffRange.ToPriceDiff()); err != nil {
		t.Errorf("PriceDiff is not marshalable: %v", err)
	}
}

// A line that dropped to zero did change, even though its percentage is
// undefined. It must not be reported as "No cost change found!".
func TestCostSubtractReportsLineDroppedToZero(t *testing.T) {
	previous := costWithKind(DeploymentKind, 5, 5, 5, 5, 5)
	current := costWithKind(VolumeClaimKind, 0, 0, 0, 10, 12)

	diff := current.Subtract(previous)
	if !strings.Contains(diff.Summary, "decrease in costs") {
		t.Errorf("Summary is '%s', want a decrease on %s", diff.Summary, headers[0])
	}
	if diff.hascostIncd != true {
		t.Errorf("hascostIncd is %t, want true (the limited lines grew)", diff.hascostIncd)
	}
}

// The percentage stays relative to the current cost when there is one.
func TestCostSubtractPercentage(t *testing.T) {
	previous := costWithKind(DeploymentKind, 100, 100, 100, 100, 100)
	current := costWithKind(DeploymentKind, 150, 150, 150, 150, 150)

	diffRange := current.Subtract(previous).MonthlyDiffRange
	if got, want := diffRange.DiffValue.MinRequested, float64(50); got != want {
		t.Errorf("DiffValue.MinRequested is %v, want %v", got, want)
	}
	if got, want := diffRange.DiffPercentage.MinRequested, float64(100.0/3); math.Abs(got-want) > 0.0001 {
		t.Errorf("DiffPercentage.MinRequested is %v, want %v", got, want)
	}
}
