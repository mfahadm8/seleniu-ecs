import boto3
import datetime
import os
import logging

ecs_client = boto3.client("ecs")
CLUSTER_NAME = os.environ.get("CLUSTER_NAME", "selenium_cluster_dev")
BACKEND_SERVICE = os.environ.get("BACKEND_SERVICE", "backendserver-dev")
FRONTEND_SERVICE = os.environ.get("FRONTEND_SERVICE", "clientwebapp-dev")
LOAD_BALANCER_NAME = os.environ.get(
    "LOAD_BALANCER_NAME", "app/Compu-EcsLo-HXKI6OBC4EXH/a3d25a18c140292c"
)
API_SERVER = bool(int(os.environ.get("API_SERVER")))
ECS_SERVER = bool(int(os.environ.get("ECS_SERVER")))
ec2_client = boto3.client("ec2")

logging.getLogger().setLevel(logging.INFO)


def handler(event, context):
    # Calculate the start time and end time based on the current time
    end_time = datetime.datetime.now()
    start_time = end_time - datetime.timedelta(hours=1)
    prevent_stop = 0
    cloudwatch = boto3.client("cloudwatch")
    response = cloudwatch.get_metric_data(
        MetricDataQueries=[
            {
                "Id": "activeConnectionCount",
                "MetricStat": {
                    "Metric": {
                        "Namespace": "AWS/ApplicationELB",
                        "MetricName": "ActiveConnectionCount",
                        "Dimensions": [
                            {"Name": "LoadBalancer", "Value": LOAD_BALANCER_NAME}
                        ],
                    },
                    "Period": 60,
                    "Stat": "Average",
                    "Unit": "Count",
                },
                "ReturnData": True,
            },
        ],
        StartTime=start_time,
        EndTime=end_time,
    )

    logging.info(response)

    # Check if there were no requestCount during the hour
    if (
        not response["MetricDataResults"][0]["Values"]
        or max(response["MetricDataResults"][0]["Values"]) < 2.01
    ):
        if ECS_SERVER == True:
            ecs_response = ecs_client.update_service(
                cluster=CLUSTER_NAME,
                service=BACKEND_SERVICE,
                desiredCount=0,
            )
            logging.info(ecs_response)
            ecs_response = ecs_client.update_service(
                cluster=CLUSTER_NAME,
                service=FRONTEND_SERVICE,
                desiredCount=0,
            )
            logging.info(ecs_response)

        if API_SERVER == True:
            filters = [{"Name": "tag:" + "Name", "Values": ["apiserver"]}]

            response = ec2_client.describe_instances(Filters=filters)
            instance_id = (
                response["Reservations"][0]["Instances"][0]["InstanceId"]
                if "InstanceId" in response["Reservations"][0]["Instances"][0]
                else False
            )
            if instance_id:
                ec2_response = ec2_client.stop_instances(InstanceIds=[instance_id])
                logging.info(ec2_response)

        return {
            "statusCode": 202,
            "body": "No RequestCount found, desired count set to 0.",
        }

    return {"statusCode": 201, "body": "RequestCount found, No action needed."}
