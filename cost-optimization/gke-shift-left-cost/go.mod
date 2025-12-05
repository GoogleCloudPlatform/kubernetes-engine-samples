module github.com/fernandorubbo/k8s-cost-estimator

go 1.15

require (
	cloud.google.com/go v0.72.0
	github.com/google/go-cmp v0.5.2
	github.com/leekchan/accounting v1.0.0
	github.com/olekukonko/tablewriter v0.0.4
	github.com/sirupsen/logrus v1.8.3
	google.golang.org/api v0.35.0
	google.golang.org/genproto v0.0.0-20201109203340-2640f1f9cdfb
	gopkg.in/yaml.v2 v2.2.8
	k8s.io/api v0.19.4
	k8s.io/apimachinery v0.19.4
	sigs.k8s.io/yaml v1.2.0
)
