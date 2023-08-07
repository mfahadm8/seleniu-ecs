import os
import boto3
import logging
import datetime

ecs_client = boto3.client("ecs")
ec2_client = boto3.client("ec2")
API_SERVER = bool(int(os.environ.get("API_SERVER")))
ECS_SERVER = bool(int(os.environ.get("ECS_SERVER")))

logging.getLogger().setLevel(logging.INFO)


def handler(event, context):
    # Update ECS service desired count
    cluster_name = os.environ["CLUSTER_NAME"]
    BACKEND_SERVICE = os.environ["BACKEND_SERVICE"]
    FRONTEND_SERVICE = os.environ["FRONTEND_SERVICE"]

    if ECS_SERVER == True:
        ecs_response = ecs_client.update_service(
            cluster=cluster_name,
            service=BACKEND_SERVICE,
            desiredCount=1,
        )
        logging.info(ecs_response)
        ecs_response = ecs_client.update_service(
            cluster=cluster_name,
            service=FRONTEND_SERVICE,
            desiredCount=1,
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
            ec2_response = ec2_client.start_instances(InstanceIds=[instance_id])

            logging.info(ec2_response)

    return {
        "statusCode": 200,
        "body": "Successfully kick started instance and ecs service!",
    }
