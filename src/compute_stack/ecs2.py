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
    vpc: ec2.Vpc

    def __init__(
        self,
        scope: Construct,
        id: str,
        config: Dict,
        vpc: ec2.Vpc,
    ) -> None:
        super().__init__(scope, id)
        self._config = config
        self.vpc = vpc
        self.selenium_version = config["compute"]["ecs2"].get(
            "selenium_version", "3.141.59"
        )
        self.memory = config["compute"]["ecs2"].get("memory", 512)
        self.cpu = config["compute"]["ecs2"].get("cpu", 256)
        self.selenium_node_max_instances = config["compute"]["ecs2"].get(
            "selenium_node_max_instances", 5
        )
        self.selenium_node_max_sessions = config["compute"]["ecs2"].get(
            "selenium_node_max_sessions", 5
        )
        self.min_instances = config["compute"]["ecs2"].get("min_instances", 1)
        self.max_instances = config["compute"]["ecs2"].get("max_instances", 10)

        cluster = ecs.Cluster(self, "cluster", vpc=self.vpc, container_insights=True)
        cfn_ecs_cluster = cluster.node.default_child
        cfn_ecs_cluster.capacity_providers = ["FARGATE", "FARGATE_SPOT"]
        cfn_ecs_cluster.default_capacity_provider_strategy = [
            {
                "capacity_provider": "FARGATE",
                "weight": 1,
                "base": 4,
            },
            {
                "capacity_provider": "FARGATE_SPOT",
                "weight": 4,
            },
        ]

        security_group = ec2.SecurityGroup(
            self, "security-group-selenium", vpc=cluster.vpc, allow_all_outbound=True
        )
        security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(4444), "Port 4444 for inbound traffic"
        )
        security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(5555), "Port 5555 for inbound traffic"
        )

        load_balancer = elbv2.ApplicationLoadBalancer(
            self, "app-lb", vpc=self.vpc, internet_facing=True
        )
        load_balancer.add_security_group(security_group)

        self.create_hub_resources(
            cluster=cluster,
            identifier="hub",
            load_balancer=load_balancer,
            security_group=security_group,
            stack=self,
            max_instances=self.max_instances,
            min_instances=self.min_instances,
        )

        self.create_browser_resource(
            cluster=cluster,
            identifier="chrome",
            load_balancer=load_balancer,
            security_group=security_group,
            stack=self,
            max_instances=self.max_instances,
            min_instances=self.min_instances,
            image="selenium/node-chrome",
        )

    def create_hub_resources(
        self,
        cluster,
        identifier,
        load_balancer,
        security_group,
        stack,
        max_instances,
        min_instances,
    ):
        service = self.create_service(
            cluster,
            identifier,
            load_balancer,
            security_group,
            stack,
            max_instances,
            min_instances,
            env={
                "GRID_BROWSER_TIMEOUT": "200000",
                "GRID_TIMEOUT": "180",
                "SE_OPTS": "-debug",
            },
            image=f"selenium/hub:{self.selenium_version}",
        )

        self.create_scaling_policy(
            cluster_name=cluster.cluster_name,
            service_name=service.service_name,
            identifier=identifier,
            stack=stack,
            min_instances=min_instances,
            max_instances=max_instances,
        )

        listener = load_balancer.add_listener(
            "Listener", port=4444, protocol=elbv2.ApplicationProtocol.HTTP
        )
        service.register_load_balancer_targets(
            container_name="selenium-hub-container",
            container_port=4444,
            new_target_group_id="ECS",
            protocol=ecs.Protocol.TCP,
            listener=ecs.ListenerConfig.application_listener(
                listener,
                protocol=elbv2.ApplicationProtocol.HTTP,
                port=4444,
                targets=[service],
            ),
        )

    def create_browser_resource(
        self,
        cluster,
        identifier,
        load_balancer,
        security_group,
        stack,
        max_instances,
        min_instances,
        image,
    ):
        service = self.create_service(
            cluster,
            identifier,
            load_balancer,
            security_group,
            stack,
            max_instances,
            min_instances,
            env={
                "HUB_PORT_4444_TCP_ADDR": load_balancer.load_balancer_dns_name,
                "HUB_PORT_4444_TCP_PORT": "4444",
                "NODE_MAX_INSTANCES": str(self.selenium_node_max_instances),
                "NODE_MAX_SESSION": str(self.selenium_node_max_sessions),
                "SE_OPTS": "-debug",
                "shm_size": "512",
            },
            image=f"{image}:{self.selenium_version}",
            entry_point=["sh", "-c"],
            command=[
                "PRIVATE=$(curl -s http://169.254.170.2/v2/metadata | jq -r '.Containers[1].Networks[0].IPv4Addresses[0]') ; "
                'export REMOTE_HOST="http://$PRIVATE:5555" ; /opt/bin/entry_point.sh'
            ],
        )

        self.create_scaling_policy(
            cluster_name=cluster.cluster_name,
            service_name=service.service_name,
            identifier=identifier,
            stack=stack,
            min_instances=min_instances,
            max_instances=max_instances,
        )

    def create_service(
        self,
        cluster,
        identifier,
        load_balancer,
        security_group,
        stack,
        max_instances,
        min_instances,
        env=None,
        image=None,
        entry_point=None,
        command=None,
    ):
        task_definition = ecs.FargateTaskDefinition(
            stack,
            f"selenium-{identifier}-task-def",
            memory_limit_mib=self.memory,
            cpu=self.cpu,
        )
        container_definition = task_definition.add_container(
            f"selenium-{identifier}-container",
            image=ecs.ContainerImage.from_registry(image),
            memory_limit_mib=self.memory,
            cpu=self.cpu,
            environment=env,
            essential=True,
            logging=ecs.LogDriver.aws_logs(
                stream_prefix="Seleniumwebapp-" + identifier,
                log_group=aws_logs.LogGroup(
                    self,
                    "SeleniumWebAppServerLogGroup-" + identifier,
                    log_group_name="/ecs/Seleniumwebapp-" + identifier,
                    retention=aws_logs.RetentionDays.ONE_WEEK,
                    removal_policy=RemovalPolicy.DESTROY,
                ),
            ),
            entry_point=entry_point,
            command=command,
        )
        container_definition.add_port_mappings(
            ecs.PortMapping(
                container_port=4444, host_port=4444, protocol=ecs.Protocol.TCP
            )
        )

        return ecs.FargateService(
            stack,
            f"selenium-{identifier}-service",
            cluster=cluster,
            task_definition=task_definition,
            assign_public_ip=True,
            min_healthy_percent=75,
            max_healthy_percent=100,
            security_groups=[security_group],
        )

    def create_scaling_policy(
        self,
        cluster_name,
        service_name,
        identifier,
        stack,
        max_instances,
        min_instances,
    ):
        target = autoscaling.ScalableTarget(
            stack,
            f"selenium-scalableTarget-{identifier}",
            service_namespace=autoscaling.ServiceNamespace.ECS,
            max_capacity=max_instances,
            min_capacity=min_instances,
            resource_id=f"service/{cluster_name}/{service_name}",
            scalable_dimension="ecs:service:DesiredCount",
        )

        worker_utilization_metric = cloudwatch.Metric(
            namespace="AWS/ECS",
            metric_name="CPUUtilization",
            statistic="max",
            period=Duration.minutes(1),
            dimensions_map={
                "ClusterName": cluster_name,
                "ServiceName": service_name,
            },
        )

        target.scale_on_metric(
            f"step-metric-scaling-{identifier}",
            metric=worker_utilization_metric,
            adjustment_type=autoscaling.AdjustmentType.CHANGE_IN_CAPACITY,
            scaling_steps=[{"upper": 30, "change": -1}, {"lower": 80, "change": 3}],
            cooldown=Duration.seconds(180),
        )
