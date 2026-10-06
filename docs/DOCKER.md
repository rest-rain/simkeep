# Docker Compose 部署

需要 Docker Engine 与 Docker Compose 插件。预构建镜像包含前端与后端，支持 `linux/amd64` 和 `linux/arm64`，不需要宿主机安装 Node.js、npm 或 Python。应用使用单个 Uvicorn worker，后台续期提醒与 Web 同时启动。

## 一键部署

Linux 服务器准备好 curl 后，使用 root 或有 sudo 权限的用户执行：

```bash
bash -o pipefail -c 'curl -fsSL https://raw.githubusercontent.com/rest-rain/simkeep/main/install.sh | bash'
```

首次运行会询问宿主机端口和 HTTP 访问地址。远程部署时填写例如 `http://服务器IP:5180` 的地址；本机试用可直接回车。默认部署目录为当前目录下的 `simkeep`，镜像为 `ghcr.io/rest-rain/simkeep:latest`。

Docker Engine 缺失时，脚本从 `https://get.docker.com` 下载官方安装脚本并执行；只有 Compose 缺失时，从 Docker 官方 GitHub 发布页下载插件，校验 SHA256 后安装。Docker 服务未启动时，使用 systemd 或 service 启动；已有可用环境直接复用。

自动安装支持 Docker 官方仍支持的 Ubuntu、Debian、CentOS Stream、Rocky Linux、RHEL 和 Fedora，支持 `amd64` / `arm64`。安装组件、启动服务或访问受限的 Docker socket 时，需要 root 或 sudo 权限。非 root 用户按提示完成 sudo 验证后，脚本会通过 sudo 调用需要权限的命令。

脚本下载缺少的配置文件，创建权限为 `600` 的 `.env`，验证 Compose 配置、拉取镜像并等待健康检查。成功后显示配置目录和访问提示；登录网页后，每个人在“通知设置”配置自己的 Telegram / SMTP。

再次从同一目录执行相同命令，会使用已有配置更新镜像与容器。已有 `.env` 和 `docker-compose.yml` 保留，数据继续使用原命名卷。需要修改地址、端口或固定镜像版本时，编辑部署目录中的 `.env` 再运行。

也可指定部署目录及首次配置，供无人值守部署使用：

```bash
bash -o pipefail -c 'curl -fsSL https://raw.githubusercontent.com/rest-rain/simkeep/main/install.sh | bash -s -- --dir ./simkeep --port 5180 --url http://your-server:5180 --non-interactive'
```

`--port`、`--url` 仅用于首次创建 `.env`；已有配置时按文件内容部署。重复执行时使用同一个 `--dir`。无人值守安装需要 root 或免密码 sudo。没有交互终端且未提供参数时，默认使用端口 `5180` 和 `http://localhost:5180`；远程部署请填写实际地址。

## 在新服务器部署

手动部署需先安装 Docker Engine 和 Compose 插件。应用只需要 `docker-compose.yml` 和 `.env`，可下载配置文件及空白模板：

```bash
mkdir -p simkeep
cd simkeep
curl -fsSLO https://raw.githubusercontent.com/rest-rain/simkeep/main/docker-compose.yml
curl -fsSLO https://raw.githubusercontent.com/rest-rain/simkeep/main/.env.example
test -f .env || cp .env.example .env
chmod 600 .env
```

编辑 `.env`，将 `SIMKEEP_PUBLIC_URL` 改为实际访问地址，例如 `http://服务器IP:5180`。`SIMKEEP_PORT` 控制宿主机端口，默认 5180；改端口时同步修改公网地址。保持 HTTP 时使用 `SIMKEEP_SECURE_COOKIES=0`。每个用户登录网页的“通知设置”，点击“配置 Telegram / 配置邮件”保存自己的凭据；不需要修改 `.env` 或重启。`.env` 中的通知凭据仅作为可选公共默认服务。

默认使用 GitHub Actions 自动构建的镜像，`.env.example` 已包含：

```dotenv
SIMKEEP_IMAGE=ghcr.io/rest-rain/simkeep:latest
```

```bash
docker compose pull web
docker compose up -d --wait web
docker compose ps
```

访问 `http://服务器IP:5180/`，首次使用创建自己的账号。服务器防火墙需要允许选定的 TCP 端口。

Docker Compose 会自动发现 `docker-compose.yml`。也可在命令中加 `-f docker-compose.yml` 指定配置文件。

默认 Compose 项目名为 `simkeep`，持久化卷为 `simkeep_simkeep-data`，数据库位于容器 `/app/data/simkeep.db`。保持项目名即可复用同一个卷。容器重启、镜像更新及普通 `docker compose down` 都会保留卷；`docker compose down -v` 会删除数据卷。

### 从源码构建

需要完整仓库。在 `.env` 中设置 `SIMKEEP_IMAGE=simkeep:local`，然后执行：

```bash
docker build -t simkeep:local .
docker compose up -d --wait web
```

构建时自动打包前端，宿主机同样无需安装应用依赖。Compose 使用已经构建的本地镜像。

## GitHub 自动构建镜像

工作流位于 [docker-image.yml](../.github/workflows/docker-image.yml)，镜像发布到 `ghcr.io/rest-rain/simkeep`，同时构建 `amd64` 与 `arm64`。发布使用 GitHub 自动提供的 `GITHUB_TOKEN`，无需配置 Docker Hub 账号或额外的访问令牌。

| 触发方式 | 发布标签 |
| --- | --- |
| 推送 `main` | `latest`、`main`、`sha-提交短编号` |
| 推送版本标签，例如 `v1.2.3` | `1.2.3`、`1.2`、`sha-提交短编号` |
| 推送预发布标签，例如 `v1.2.3-rc.1` | `1.2.3-rc.1`、`sha-提交短编号` |
| 在 Actions 中手动运行 | 所选分支或版本对应的标签 |
| 向 `main` 提交 Pull Request | 仅验证构建，不发布 |

`latest` 只随 `main` 更新。使用正式版本标签部署时，例如设置 `SIMKEEP_IMAGE=ghcr.io/rest-rain/simkeep:1.2.3`，可避免跟随开发分支更新。

在仓库的 **Actions → Docker image** 查看构建结果，或点击 **Run workflow** 手动运行。仓库需启用 GitHub Actions；工作流已经声明 `contents: read` 和 `packages: write` 权限。

拉取提示 `denied` 时，先确认工作流已成功及包的可见性。新建 GHCR 包可能为 Private，公开源码仓库也不保证包可匿名拉取。维护者可打开 [SIMKEEP 的包设置](https://github.com/users/rest-rain/packages/container/simkeep/settings)，在 **Change visibility** 中改为 **Public**。构建成功前包设置页面可能尚不存在。

构建只读取 `.dockerignore` 允许的应用文件，不传入服务器 `.env`、数据库或通知密钥。镜像内附带 MIT LICENSE。

## 更新、配置与日志

使用预构建镜像时：

```bash
docker compose pull web
docker compose up -d --wait web
```

已有部署更新配置文件后，检查 `.env`：如果曾设置 `SIMKEEP_IMAGE=simkeep:local`，将其改为 `ghcr.io/rest-rain/simkeep:latest`，再执行上述命令。保留原 `.env` 中的访问地址和其他配置。旧目录中若仍有 `compose.yml`，先将其改名备份；否则 Compose 会优先读取旧文件。

使用源码镜像时，更新代码后执行 `docker build -t simkeep:local .`，再执行 `docker compose up -d --wait web`。更新镜像会重建容器，数据仍保存在原命名卷中。

修改 `.env` 后重建容器加载新配置：

```bash
docker compose up -d --force-recreate --wait web
```

仅执行 `docker compose restart` 不会加载修改后的环境配置。日常查看或重启：

```bash
docker compose logs --tail=100 web
docker compose restart web
docker compose ps
```

容器设置 `unless-stopped` 自动重启，Docker 服务需要随服务器启动。镜像以 UID / GID 10001 运行，根文件系统只读，数据卷和临时目录可写。健康检查访问 `/api/health`，日志最多保留三份，每份 10 MB。`.env`、数据库、备份与测试文件均不进入镜像或公开静态目录。

## 备份

使用 SQLite backup API 获取一致的数据库备份：

```bash
docker compose exec web python scripts/backup.py
docker compose cp web:/app/data/backups ./docker-backups
```

备份保存在卷中的 `/app/data/backups/`，第二条命令复制到宿主机。复制出的备份包含账号、卡片、余额、历史、渠道设置以及用户在网页保存的 Bot Token / SMTP 密码，应存放在受保护的位置。迁移到另一台服务器时同时保留 `.env`，其中的可选公共服务密钥不在数据库备份中。个人配置会随数据卷或数据库备份一起恢复；旧版备份没有配置表时，应用启动自动补建。

## 恢复或导入已有 SQLite

先创建当前库备份，再停止应用。将选定的一致备份命名为当前项目目录下的 `restore.db`。不要直接复制运行中的主数据库而遗漏 WAL。

```bash
docker compose stop web
docker compose run --rm --no-deps -T --entrypoint python web scripts/restore.py --replace < restore.db
docker compose up -d --wait web
```

恢复容器以应用用户读取标准输入，不需要 root 或修改宿主机备份权限。它检查数据库完整性与 SIMKEEP 表结构，临时生成恢复库后替换；未传 --replace 时会拒绝覆盖现有库。恢复容器只执行数据库操作，不启动提醒进程。使用 `docker compose -p 其他项目名` 时，以上所有命令也须带相同项目名。

## 从其他运行方式迁移

先用 SQLite backup API 创建一致性备份，保留原运行配置，然后停止旧进程。使用上面的“恢复或导入已有 SQLite”步骤导入 Docker 命名卷，再启动 web 容器。确认数据与通知设置后停用旧服务的自动启动；Docker 启动后的新数据以容器数据卷为准。

同一份 Telegram Bot 配置只运行一个提醒进程。不要同时运行旧服务和 Docker 容器，以免重复消费 Telegram 更新或重复安排提醒。
