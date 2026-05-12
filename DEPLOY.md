# GTO Trainer — AWS 部署指南

## 前置条件
- AWS 账号，已配置 IAM 用户（有 ECS/ECR/RDS/ElastiCache/CDK 权限）
- 本机装好：`aws cli` / `node.js 18+` / `python 3.12` / `docker`
- GitHub 仓库已创建

---

## 第一步：安装 AWS CDK

```bash
npm install -g aws-cdk
cdk --version    # 确认安装成功
```

---

## 第二步：配置 AWS 凭证

```bash
aws configure
# 填入：
#   AWS Access Key ID
#   AWS Secret Access Key
#   Default region: us-east-1
#   Default output format: json
```

---

## 第三步：Bootstrap CDK（每个账号/区域只需一次）

```bash
cdk bootstrap aws://YOUR_ACCOUNT_ID/us-east-1
```

你的 Account ID 在 AWS 控制台右上角可以找到。

---

## 第四步：安装 CDK 依赖并部署基础设施

```bash
cd infrastructure
pip install -r requirements.txt
cdk deploy --context account=YOUR_ACCOUNT_ID --context region=us-east-1
```

这一步会创建：
- VPC + 子网
- RDS PostgreSQL
- ElastiCache Redis
- ECS Cluster + Fargate Service
- ALB（负载均衡）
- ECR 镜像仓库
- Secrets Manager 里的密钥

**大约需要 15-20 分钟。**

部署完成后记录输出里的：
```
GtoTrainerStack.AlbDnsName = xxx.us-east-1.elb.amazonaws.com
GtoTrainerStack.EcrRepoUri  = 123456789.dkr.ecr.us-east-1.amazonaws.com/gto-trainer
```

---

## 第五步：手动推第一个 Docker 镜像

CDK 部署完基础设施，但 ECR 里还没有镜像，需要手动推一次：

```bash
# 在项目根目录（gto_v2/）下执行

# 登录 ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

# 构建镜像
docker build -t gto-trainer .

# 打标签
docker tag gto-trainer:latest \
  YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/gto-trainer:latest

# 推送
docker push \
  YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/gto-trainer:latest
```

---

## 第六步：配置 GitHub Actions（自动部署）

在 GitHub 仓库 → Settings → Secrets → Actions，添加：

| Secret 名称              | 值                        |
|--------------------------|---------------------------|
| `AWS_ACCESS_KEY_ID`      | 你的 AWS Access Key       |
| `AWS_SECRET_ACCESS_KEY`  | 你的 AWS Secret Key       |

之后每次 push 到 `main` 分支，GitHub Actions 自动：
1. 运行测试
2. 构建 Docker 镜像推到 ECR
3. 更新 ECS 服务

---

## 第七步：访问应用

```
http://GtoTrainerStack.AlbDnsName
```

（CDK 输出里的 ALB DNS 地址）

如果你有自己的域名，在 Route 53 或其他 DNS 服务商添加 CNAME 指向 ALB。

---

## 数据库初始化

第一次启动时会自动执行 `init_db()`，建好所有表。
如果需要手动连接 RDS 检查：

```bash
# 通过 ECS Exec 进入容器
aws ecs execute-command \
  --cluster GtoTrainerStack-GtoCluster \
  --task TASK_ID \
  --container GtoContainer \
  --command "/bin/bash" \
  --interactive
```

---

## 费用估算（us-east-1，按月）

| 服务                    | 规格            | 大约费用    |
|-------------------------|-----------------|-------------|
| ECS Fargate             | 0.25 vCPU 512MB | ~$9/月      |
| RDS PostgreSQL          | t3.micro 20GB   | ~$15/月     |
| ElastiCache Redis       | t3.micro        | ~$12/月     |
| ALB                     | 基础费用         | ~$16/月     |
| NAT Gateway             | 1个              | ~$32/月     |
| **合计**                |                 | **~$84/月** |

> 省钱建议：不用的时候把 ECS desired_count 改为 0，RDS 开 pause on inactivity。

---

## 常用命令

```bash
# 查看服务状态
aws ecs describe-services \
  --cluster GtoTrainerStack-GtoCluster \
  --services GtoTrainerStack-GtoService

# 查看日志
aws logs tail /ecs/gto-trainer --follow

# 手动重新部署（不改代码的情况下）
aws ecs update-service \
  --cluster GtoTrainerStack-GtoCluster \
  --service GtoTrainerStack-GtoService \
  --force-new-deployment

# 销毁所有资源（避免产生费用）
cd infrastructure
cdk destroy
```

---

## 环境变量说明

生产环境的环境变量通过 Secrets Manager 注入，不需要 `.env` 文件：

| 变量名           | 来源                        | 说明              |
|------------------|-----------------------------|-------------------|
| `DATABASE_URL`   | Secrets Manager (db-secret) | PostgreSQL 连接串 |
| `REDIS_URL`      | Secrets Manager             | Redis 连接串      |
| `JWT_SECRET`     | Secrets Manager (jwt-secret)| JWT 签名密钥      |
| `SECRET_KEY`     | Secrets Manager             | Flask 密钥        |
| `FLASK_ENV`      | ECS 环境变量                | production        |
