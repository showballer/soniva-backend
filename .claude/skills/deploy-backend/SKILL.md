---
name: deploy-backend
description: 构建并部署 soniva-backend Docker 镜像到线上服务器，带自动回滚。用于用户提到 "部署"、"上线"、"发布"、"更新线上"、"重新打包部署"、"deploy backend"、"release to production"、"push to prod" 等意图。流程包括：交互式收集服务器凭据（IP / 用户名 / 密码 或 SSH key）→ 本地 buildx 跨平台构建 linux/amd64 镜像 → docker save 成 tar → scp 上传 → SSH 执行原子容器替换 → 健康检查 → 失败自动回滚。凭据每次重新询问，绝不写入任何文件。
---

# Soniva Backend 生产部署技能

完整部署流程：本地 arm64 Mac 构建 linux/amd64 镜像 → tar 上传到阿里云 ECS → 原子替换运行中容器 → 健康验证 → 保留回滚 tag。

---

## 项目固定参数（不要问用户，这些是服务器真实状态）

这些值是通过实际侦察生产环境得到的，除非服务器架构重建否则保持不变：

| 项 | 值 |
|---|---|
| 容器名 | `soniva-backend` |
| 镜像名 | `soniva-backend` |
| 构建平台 | `linux/amd64`（本地 Mac arm64 → 服务器 x86_64，必须交叉构建） |
| 端口映射 | `8000:8000` |
| 挂载卷 | `/data/soniva/uploads:/app/uploads` |
| 重启策略 | `unless-stopped` |
| **Docker 网络** | **`mynetwork`（必须！nginx 通过容器名 DNS 访问后端）** |
| 健康检查（容器内） | `GET /health` → `{"status":"healthy"}` |
| 健康检查（外网真实路径） | `GET https://www.showballer.cn/soniva/health` → 200 |
| 服务器项目目录 | `/root/sonvia`（注意是 `sonvia` 不是 `soniva`，别"修正"） |
| 服务器 .env 路径 | `/root/sonvia/.env` |
| 服务器架构 | x86_64（阿里云 ECS，Ubuntu 24.04） |
| 数据库 | 阿里云 RDS MySQL，库名 `soniva_db` |
| 反向代理 | nginx 容器 `my-nginx` 占 80/443；nginx.conf 在 `/root/nginx-conf/nginx.conf`；`location /soniva/ → proxy_pass http://soniva-backend:8000/` |
| 外网访问 | 走 nginx：`https://www.showballer.cn/soniva/...`；直连 8000 被阿里云安全组拦 |

**迁移说明（非常重要）**：项目**没有** `alembic.ini`，`alembic/versions/` 是空的。迁移是 `migrations/` 下的裸 SQL 文件，且 002 有 4 个变体（`continue/final/update/update_fixed`）是历史迭代版本。**绝不要盲跑** `alembic upgrade head`（跑不起来）或任何 SQL。每次部署前先查数据库实际 schema 判断。

**网络说明（踩过的坑，必读）**：nginx 容器 `my-nginx` 在 user-defined bridge 网络 `mynetwork` 里，通过 `proxy_pass http://soniva-backend:8000/` 走**容器名 DNS** 访问后端。`docker run` 时如果**忘记 `--network mynetwork`**，新容器会跑到默认 `bridge` 网络，nginx 就解析不到 `soniva-backend`，导致所有 `https://www.showballer.cn/soniva/...` 请求 502。**所有 `docker run` 命令必须包含 `--network mynetwork`**（含阶段 5 的主启动和回滚分支）。

---

## 触发前置条件（快速检查，失败就停）

在开始任何动作前，静默跑这些检查；任一失败要让用户处理：

```bash
docker info >/dev/null 2>&1 || echo "Docker 未启动"
docker buildx version >/dev/null 2>&1 || echo "buildx 不可用"
which sshpass >/dev/null 2>&1 || {
  echo "sshpass 未安装，建议执行："
  echo "  brew install hudochenkov/sshpass/sshpass"
}
```

如 `sshpass` 缺失且用户选择用密码登录，询问是否自动安装（`brew install hudochenkov/sshpass/sshpass`）。

---

## 阶段 0 — 交互式收集服务器凭据

**规则**：
1. IP / 用户名 / 密码**每次都要问**，不从前次对话或任何文件读取
2. 密码**只存在于单次 Bash 命令的 `SSHPASS` env var 里**，绝不写入文件、不存 memory、不写进技能产物
3. 推荐用户用 SSH key 而非密码

### 问什么、怎么问

用 `AskUserQuestion` 问**认证方式**（这是个有限选项的决策）：

```
Question: 服务器登录方式？
Options:
  - "已配好 SSH key (推荐)" — 不需要密码，更安全
  - "临时用密码" — 密码会在对话中出现一次，用完即弃
```

然后用**普通消息文本**问 IP / 用户名 / 密码（不用 AskUserQuestion，这些是自由输入）：

> 请告诉我：服务器 IP、SSH 用户名（默认 `root`）。若选了密码登录，也请一并粘贴密码。格式例如：
> ```
> IP: 1.2.3.4
> user: root
> password: xxxxx
> ```

**禁止**：
- 不要用默认值硬编码服务器 IP（每次问用户，IP 可能变）
- 不要在技能文件、MEMORY、设置文件里存储密码或 IP
- 不要在确认性 echo / log 里打印密码明文

**使用方式**（把密码放在命令内的 env var 里，不用 `-p` 参数因为那样会出现在 `ps` 里）：

```bash
export SSHPASS='<password-the-user-just-typed>'
sshpass -e ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null <USER>@<IP> "..."
```

SSH key 模式下直接：

```bash
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null <USER>@<IP> "..."
```

---

## 阶段 1 — 只读侦察（不修改任何东西）

单次 SSH 收集全部信息，一次性输出：

```bash
# 变量：SSHPASS（密码模式）、REMOTE=<USER>@<IP>
sshpass -e ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null $REMOTE "
  echo '=== arch ===' && uname -m
  echo '=== disk ===' && df -h / | tail -1
  echo '=== 项目目录 ===' && ls -la /root/sonvia/ 2>/dev/null || echo '不存在'
  echo '=== 当前 soniva-backend 容器 ===' && docker ps -a --filter name=soniva-backend --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
  echo '=== 当前容器所在网络 (必须含 mynetwork) ===' && docker inspect soniva-backend --format 'Networks: {{range \$k,\$v := .NetworkSettings.Networks}}{{\$k}}({{\$v.IPAddress}}) {{end}}' 2>/dev/null || echo '容器不存在'
  echo '=== nginx 容器所在网络 (确认 skill 假设仍成立) ===' && docker inspect my-nginx --format 'Networks: {{range \$k,\$v := .NetworkSettings.Networks}}{{\$k}}({{\$v.IPAddress}}) {{end}}' 2>/dev/null || echo '没有 my-nginx 容器，需要人工核对 nginx 设置'
  echo '=== nginx 配置里对 soniva 的 proxy_pass ===' && grep -nE 'soniva|proxy_pass.*soniva-backend' /root/nginx-conf/nginx.conf 2>/dev/null | head -10
  echo '=== 镜像 ===' && docker images | grep -E 'REPOSITORY|soniva-backend'
  echo '=== uploads 卷 ===' && ls -la /data/soniva/uploads 2>/dev/null | head -5 || echo '不存在'
  echo '=== 服务器 .env key 列表 (只名不值) ==='
  grep -E '^[A-Z_]+=' /root/sonvia/.env 2>/dev/null | cut -d= -f1 | sort
"
```

**停下来报告**（让用户确认继续）：
- 服务器架构（必须是 `x86_64`，否则改 `--platform`）
- 磁盘剩余（至少 1 GB）
- 当前容器是否在跑
- 服务器 .env 是否存在
- 如果有异常（目录不存在、容器不存在、磁盘不足）立即暂停，不要硬冲

### 本地 vs 服务器 .env key diff

```bash
# 本地 key 列表（不打印值）
grep -E '^[A-Z_]+=' .env | cut -d= -f1 | sort > /tmp/local-env-keys.txt

# 和服务器 diff（只比 key，不比值）
diff /tmp/local-env-keys.txt <(sshpass -e ssh ... "grep -E '^[A-Z_]+=' /root/sonvia/.env | cut -d= -f1 | sort")
```

### 数据库 schema 健康检查（决定要不要跑迁移）

```bash
sshpass -e ssh ... "
docker exec soniva-backend python -c \"
from sqlalchemy import create_engine, inspect
import os
insp = inspect(create_engine(os.environ['DATABASE_URL']))
tables = set(insp.get_table_names())
print('has identify_conversations:', 'identify_conversations' in tables)
if 'identify_messages' in tables:
    cols = {c['name'] for c in insp.get_columns('identify_messages')}
    print('identify_messages.tactics:', 'tactics' in cols)
if 'voice_test_results' in tables:
    cols = {c['name'] for c in insp.get_columns('voice_test_results')}
    print('voice_test new cols:', 'auxiliary_tags' in cols and 'signature' in cols)
\"
"
```

根据输出判断：所有 True → 已全迁移，跳过；有 False → 暂停让用户决定手动跑哪个 SQL。

---

## 阶段 2 — 决策点（AskUserQuestion）

### 决策 1：.env 策略

只有当 key diff 显示服务器缺 key 时才问；否则跳过：

```
Question: .env 策略？
Options:
  - "保留服务器 .env 不动 (推荐)"
    新代码如果对缺失 key 有 fallback，能跑。最安全
  - "追加缺失 key 到服务器 .env"
    用本地 .env 里的值补，备份原文件。需确认本地是生产值
  - "完全覆盖服务器 .env"
    风险最大，除非确认本地 = 生产值，否则不选
```

### 决策 2：迁移策略

依据阶段 1 的 schema 检查结果：

- **全已迁移** → 直接告知"所有迁移已应用，跳过"，不要问用户
- **缺失字段** → 暂停，展示缺的字段 + 对应 SQL 文件，问用户要不要跑、跑哪个、是否先备份 DB

**绝不要自动跑 SQL。**

### 决策 3：停机窗口确认

简单确认一条：容器替换会有 10–30 秒服务中断，现在是否合适？

---

## 阶段 3 — 本地构建

```bash
cd <repo-root>
GIT_SHA=$(git rev-parse --short HEAD)

# 后台跑（5-10 分钟），用 run_in_background=true
docker buildx build \
  --platform linux/amd64 \
  --load \
  -t soniva-backend:$GIT_SHA \
  -t soniva-backend:latest \
  . 2>&1 | tee /tmp/soniva-build.log
```

**构建完后验证**：

```bash
docker inspect soniva-backend:latest --format '{{.Os}}/{{.Architecture}}'
# 必须是 linux/amd64，不是就有问题
```

---

## 阶段 4 — 导出 tar + 上传

```bash
docker save soniva-backend:latest soniva-backend:$GIT_SHA -o /tmp/soniva-backend-new.tar

# 如果选了"追加缺失 key"，生成只含缺失 key 的片段（不含值打印）
# 这里只写缺失 key 的几行，不要整个 .env
{
  echo ""
  echo "# ===== Appended on $(date +%Y-%m-%d) ====="
  for key in <missing_keys>; do
    grep -E "^${key}=" .env | head -1
  done
} > /tmp/soniva-env-append.txt

# 上传
sshpass -e scp /tmp/soniva-backend-new.tar \
  [/tmp/soniva-env-append.txt] \
  $REMOTE:/root/sonvia/
```

这步也用 `run_in_background=true`（tar 大约 300-400MB，scp 可能几分钟）。

---

## 阶段 5 — 原子替换（单次 SSH session，`set -e`，带回滚）

**核心脚本**（所有步骤在一个 SSH 会话里，避免中间失败半截状态）：

```bash
sshpass -e ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null $REMOTE 'bash -s' << 'DEPLOY_EOF'
set -e
cd /root/sonvia
TS=$(date +%Y%m%d_%H%M%S)
BACKUP_TAG="rollback-$TS"

# 通用的 run 参数（回滚复用）
# --network mynetwork 是关键——nginx 通过容器名 DNS 访问后端，不在这个网络里就 502
RUN_ARGS="-p 8000:8000 -v /data/soniva/uploads:/app/uploads --env-file /root/sonvia/.env --network mynetwork --restart unless-stopped"

# 回滚函数：停掉新容器，把 rollback tag 重新指向 latest，重启老镜像
rollback() {
  echo "!!! 触发回滚 ($1)"
  docker rm -f soniva-backend 2>/dev/null || true
  docker tag soniva-backend:$BACKUP_TAG soniva-backend:latest
  docker run -d --name soniva-backend $RUN_ARGS soniva-backend:latest
  exit 1
}

# 1. 备份 .env
cp .env .env.bak.$TS

# 2. 追加缺失 key（如果有 append 文件）
if [ -f soniva-env-append.txt ]; then
  cat soniva-env-append.txt >> .env
  # 追加后验证关键 key 存在
  for k in <关键-key-列表>; do
    grep -q "^${k}=" .env || { echo "!!! .env 追加后仍缺 $k"; exit 1; }
  done
fi

# 3. 给当前 latest 打回滚 tag
docker tag soniva-backend:latest soniva-backend:$BACKUP_TAG

# 4. 加载新镜像
docker load -i soniva-backend-new.tar

# 5. 停 + 删旧容器
docker stop soniva-backend
docker rm soniva-backend

# 6. 启动新容器
docker run -d --name soniva-backend $RUN_ARGS soniva-backend:latest \
  || rollback "启动失败"

# 7. 等 8 秒让 uvicorn 完成启动
sleep 8

# 8. 健康检查（两级：容器内 + nginx 代理路径）
# 8a. 直连容器（宿主机 → 127.0.0.1:8000）
if ! curl -sf --max-time 5 http://127.0.0.1:8000/health -o /tmp/health.out; then
  echo "!!! 容器 /health 失败，日志："
  docker logs --tail 40 soniva-backend
  rollback "容器健康检查失败"
fi
# 8b. 确认在 mynetwork 里，nginx 能路由到
if ! docker inspect soniva-backend --format '{{range \$k,\$v := .NetworkSettings.Networks}}{{\$k}} {{end}}' | grep -qw mynetwork; then
  echo "!!! 容器未加入 mynetwork，nginx 会 502"
  rollback "网络配置错误"
fi
# 8c. 从 nginx 容器内部真实走一遍路径（100% 等价于用户访问）
if ! docker exec my-nginx sh -c 'curl -sf --max-time 5 http://soniva-backend:8000/health' >/dev/null 2>&1; then
  # 如果 nginx 容器没有 curl，退而求其次用 wget 或走域名回环
  docker exec my-nginx sh -c 'wget -qO- --timeout=5 http://soniva-backend:8000/health' 2>/dev/null \
    || { echo '!!! nginx 容器访问不到 soniva-backend:8000'; rollback "端到端检查失败"; }
fi

echo "✓ 部署成功"
echo "  回滚 tag: soniva-backend:$BACKUP_TAG"
echo "  .env 备份: /root/sonvia/.env.bak.$TS"
docker ps --filter name=soniva-backend --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
docker logs --tail 20 soniva-backend
DEPLOY_EOF
```

**重要**：
- `rollback()` 函数在任何中间失败都会恢复到旧镜像
- `.env.bak.$TS` 留着，万一 env 也要回滚
- `soniva-backend:$BACKUP_TAG` 留到用户确认稳定才删

---

## 阶段 6 — 清理 + 最终报告

### 立即清理（含密钥的临时文件）

```bash
# 服务器上（如果用了 .env 追加）
sshpass -e ssh $REMOTE "shred -u /root/sonvia/soniva-env-append.txt"

# 本地
rm -f /tmp/soniva-backend-new.tar /tmp/soniva-env-append.txt /tmp/local-env-keys.txt /tmp/soniva-build.log
```

### 展示给用户的最终报告

必须包含：

```
✓ 部署成功
  - 新镜像: soniva-backend:<git-sha> / :latest (linux/amd64)
  - 容器: soniva-backend 运行中，/health 200 OK
  - 回滚 tag: soniva-backend:rollback-<TS>
  - .env 备份: /root/sonvia/.env.bak.<TS>

如需回滚（复制即用，注意 --network mynetwork 不能漏）：
  ssh <USER>@<IP>
  docker stop soniva-backend && docker rm soniva-backend
  docker tag soniva-backend:rollback-<TS> soniva-backend:latest
  docker run -d --name soniva-backend \
    -p 8000:8000 -v /data/soniva/uploads:/app/uploads \
    --env-file /root/sonvia/.env \
    --network mynetwork \
    --restart unless-stopped \
    soniva-backend:latest

稳定运行几天后可清理：
  服务器 /root/sonvia/soniva-backend-new.tar  (~400MB)
  服务器 /root/soniva-backend.tar (如果还在，更老的 tar ~1GB)
  镜像 soniva-backend:rollback-<TS>
```

---

## 常见问题处理

| 症状 | 原因 | 对策 |
|---|---|---|
| `docker buildx build` 卡很久 | 首次交叉编译 librosa/soundfile | 正常，耐心等 |
| 镜像架构是 arm64 | 忘了 `--platform linux/amd64` | 重新 build |
| scp 很慢 | 阿里云跨境网络 | 不要 interrupt；可以用 `pv` 看进度 |
| 健康检查超时 | uvicorn 启动慢（数据库握手） | `sleep` 拉到 15s 重试；仍失败看 `docker logs` |
| 容器起不来 "no module" | 依赖没装上/错平台 | 看 build log，可能是 requirements.txt 未更新 |
| 启动后外网 8000 连不上 | 正常——阿里云安全组只开 80/443，通过 nginx 访问 | 用内网 127.0.0.1:8000 或通过域名验证 |
| `https://www.showballer.cn/soniva/...` 502 / 504 | 容器没在 `mynetwork`，nginx `proxy_pass soniva-backend:8000` 解析失败 | `docker network connect mynetwork soniva-backend` 临时修；长期重建时加 `--network mynetwork` |
| 浏览器访问报证书过期 | 站点 SSL 证书过期（2026-04-15 到期），独立于部署 | 续签证书；部署流程不受影响，用 `curl -k` 或直连容器验证 |
| `docker exec my-nginx curl ...` 报 `not found` | nginx 镜像里没装 curl | 改用 wget：`docker exec my-nginx wget -qO- http://soniva-backend:8000/health` |
| `.env` 里值含特殊字符 | `--env-file` 对引号处理有坑 | 确认 value 不带未转义的 `$`、反引号 |
| 老 tar 文件占磁盘 | 历次部署堆积 | 确认当前容器稳定后手动删 |

---

## 绝对不做的事

- ❌ 把服务器 IP/密码硬编码到任何文件
- ❌ 把密码写到 `.claude/` 下任何地方
- ❌ 不问用户就 `docker rm` 当前容器（一定要先验证新镜像能跑）
- ❌ 自动跑 `alembic upgrade head`（本项目用的不是 alembic）
- ❌ 盲跑 `migrations/*.sql`（002 有 4 个变体，先查 DB schema）
- ❌ `--no-verify`、`--force` 等任何绕过安全检查的参数
- ❌ 部署后不验证 `/health` 就宣布成功
- ❌ 失败不回滚就退出（必须调用 rollback 函数）
- ❌ `docker run` 不带 `--network mynetwork`（nginx 会 502）
- ❌ 修改 `/root/nginx-conf/nginx.conf`（用户明确要求不动 nginx）
- ❌ 只验证容器内 `/health`、不验证 `https://www.showballer.cn/soniva/health`（网络断链会被漏掉）
