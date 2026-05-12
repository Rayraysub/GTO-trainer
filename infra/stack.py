"""
stack.py
--------
GTO Trainer AWS 基础设施
包含：VPC / ECR / ECS Fargate / RDS PostgreSQL / ElastiCache Redis / ALB
"""

from aws_cdk import (
    Stack, Duration, RemovalPolicy,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_ecr as ecr,
    aws_rds as rds,
    aws_elasticache as elasticache,
    aws_secretsmanager as secretsmanager,
    aws_logs as logs,
    aws_iam as iam,
)
from constructs import Construct
import json


class GtoTrainerStack(Stack):

    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        # ── VPC ───────────────────────────────────────────
        vpc = ec2.Vpc(
            self, "GtoVpc",
            max_azs=2,
            nat_gateways=1,          # 省钱：只用1个NAT
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

        # ── Security Groups ───────────────────────────────
        # ALB 安全组：允许外部 80/443
        alb_sg = ec2.SecurityGroup(self, "AlbSg", vpc=vpc,
                                   description="ALB security group")
        alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80))
        alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443))

        # ECS 安全组：只允许 ALB 进入
        ecs_sg = ec2.SecurityGroup(self, "EcsSg", vpc=vpc,
                                   description="ECS tasks security group")
        ecs_sg.add_ingress_rule(alb_sg, ec2.Port.tcp(8000))

        # RDS 安全组：只允许 ECS 进入
        rds_sg = ec2.SecurityGroup(self, "RdsSg", vpc=vpc,
                                   description="RDS security group")
        rds_sg.add_ingress_rule(ecs_sg, ec2.Port.tcp(5432))

        # Redis 安全组：只允许 ECS 进入
        redis_sg = ec2.SecurityGroup(self, "RedisSg", vpc=vpc,
                                     description="Redis security group")
        redis_sg.add_ingress_rule(ecs_sg, ec2.Port.tcp(6379))

        # ── Secrets Manager ───────────────────────────────
        # 数据库密码（自动生成，不用手动管理）
        db_secret = secretsmanager.Secret(
            self, "DbSecret",
            secret_name="gto-trainer/db-password",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template=json.dumps({"username": "gto_admin"}),
                generate_string_key="password",
                exclude_punctuation=True,
                password_length=32,
            ),
        )

        # JWT Secret
        jwt_secret = secretsmanager.Secret(
            self, "JwtSecret",
            secret_name="gto-trainer/jwt-secret",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                exclude_punctuation=True,
                password_length=64,
            ),
        )

        # Flask Secret Key
        flask_secret = secretsmanager.Secret(
            self, "FlaskSecret",
            secret_name="gto-trainer/flask-secret",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                exclude_punctuation=True,
                password_length=64,
            ),
        )

        # ── RDS PostgreSQL ────────────────────────────────
        db = rds.DatabaseInstance(
            self, "GtoDb",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_15
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3, ec2.InstanceSize.MICRO  # 最小省钱
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            security_groups=[rds_sg],
            credentials=rds.Credentials.from_secret(db_secret),
            database_name="gto_trainer",
            allocated_storage=20,
            backup_retention=Duration.days(7),
            deletion_protection=False,           # 开发阶段方便删除
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ── ElastiCache Redis ─────────────────────────────
        redis_subnet_group = elasticache.CfnSubnetGroup(
            self, "RedisSubnetGroup",
            description="Redis subnet group",
            subnet_ids=[s.subnet_id for s in vpc.isolated_subnets],
        )

        redis = elasticache.CfnCacheCluster(
            self, "GtoRedis",
            cache_node_type="cache.t3.micro",    # 最小省钱
            engine="redis",
            num_cache_nodes=1,
            vpc_security_group_ids=[redis_sg.security_group_id],
            cache_subnet_group_name=redis_subnet_group.ref,
        )

        # ── ECR（存 Docker 镜像）─────────────────────────
        ecr_repo = ecr.Repository(
            self, "GtoRepo",
            repository_name="gto-trainer",
            removal_policy=RemovalPolicy.DESTROY,
            lifecycle_rules=[
                ecr.LifecycleRule(max_image_count=5)  # 只保留最近5个镜像
            ],
        )

        # ── ECS Cluster ───────────────────────────────────
        cluster = ecs.Cluster(self, "GtoCluster", vpc=vpc)

        # ── Task IAM Role（允许读取 Secrets Manager）─────
        task_role = iam.Role(
            self, "TaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        db_secret.grant_read(task_role)
        jwt_secret.grant_read(task_role)
        flask_secret.grant_read(task_role)

        # ── ECS Task Definition ───────────────────────────
        task_def = ecs.FargateTaskDefinition(
            self, "GtoTaskDef",
            memory_limit_mib=512,
            cpu=256,
            task_role=task_role,
        )

        # 构建数据库 URL
        db_url = f"postgresql://gto_admin:{db_secret.secret_value_from_json('password').unsafe_unwrap()}@{db.db_instance_endpoint_address}:5432/gto_trainer"
        redis_url = f"redis://{redis.attr_redis_endpoint_address}:{redis.attr_redis_endpoint_port}/0"

        # 容器定义
        container = task_def.add_container(
            "GtoContainer",
            image=ecs.ContainerImage.from_ecr_repository(ecr_repo, tag="latest"),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="gto-trainer",
                log_retention=logs.RetentionDays.ONE_WEEK,
            ),
            environment={
                "FLASK_ENV":          "production",
                "EQUITY_SIMULATIONS": "1500",
            },
            secrets={
                "DATABASE_URL": ecs.Secret.from_secrets_manager(db_secret, "database_url"),
                "REDIS_URL":    ecs.Secret.from_secrets_manager(flask_secret, "redis_url"),
                "JWT_SECRET":   ecs.Secret.from_secrets_manager(jwt_secret),
                "SECRET_KEY":   ecs.Secret.from_secrets_manager(flask_secret),
            },
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "curl -f http://localhost:8000/api/health || exit 1"],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                retries=3,
            ),
        )
        container.add_port_mappings(ecs.PortMapping(container_port=8000))

        # ── ALB + Fargate Service ─────────────────────────
        fargate_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, "GtoService",
            cluster=cluster,
            task_definition=task_def,
            desired_count=1,
            security_groups=[ecs_sg],
            assign_public_ip=False,
            public_load_balancer=True,
        )

        # 健康检查设置
        fargate_service.target_group.configure_health_check(
            path="/api/health",
            healthy_http_codes="200",
            interval=Duration.seconds(30),
            timeout=Duration.seconds(5),
            healthy_threshold_count=2,
            unhealthy_threshold_count=3,
        )

        # Auto Scaling（可选，节省成本时设为1）
        scaling = fargate_service.service.auto_scale_task_count(
            min_capacity=1,
            max_capacity=3,
        )
        scaling.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=70,
            scale_in_cooldown=Duration.seconds(60),
            scale_out_cooldown=Duration.seconds(60),
        )
