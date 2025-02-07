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
	"math"
	"strings"

	"github.com/leekchan/accounting"
	"github.com/olekukonko/tablewriter"
)

const (
	upArrow   = "&#8593;"
	downArrow = "&#8595;"
)

var headers = []string{"MIN REQUESTED",
	"MIN REQ + HPA CPU BUFFER",
	"MAX REQUESTED",
	"MIN LIMITED",
	"MAX LIMITED"}

// Cost groups cost range by kinda
type Cost struct {
	MonthlyRanges []CostRange
}

// CostRange represent the range of estimated value
type CostRange struct {
	Kind string `json:"kind"`

	MinRequested float64 `json:"minRequested"`
	MaxRequested float64 `json:"maxRequested"`

	HPABuffer float64 `json:"hpaBuffer"` //Note: currently only supports CPU Target utilizaiton

	MinLimited float64 `json:"minLimited"`
	MaxLimited float64 `json:"maxLimited"`
}

// DiffCost holds the total difference between two costs
type DiffCost struct {
	Summary          string
	hascostIncd      bool
	CostCurr         Cost
	CostPrev         Cost
	MonthlyDiffRange DiffCostRange
}

// DiffCostRange holds the total difference between two costs
type DiffCostRange struct {
	Kind           string
	CostCurr       CostRange
	CostPrev       CostRange
	DiffValue      CostRange
	DiffPercentage CostRange
}

// MonthlyTotal returns the sum for all MonthlyRanges
func (c *Cost) MonthlyTotal() CostRange {
	totalMonthlyRange := CostRange{Kind: "MonthlyTotal"}
	for _, monthlyRange := range c.MonthlyRanges {
		totalMonthlyRange = totalMonthlyRange.Add(monthlyRange)
	}
	return totalMonthlyRange
}

// Subtract current total cost from previous total cost
func (c *Cost) Subtract(costPrev Cost) DiffCost {
	cr := c.MonthlyTotal()
	diff := cr.Subtract(costPrev.MonthlyTotal())
	summary, hascostIncd := diff.status()
	return DiffCost{
		Summary:          summary,
		hascostIncd:      hascostIncd,
		CostCurr:         *c,
		CostPrev:         costPrev,
		MonthlyDiffRange: diff,
	}
}

// ToMarkdown convert to Markdown string
func (c *Cost) ToMarkdown() string {
	data := [][]string{}
	total := CostRange{Kind: bold("TOTAL")}
	for _, mr := range c.MonthlyRanges {
		data = append(data,
			[]string{mr.Kind,
				currency(mr.MinRequested),
				currency(mr.HPABuffer),
				currency(mr.MaxRequested),
				currency(mr.MinLimited),
				currency(mr.MaxLimited)})

		total.MinRequested = total.MinRequested + mr.MinRequested
		total.HPABuffer = total.HPABuffer + mr.HPABuffer
		total.MaxRequested = total.MaxRequested + mr.MaxRequested
		total.MinLimited = total.MinLimited + mr.MinLimited
		total.MaxLimited = total.MaxLimited + mr.MaxLimited
	}
	data = append(data,
		[]string{total.Kind,
			bold(currency(total.MinRequested)),
			bold(currency(total.HPABuffer)),
			bold(currency(total.MaxRequested)),
			bold(currency(total.MinLimited)),
			bold(currency(total.MaxLimited))})

	out := &strings.Builder{}
	table := tablewriter.NewWriter(out)
	table.SetHeader(
		[]string{"Kind",
			headers[0] + " (USD)",
			headers[1] + " (USD)",
			headers[2] + " (USD)",
			headers[3] + " (USD)",
			headers[4] + " (USD)"})
	table.SetBorders(tablewriter.Border{Left: true, Top: false, Right: true, Bottom: false})
	table.SetCenterSeparator("|")
	table.SetColumnAlignment([]int{0, 2, 2, 2, 2, 2})
	table.AppendBulk(data)
	table.Render()
	return out.String()
}

func bold(val string) string {
	return fmt.Sprintf("**%s**", val)
}

// Add sums the given costrange to the current costrange
func (c *CostRange) Add(costRange CostRange) CostRange {
	ret := CostRange{Kind: c.Kind}
	ret.MinRequested = c.MinRequested + costRange.MinRequested
	ret.MaxRequested = c.MaxRequested + costRange.MaxRequested
	ret.HPABuffer = c.HPABuffer + costRange.HPABuffer
	ret.MinLimited = c.MinLimited + costRange.MinLimited
	ret.MaxLimited = c.MaxLimited + costRange.MaxLimited
	return ret
}

// Subtract subtracts the given costrange to the current costrange
func (c *CostRange) Subtract(costRangePrev CostRange) DiffCostRange {

	diff := CostRange{Kind: c.Kind}
	diff.MinRequested = c.MinRequested - costRangePrev.MinRequested
	diff.MaxRequested = c.MaxRequested - costRangePrev.MaxRequested
	diff.HPABuffer = c.HPABuffer - costRangePrev.HPABuffer
	diff.MinLimited = c.MinLimited - costRangePrev.MinLimited
	diff.MaxLimited = c.MaxLimited - costRangePrev.MaxLimited

	diffP := CostRange{Kind: c.Kind}
	diffP.MinRequested = diff.MinRequested * 100 / c.MinRequested
	diffP.MaxRequested = diff.MaxRequested * 100 / c.MaxRequested
	diffP.HPABuffer = diff.HPABuffer * 100 / c.HPABuffer
	diffP.MinLimited = diff.MinLimited * 100 / c.MinLimited
	diffP.MaxLimited = diff.MaxLimited * 100 / c.MaxLimited

	return DiffCostRange{
		Kind:           c.Kind,
		CostCurr:       *c,
		CostPrev:       costRangePrev,
		DiffValue:      diff,
		DiffPercentage: diffP,
	}
}

func (c *CostRange) max() float64 {
	max := c.MinRequested
	if c.MaxRequested > max {
		max = c.MaxRequested
	}
	if c.HPABuffer > max {
		max = c.HPABuffer
	}
	if c.MinLimited > max {
		max = c.MinLimited
	}
	if c.MaxLimited > max {
		max = c.MaxLimited
	}
	return max
}

// ToMarkdown convert to Markdown string
func (d *DiffCost) ToMarkdown() string {

	current := fmt.Sprintf("## Current Monthly Cost\n\n%s", d.CostCurr.ToMarkdown())
	previous := fmt.Sprintf("## Previous Monthly Cost\n\n%s", d.CostPrev.ToMarkdown())
	diff := d.MonthlyDiffRange.ToMarkdown()
	total := fmt.Sprintf("## Difference in Costs\n\n**Summary:** %s\n\n%s", d.Summary, diff)
	return fmt.Sprintf("%s\n\n%s\n\n%s", previous, current, total)
}

//---

// PriceMaxDiff ...
type PriceMaxDiff struct {
	USD  float64 `json:"usd"`
	Perc float64 `json:"perc"`
}

// PriceSummary ...
type PriceSummary struct {
	PossiblyCostIncrease bool         `json:"possiblyCostIncrease"`
	MaxDiff              PriceMaxDiff `json:"maxDiff"`
}

// PriceDetails ...
type PriceDetails struct {
	USD  CostRange `json:"usd"`
	Perc CostRange `json:"perc"`
}

// PriceDiff ...
type PriceDiff struct {
	Summary PriceSummary `json:"summary"`
	Details PriceDetails `json:"details"`
}

// ToPriceDiff struct
func (d *DiffCostRange) ToPriceDiff() PriceDiff {
	return PriceDiff{
		Summary: d.ToPriceSummary(),
		Details: d.ToPriceDetails(),
	}
}

// ToPriceSummary struct
func (d *DiffCostRange) ToPriceSummary() PriceSummary {
	_, costIncrease := d.status()
	return PriceSummary{
		PossiblyCostIncrease: costIncrease,
		MaxDiff:              d.ToPriceMaxDiff(),
	}
}

// ToPriceMaxDiff struct
func (d *DiffCostRange) ToPriceMaxDiff() PriceMaxDiff {
	return PriceMaxDiff{
		USD:  math.Floor(d.DiffValue.max()*100) / 100,
		Perc: math.Floor(d.DiffPercentage.max()*100) / 100,
	}
}

// ToPriceDetails struct
func (d *DiffCostRange) ToPriceDetails() PriceDetails {
	return PriceDetails{
		USD:  d.DiffValue,
		Perc: d.DiffPercentage,
	}
}

// ToMarkdown convert to Markdown string
func (d *DiffCostRange) ToMarkdown() string {
	data := [][]string{
		{bold(headers[0]), currency(d.CostPrev.MinRequested), currency(d.CostCurr.MinRequested), currencyDiff(d.DiffValue.MinRequested), percDiff(d.DiffPercentage.MinRequested)},
		{bold(headers[1]), currency(d.CostPrev.HPABuffer), currency(d.CostCurr.HPABuffer), currencyDiff(d.DiffValue.HPABuffer), percDiff(d.DiffPercentage.HPABuffer)},
		{bold(headers[2]), currency(d.CostPrev.MaxRequested), currency(d.CostCurr.MaxRequested), currencyDiff(d.DiffValue.MaxRequested), percDiff(d.DiffPercentage.MaxRequested)},
		{bold(headers[3]), currency(d.CostPrev.MinLimited), currency(d.CostCurr.MinLimited), currencyDiff(d.DiffValue.MinLimited), percDiff(d.DiffPercentage.MinLimited)},
		{bold(headers[4]), currency(d.CostPrev.MaxLimited), currency(d.CostCurr.MaxLimited), currencyDiff(d.DiffValue.MaxLimited), percDiff(d.DiffPercentage.MaxLimited)},
	}

	out := &strings.Builder{}
	table := tablewriter.NewWriter(out)
	table.SetHeader([]string{"Cost Variation", "Previous (USD)", "Current (USD)", "Difference (USD)", "Difference (%)"})
	table.SetBorders(tablewriter.Border{Left: true, Top: false, Right: true, Bottom: false})
	table.SetCenterSeparator("|")
	table.SetColumnAlignment([]int{0, 2, 2, 2, 2})
	table.AppendBulk(data)
	table.Render()
	return out.String()
}

func (d *DiffCostRange) status() (summary string, costIncrease bool) {
	var costInc, costDec []string

	if d.DiffPercentage.MinRequested > 0 {
		costInc = append(costInc, headers[0])
	}
	if d.DiffPercentage.HPABuffer > 0 {
		costInc = append(costInc, headers[1])
	}
	if d.DiffPercentage.MaxRequested > 0 {
		costInc = append(costInc, headers[2])
	}
	if d.DiffPercentage.MinLimited > 0 {
		costInc = append(costInc, headers[3])
	}
	if d.DiffPercentage.MaxLimited > 0 {
		costInc = append(costInc, headers[4])
	}

	if d.DiffPercentage.MinRequested < 0 {
		costDec = append(costDec, headers[0])
	}
	if d.DiffPercentage.HPABuffer < 0 {
		costDec = append(costDec, headers[1])
	}
	if d.DiffPercentage.MaxRequested < 0 {
		costDec = append(costDec, headers[2])
	}
	if d.DiffPercentage.MinLimited < 0 {
		costDec = append(costDec, headers[3])
	}
	if d.DiffPercentage.MaxLimited < 0 {
		costDec = append(costDec, headers[4])
	}

	if len(costInc) > 0 {
		costIncrease = true
		summary = summary + fmt.Sprintf("There are increase in costs on: '%s'", strings.Join(costInc, "', '"))
	}
	if len(costDec) > 0 {
		start := "There"
		if len(summary) > 0 {
			start = ". And there"
		}
		summary = summary + fmt.Sprintf("%s are decrease in costs on: '%s'", start, strings.Join(costDec, "', '"))
	}
	if len(costInc) == 0 && len(costDec) == 0 {
		summary = "No cost change found!"
	}
	return
}

// --- helper functions ---

func currency(value float64) string {
	ac := accounting.Accounting{Symbol: "$", Precision: 2}
	return ac.FormatMoneyFloat64(value)
}

func currencyDiff(value float64) string {
	ac := accounting.Accounting{Symbol: "$", Precision: 2, FormatZero: " "}
	valueFormated := ac.FormatMoneyFloat64(value)
	if value > 0 {
		return fmt.Sprintf("**+%s (%s)**", valueFormated, upArrow)
	} else if value < 0 {
		return fmt.Sprintf("%s (%s)", valueFormated, downArrow)
	}
	return valueFormated
}

func percDiff(perc float64) string {
	if perc != 0 {
		percFormated := fmt.Sprintf("%.2f%%", perc)
		if perc > 0 {
			return fmt.Sprintf("**+%s (%s)**", percFormated, upArrow)
		} else if perc < 0 {
			return fmt.Sprintf("%s (%s)", percFormated, downArrow)
		}
		return percFormated
	}
	return " "
}
