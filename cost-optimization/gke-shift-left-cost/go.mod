module github.com/fernandorubbo/k8s-cost-estimator

go 1.15

require (
	cloud.google.com/go v0.123.0
	github.com/google/go-cmp v0.7.0
	github.com/leekchan/accounting v1.0.0
	github.com/olekukonko/tablewriter v0.0.5
	github.com/sirupsen/logrus v1.10.2
	google.golang.org/api v0.300.0
	google.golang.org/genproto v0.0.0-20201109203340-2640f1f9cdfb
	gopkg.in/yaml.v2 v2.4.0
	k8s.io/api v0.37.1
	k8s.io/apimachinery v0.37.1
	sigs.k8s.io/yaml v1.6.0
)
