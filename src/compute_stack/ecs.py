from typing import Dict

from aws_cdk import (
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecr as ecr,
    aws_logs,
    aws_cloudwatch as cloudwatch,
    Duration,
    aws_elasticloadbalancingv2 as elbv2,
    aws_applicationautoscaling as autoscaling,
    RemovalPolicy,
)
from constructs import Construct


class Ecs(Construct):
    _config: Dict
    _cluster: ecs.ICluster
    _selenium_service: ecs.FargateService
    _vpc: ec2.Vpc

    def __init__(
        self,
        scope: Construct,
        id: str,
        config: Dict,
        vpc: ec2.Vpc,
    ) -> None:
        super().__init__(scope, id)
        self._config = config
        self._vpc = vpc
        self.__create_ecs_cluster()
        for index in range(0, config["compute"]["ecs"]["selenium"]["service_count"]):
            self.__create_selenium_service(index)

    def __create_ecs_cluster(self):
        # Create ECS cluster
        self._cluster = ecs.Cluster(
            self,
            "selenium",
            cluster_name="selenium_cluster_" + self._config["stage"],
            vpc=self._vpc,
        )

    def __create_selenium_service(self, index):
        # Create Fargate task definition for ui

        # Import ECR repository for ui

        # Create Fargate task definition for ui
        selenium_taskdef = ecs.FargateTaskDefinition(
            self,
            "selenium-taskdef" + str(index),
            memory_limit_mib=self._config["compute"]["ecs"]["selenium"]["memory"],
            cpu=self._config["compute"]["ecs"]["selenium"]["cpu"],
        )

        selenium_container = selenium_taskdef.add_container(
            "ui-container" + str(index),
            image=ecs.ContainerImage.from_registry(
                name=self._config["compute"]["ecs"]["selenium"]["repo_arn"]
                + ":"
                + self._config["compute"]["ecs"]["selenium"]["image_tag"],
            ),
            logging=ecs.LogDriver.aws_logs(
                stream_prefix="Seleniumwebapp" + str(index),
                log_group=aws_logs.LogGroup(
                    self,
                    "SeleniumWebAppServerLogGroup" + str(index),
                    log_group_name="/ecs/Seleniumwebapp-server" + str(index),
                    retention=aws_logs.RetentionDays.ONE_WEEK,
                    removal_policy=RemovalPolicy.DESTROY,
                ),
            ),
        )
        selenium_container.add_port_mappings(
            ecs.PortMapping(
                container_port=self._config["compute"]["ecs"]["selenium"]["port"]
            )
        )

        capacity = [
            ecs.CapacityProviderStrategy(
                capacity_provider="FARGATE_SPOT",
                weight=self._config["compute"]["ecs"]["selenium"]["fargate_spot"][
                    "weight"
                ],
                base=self._config["compute"]["ecs"]["selenium"]["fargate_spot"]["base"],
            ),
            ecs.CapacityProviderStrategy(
                capacity_provider="FARGATE",
                weight=self._config["compute"]["ecs"]["selenium"]["fargate"]["weight"],
                base=self._config["compute"]["ecs"]["selenium"]["fargate"]["base"],
            ),
        ]

        selenium_security_group = ec2.SecurityGroup(
            self,
            "SeleniumWebAppSecurityGroup" + str(index),
            vpc=self._vpc,
            allow_all_outbound=True,
        )
        selenium_security_group.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.all_traffic(),
        )
        self._selenium_service = ecs.FargateService(
            self,
            "Seleniumwebapp-service" + str(index),
            cluster=self._cluster,
            security_groups=[selenium_security_group],
            desired_count=self._config["compute"]["ecs"]["selenium"][
                "minimum_containers"
            ],
            service_name="Seleniumwebapp-" + self._config["stage"],
            task_definition=selenium_taskdef,
            assign_public_ip=True,
            capacity_provider_strategies=capacity,
        )

        # Enable auto scaling for the frontend service
        scaling = autoscaling.ScalableTarget(
            self,
            "Selenium-webapp-scaling" + str(index),
            service_namespace=autoscaling.ServiceNamespace.ECS,
            resource_id=f"service/{self._cluster.cluster_name}/{self._selenium_service.service_name}",
            scalable_dimension="ecs:service:DesiredCount",
            min_capacity=self._config["compute"]["ecs"]["selenium"][
                "minimum_containers"
            ],
            max_capacity=self._config["compute"]["ecs"]["selenium"][
                "maximum_containers"
            ],
        )

        scaling.scale_on_metric(
            "ScaleToCPUWithMultipleDatapoints" + str(index),
            metric=cloudwatch.Metric(
                namespace="AWS/ECS",
                metric_name="CPUUtilization",
            ),
            scaling_steps=[
                autoscaling.ScalingInterval(change=-1, lower=10),
                autoscaling.ScalingInterval(change=+1, lower=50),
                autoscaling.ScalingInterval(change=+3, lower=70),
            ],
            evaluation_periods=10,
            datapoints_to_alarm=6,
        )

        self.__setup_application_load_balancer(index)

    def __setup_application_load_balancer(self, index):
        # Create security group for the load balancer
        lb_security_group = ec2.SecurityGroup(
            self,
            "LoadBalancerSecurityGroup" + str(index),
            vpc=self._cluster.vpc,
            allow_all_outbound=True,
        )
        lb_security_group.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(80),
        )
        lb_security_group.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(443),
        )

        # Create load balancer
        self.lb = elbv2.ApplicationLoadBalancer(
            self,
            "LoadBalancer" + str(index),
            vpc=self._cluster.vpc,
            internet_facing=True,
            security_group=lb_security_group,
        )

        # Create target group
        target_group = elbv2.ApplicationTargetGroup(
            self,
            "TargetGroup" + str(index),
            vpc=self._cluster.vpc,
            port=self._config["compute"]["ecs"]["selenium"]["port"],
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[self._selenium_service],
            health_check=elbv2.HealthCheck(
                path="/ui",
                protocol=elbv2.Protocol.HTTP,
                port=str(self._config["compute"]["ecs"]["selenium"]["port"]),
                interval=Duration.seconds(60),
                timeout=Duration.seconds(30),
                healthy_threshold_count=2,
                unhealthy_threshold_count=5,
            ),
        )

        # Create HTTP listener for redirection
        http_listener = self.lb.add_listener(
            "HttpListener" + str(index),
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            default_target_groups=[target_group],
        )
