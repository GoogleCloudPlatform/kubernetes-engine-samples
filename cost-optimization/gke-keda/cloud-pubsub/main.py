# -*- coding: utf-8 -*-
"""Pub/Sub pull example on Google Kubernetes Engine.

This program pulls messages from a Cloud Pub/Sub topic and
prints to standard output.
"""

import datetime
import time

# [START gke_keda_pubsub_pull]
# [START container_keda_pubsub_pull]
from google import auth
from google.cloud import pubsub_v1


def main():
    """Continuously pull messages from subsciption"""

    # read default project ID
    _, project_id = auth.default()
    subscription_id = 'keda-echo-read'

    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(
        project_id, subscription_id)

    def callback(message: pubsub_v1.subscriber.message.Message) -> None:
        """Process received message"""
        print(f"Received message: ID={message.message_id} Data={message.data}")
        print(f"[{datetime.datetime.now()}] Processing: {message.message_id}")
        time.sleep(3)
        print(f"[{datetime.datetime.now()}] Processed: {message.message_id}")
        message.ack()

    streaming_pull_future = subscriber.subscribe(
        subscription_path, callback=callback)
    print(f"Pulling messages from {subscription_path}...")

    with subscriber:
        try:
            streaming_pull_future.result()
        except Exception as e:
            print(e)
# [END container_keda_pubsub_pull]
# [END gke_keda_pubsub_pull]


if __name__ == '__main__':
    main()
