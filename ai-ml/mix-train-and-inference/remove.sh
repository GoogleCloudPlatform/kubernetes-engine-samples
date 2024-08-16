#!/bin/zsh

cd gke-platform
sed -ie 's/"deletion_protection": true/"deletion_protection": false/g' terraform.tfstate
terraform destroy --auto-approve
cd -
