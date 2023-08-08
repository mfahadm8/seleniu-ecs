from typing import Dict

from aws_cdk import aws_ec2 as ec2, aws_ssm as ssm, Stack

from utils.stack_util import add_tags_to_stack
from .vpc import Vpc
from constructs import Construct


class NetworkStack(Stack):
    _vpc: ec2.IVpc
    config: Dict

    def __init__(self, scope: Construct, id: str, config: Dict, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.config = config
        # Apply common tags to stack resources.
        add_tags_to_stack(self, config)

        vpcConstruct = Vpc(self, "Vpc", config)
        self._vpc = vpcConstruct.vpc
        self.__push_vpc_id_cidr()

    def __push_vpc_id_cidr(self):
        vpc_id = self._vpc.vpc_id
        vpc_cidr_block = self._vpc.vpc_cidr_block

        ssm.StringParameter(
            scope=self,
            id="vpcId",
            tier=ssm.ParameterTier.STANDARD,
            string_value=vpc_id,
            parameter_name=self.config["ssm_infra"] + "vpc",
        )

        ssm.StringParameter(
            scope=self,
            id="vpcCidr",
            tier=ssm.ParameterTier.STANDARD,
            string_value=vpc_cidr_block,
            parameter_name=self.config["ssm_infra"] + "vpcCidrBlock",
        )
