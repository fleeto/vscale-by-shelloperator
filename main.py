#!/usr/bin/env python3
import requests
import subprocess
import json
import logging
import sys
import os

# 设置 log level 为 info
logging.basicConfig(level=logging.INFO)

# Prometheus server URL
PROMETHEUS_URL = 'http://prom-prometheus-server/api/v1/query'

# Prometheus query to get CPU usage rate for nginx container
CPU_USAGE_QUERY = '''(sum(rate(container_cpu_usage_seconds_total{{namespace="{0}", pod="{1}", container="{2}"}}[5m])) by (pod, container) 
/ sum(container_spec_cpu_quota{{namespace="{0}", pod="{1}",container="{2}"}}
/container_spec_cpu_period{{namespace="{0}", pod="{1}", container="{2}"}}) by (pod, container) * 100)'''


def query_prometheus(query):
    response = requests.get(PROMETHEUS_URL, params={'query': query})
    data = response.json()
    if data['status'] == 'success' and data['data']['result']:
        return float(data['data']['result'][0]['value'][1])
    else:
        return None


def get_cpu_usage_and_limit(namespace, pod_name, container_name):
    query = CPU_USAGE_QUERY.format(namespace, pod_name, container_name)
    logging.info(f"Querying Prometheus: {query}")
    cpu_usage = query_prometheus(query)
    return cpu_usage


def scale_cpu_resources(namespace, pod_name, container_name):
    # Get the current resource requests and limits
    result = subprocess.run(
        ["kubectl", "get", "pod", pod_name, "-n", namespace, "-o", "json"],
        capture_output=True, text=True
    )
    pod_data = json.loads(result.stdout)

    containers = pod_data['spec']['containers']
    for container in containers:
        if container['name'] == container_name:
            current_requests = container['resources']['requests']['cpu']
            current_limits = container['resources']['limits']['cpu']

            # Calculate new requests and limits
            new_requests = str(float(current_requests[:-1]) * 2) + 'm'
            new_limits = str(float(current_limits[:-1]) * 2) + 'm'

            # Patch the pod with new requests and limits
            patch = {
                "spec": {
                    "containers": [
                        {
                            "name": container_name,
                            "resources": {
                                "requests": {
                                    "cpu": new_requests
                                },
                                "limits": {
                                    "cpu": new_limits
                                }
                            }
                        }
                    ]
                }
            }
            patch_json = json.dumps(patch)
            subprocess.run(
                ["kubectl", "patch", "pod", pod_name, "-n", namespace, "--patch", patch_json],
                check=True
            )
            logging.info(f"Scaled CPU resources for container {container_name} in pod {pod_name}")


def execute():
    namespace = os.getenv("NAMESPACE")
    pod_name = os.getenv("POD_NAME")
    container_name = os.getenv("CONTAINER_NAME")

    cpu_usage = get_cpu_usage_and_limit(namespace, pod_name, container_name)
    if cpu_usage is not None:
        logging.info(f"CPU Usage Ratio: {cpu_usage:.2f}%")

        if cpu_usage > 80:
            logging.info("CPU usage ratio is greater than 80%, scaling resources...")
            scale_cpu_resources(namespace, pod_name, container_name)
        else:
            print("CPU usage ratio is within limits.")
    else:
        print("Failed to retrieve CPU usage or limit.")


# 如果有 `--config` 参数，则读取 /config/config.json，打印出来
if len(sys.argv) > 1 and sys.argv[1] == "--config":
    with open("/conf/config.yaml", "r") as f:
        print(f.read())
    exit(0)
else:
    execute()