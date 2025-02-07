# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from flask import Flask, jsonify
from flask import request
import logging
import sys,os, time
from kubernetes import client, config, utils
import kubernetes.client
from kubernetes.client.rest import ApiException


app = Flask(__name__)
@app.route('/check')
def message():
    return jsonify({"Message": "Hi there"})


@app.route('/', methods=['POST'])
def bucket():
    request_data = request.get_json()
    print(request_data)
    bckt = request_data['bucket']
    f_name = request_data['name']
    id = request_data['generation'] 
    kube_create_job(bckt, f_name, id)
    return "ok"

# Set logging
logging.basicConfig(stream=sys.stdout, level=logging.INFO)

# Setup K8 configs
config.load_incluster_config()

def kube_create_job_object(name, container_image, bucket_name, f_name, namespace="elastic", container_name="jobcontainer", env_vars={}):

    body = client.V1Job(api_version="batch/v1", kind="Job")
    body.metadata = client.V1ObjectMeta(namespace=namespace, name=name)
    body.status = client.V1JobStatus()
    
    template = client.V1PodTemplate()
    template.template = client.V1PodTemplateSpec()
    env_list = [
        client.V1EnvVar(name="ES_URL", value=os.getenv("ES_URL")),
        client.V1EnvVar(name="INDEX_NAME", value="training-docs"), 
        client.V1EnvVar(name="FILE_NAME", value=f_name), 
        client.V1EnvVar(name="BUCKET_NAME", value=bucket_name),
        client.V1EnvVar(name="PASSWORD", value_from=client.V1EnvVarSource(secret_key_ref=client.V1SecretKeySelector(key="elastic", name="elasticsearch-ha-es-elastic-user"))), 
    ]
    
    container = client.V1Container(name=container_name, image=container_image, image_pull_policy='Always', env=env_list)
    template.template.spec = client.V1PodSpec(containers=[container], restart_policy='Never', service_account='embed-docs-sa')

    body.spec = client.V1JobSpec(backoff_limit=3, ttl_seconds_after_finished=60, template=template.template)
    return body

def kube_test_credentials():
    try: 
        api_response = api_instance.get_api_resources()
        logging.info(api_response)
    except ApiException as e:
        print("Exception when calling API: %s\n" % e)

def kube_create_job(bckt, f_name, id):
    container_image = os.getenv("JOB_IMAGE")
    namespace = os.getenv("JOB_NAMESPACE")
    name = "docs-embedder" + id
    body = kube_create_job_object(name, container_image, bckt, f_name)
    v1=client.BatchV1Api()
    try: 
        v1.create_namespaced_job(namespace, body, pretty=True)
    except ApiException as e:
        print("Exception when calling BatchV1Api->create_namespaced_job: %s\n" % e)
    return

if __name__ == '__main__':
    app.run('0.0.0.0', port=5001, debug=True)
