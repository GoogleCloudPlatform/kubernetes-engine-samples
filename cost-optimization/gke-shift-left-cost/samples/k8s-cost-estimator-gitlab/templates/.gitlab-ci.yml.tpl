image: 
  name: us-central1-docker.pkg.dev/GCP_PROJECT_ID/docker-repo/k8s-cost-estimator:v0.0.1
  entrypoint: ["bash", "-c"]

workflow:
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
      when: always
    - when: never

estimate-cost: 
  tags: 
    - "k8s-cost-estimator-runner"
  script: |
    set -e

    echo ""
    echo "*************************************************************************"
    echo "** Checking out '$CI_MERGE_REQUEST_TARGET_BRANCH_NAME' branch ..."
    echo "*************************************************************************"
    git config --global user.email "GITLAB_EMAIL" && git config --global user.name "GITLAB_USER"
    mkdir previous
    git clone https://gitlab.com/GITLAB_USER/k8s-cost-estimator-gitlab.git previous/
    cd previous
    git checkout $CI_MERGE_REQUEST_TARGET_BRANCH_NAME
    cd ..

    echo ""
    echo "*************************************************************************"
    echo "** Estimating cost difference between current and previous versions..."
    echo "*************************************************************************"
    k8s-cost-estimator --k8s wordpress --k8s-prev previous/wordpress --output output.json --environ=GITLAB

    echo ""
    echo "***************************************************************************************************************"
    echo "** Updating Merge Request 'projects/$CI_MERGE_REQUEST_PROJECT_ID/merge_requests/$CI_MERGE_REQUEST_IID' ..."
    echo "***************************************************************************************************************"    
    createObject() {
      url=$1
      body=$2
      resp=$(curl -w "\nSTATUS_CODE:%{http_code}\n" -X POST -H "content-type:application/json" -H "PRIVATE-TOKEN:$GITLAB_API_TOKEN" -d "$body" $url)
      httpStatusCode=$([[ $resp =~ [[:space:]]*STATUS_CODE:([0-9]{3}) ]] && echo ${BASH_REMATCH[1]})
      if [ $httpStatusCode != "201" ] 
        then
          echo "Error creating object!"
          echo "\- URL: $url "
          echo "\- BODY: $body "
          echo "\- RESPONSE: $resp "
          exit -1
      fi
    }

    comments_url="https://gitlab.com/api/v4/projects/$CI_MERGE_REQUEST_PROJECT_ID/merge_requests/$CI_MERGE_REQUEST_IID/notes"
    comments_body="$(cat output.json)"
    createObject $comments_url "$comments_body"
    
    POSSIBLY_COST_INCREASE=$(cat output.diff | jq ".summary.maxDiff.usd")
    if (( $(echo "$POSSIBLY_COST_INCREASE > $GITLAB_FINOPS_COST_USD_THRESHOLD" | bc -l) ))
      then
        echo ""
        echo "****************************************************************************************"
        echo "** Possible cost increase bigger than \$$GITLAB_FINOPS_COST_USD_THRESHOLD USD detected. Requesting FinOps approval ..."
        echo "****************************************************************************************"    
        reviewers_url="https://gitlab.com/api/v4/projects/$CI_MERGE_REQUEST_PROJECT_ID/merge_requests/$CI_MERGE_REQUEST_IID/approval_rules"
        reviewers_body="{\"name\":\"Require FinOps Approval\", \"approvals_required\":1, \"user_ids\":[$GITLAB_FINOPS_REVIEWER_ID]}"
        createObject $reviewers_url "$reviewers_body"
      else
        echo ""
        echo "****************************************************************************************************************"
        echo "** No cost increase bigger than \$$GITLAB_FINOPS_COST_USD_THRESHOLD USD detected. FinOps approval is NOT required in this situation!"
        echo "****************************************************************************************************************"
    fi