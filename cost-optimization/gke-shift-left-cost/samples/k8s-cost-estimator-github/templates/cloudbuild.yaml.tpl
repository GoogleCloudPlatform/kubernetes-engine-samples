steps:

- name: us-central1-docker.pkg.dev/GCP_PROJECT_ID/docker-repo/k8s-cost-estimator:v0.0.1
  entrypoint: 'bash'
  args: 
    - '-c'
    - |
      set -e

      echo ""
      echo "*************************************************************************"
      echo "** Checking out '$_BASE_BRANCH' branch ..."
      echo "*************************************************************************"
      git config --global user.email "GITHUB_EMAIL" && git config --global user.name "GITHUB_USER"
      mkdir previous
      git clone https://github.com/GITHUB_USER/k8s-cost-estimator-github.git previous/
      cd previous
      git checkout $_BASE_BRANCH
      cd ..

      echo ""
      echo "*************************************************************************"
      echo "** Estimating cost difference between current and previous versions..."
      echo "*************************************************************************"
      k8s-cost-estimator --k8s wordpress --k8s-prev previous/wordpress --output output.json --environ=GITHUB

      echo ""
      echo "***************************************************************************************************************"
      echo "** Updating Pull Request '$_PR_NUMBER' ..."
      echo "***************************************************************************************************************" 
      createObject() {
        url=$$1
        body=$$2
        resp=$(curl -w "\nSTATUS_CODE:%{http_code}\n" -X POST -H "Accept: application/vnd.github.v3+json" -H "Authorization: Bearer $_GITHUB_TOKEN" -d "$$body"  $$url)
        httpStatusCode=$([[ $$resp =~ [[:space:]]*STATUS_CODE:([0-9]{3}) ]] && echo $${BASH_REMATCH[1]})
        if [ $$httpStatusCode != "201" ] 
          then
            echo "Error creating object!"
            echo "\- URL: $$url "
            echo "\- BODY: $$body "
            echo "\- RESPONSE: $$resp "
            exit -1
        fi
      }

      comments_url="https://api.github.com/repos/GITHUB_USER/k8s-cost-estimator-github/issues/$_PR_NUMBER/comments"
      comments_body="$(cat output.json)"
      createObject $$comments_url "$$comments_body"

      COST_USD_THRESHOLD=$_GITHUB_FINOPS_COST_USD_THRESHOLD
      POSSIBLY_COST_INCREASE=$(cat output.diff | jq ".summary.maxDiff.usd")
      if (( $(echo "$$POSSIBLY_COST_INCREASE > $$COST_USD_THRESHOLD" | bc -l) ))
        then
          echo ""
          echo "****************************************************************************************"
          echo "** Possible cost increase bigger than \$ $$COST_USD_THRESHOLD USD detected. Requesting FinOps approval ..."
          echo "****************************************************************************************"   
          reviewers_url="https://api.github.com/repos/GITHUB_USER/k8s-cost-estimator-github/pulls/$_PR_NUMBER/requested_reviewers"
          reviewers_body="{\"reviewers\":[\"$_GITHUB_FINOPS_REVIEWER_USER\"]}"
          createObject $$reviewers_url "$$reviewers_body"
        else
          echo ""
          echo "****************************************************************************************************************"
          echo "** No cost increase bigger than \$ $$COST_USD_THRESHOLD USD detected. FinOps approval is NOT required in this situation!"
          echo "****************************************************************************************************************"
      fi