module github.com/fernandorubbo/k8s-cost-estimator

go 1.15

require (
	cloud.google.com/go v0.123.0
	github.com/google/go-cmp v0.7.0
	github.com/leekchan/accounting v1.0.0
	github.com/olekukonko/tablewriter v0.0.5
	github.com/sirupsen/logrus v1.9.4
	google.golang.org/api v0.276.0
	google.golang.org/genproto v0.0.0-20201109203340-2640f1f9cdfb
	gopkg.in/yaml.v2 v2.4.0
	k8s.io/api v0.36.0
	k8s.io/apimachinery v0.36.0
	sigs.k8s.io/yaml v1.6.0
)
