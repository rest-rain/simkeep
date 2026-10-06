<p align="center">
  <img src="docs/images/cover.svg" width="100%" alt="SIMKEEP 续卡：记住每张卡的下一次续期">
</p>

# SIMKEEP · 续卡

**记住每张卡的下一次续期。**

SIMKEEP 是一个可自行部署的 SIM / eSIM 管理平台。把开通日期、平台注册关系、多币种余额、续期操作和通知放在同一个地方，让每个人管理自己的卡片。

名字来自 **SIM + Keep**：让需要保留的号码持续保持可用。

[界面预览](#界面预览) · [Docker 部署](#docker-部署) · [通知配置](#通知配置) · [备份与更新](#备份与更新)

## 功能

- **卡片档案**：记录 SIM / eSIM 类型、运营商、地区、号码、开通时间、套餐及备注，支持归档与恢复。
- **续期计划**：一张卡设置多条规则，支持重置、购买套餐、打电话、发短信、充值及自定义操作；周期按天或日历月计算。
- **下次日期自动计算**：记录完成时间后，按完成日顺延或固定周期更新下一次续期，保留操作历史。
- **多币种余额与费用**：支持 23 种币种，分别记录余额、预计费用与实际费用；完成操作时默认扣除同币种余额，也可只记录费用。充值可计入余额。
- **平台注册记录**：关联 Telegram、Google、WhatsApp、PayPal 等平台及账号标识，支持搜索和筛选。
- **Telegram / 邮件提醒**：每个账号在网页填写自己的 Bot Token 或 SMTP，设置时区、提醒时间、提前天数及逾期提醒，查看发送记录。
- **多人使用**：注册、登录和退出；卡片、费用、平台关系、通知设置及凭据按账号隔离。
- **桌面与手机**：卡片视图、列表、续期日历、移动端布局和 JSON 导出；界面不依赖外部 CDN。

金额使用十进制与整数最小单位计算，不进行汇率换算。续期操作由你实际执行，SIMKEEP 负责提醒、记录和计算。

## 界面预览

下图使用独立演示账号和虚构资料；号码、邮箱、余额及费用均为示例，运营商周期请以实际条款为准。

### 卡片总览

查看各币种余额、近期续期金额、卡片和日历。

![SIMKEEP 卡片总览](docs/images/overview.png)

### 卡片详情与续期历史

把卡片资料、关联平台、续期规则和实际费用放在一起。

![卡片详情与费用历史](docs/images/card-detail.png)

### 通知设置

在网页配置自己的通知服务，再绑定 Telegram 或验证接收邮箱。

![Telegram 与邮件通知设置](docs/images/notifications.png)

<details>
<summary>查看手机界面</summary>

<p align="center">
  <img src="docs/images/mobile.png" width="390" alt="SIMKEEP 手机卡片管理界面">
</p>

</details>

## Docker 部署

需要 Docker Engine 和 Docker Compose 插件。可直接使用 GHCR 镜像，支持 `amd64` / `arm64`，服务器无需安装 Node.js 或 Python。

### 一键部署

Linux 服务器准备好 curl 后，使用 root 或有 sudo 权限的用户执行：

```bash
bash -o pipefail -c 'curl -fsSL https://raw.githubusercontent.com/rest-rain/simkeep/main/install.sh | bash'
```

脚本会自动安装缺少的 Docker Engine / Compose 插件并启动 Docker 服务，已有可用环境则直接复用。支持 Docker 官方仍支持的 Ubuntu、Debian、CentOS Stream、Rocky Linux、RHEL 和 Fedora，架构为 `amd64` / `arm64`。

默认部署到当前目录下的 `simkeep` 文件夹，首次运行询问端口和 HTTP 访问地址，下载配置并启动镜像。打开显示的地址后创建账号。

再次从同一目录执行相同命令会保留已有 `.env`、`docker-compose.yml` 和数据卷，拉取镜像并更新容器。指定目录、无人值守部署等用法见 [一键部署说明](docs/DOCKER.md#一键部署)。

### 手动部署

将 [docker-compose.yml](docker-compose.yml) 和 [.env.example](.env.example) 下载到同一目录，进入该目录后执行：

```bash
test -f .env || cp .env.example .env
chmod 600 .env
```

编辑 `.env`，把 `SIMKEEP_PUBLIC_URL` 改成自己的访问地址，例如 `http://your-server:5180`。本机试用可保留 `http://localhost:5180`。

默认镜像为 `ghcr.io/rest-rain/simkeep:latest`，由 GitHub Actions 自动构建。`latest` 对应 `main` 的最新构建；需要固定版本时修改 `.env` 中的 `SIMKEEP_IMAGE`，使用已发布的版本标签。

```bash
docker compose pull web
docker compose up -d --wait web
docker compose ps
```

打开 `http://localhost:5180` 或设置的服务器地址，点击“创建账号”。没有预置管理员、初始密码或演示资料。

Docker Compose 会自动读取 `docker-compose.yml`。也可从源码构建，详见 [源码构建说明](docs/DOCKER.md#从源码构建)。

| 配置项 | 默认值 | 用途 |
| --- | --- | --- |
| `SIMKEEP_IMAGE` | `ghcr.io/rest-rain/simkeep:latest` | 自动构建镜像；可改为已发布的版本标签 |
| `SIMKEEP_PUBLIC_URL` | `http://localhost:5180` | 网页访问地址和提醒中的链接 |
| `SIMKEEP_PORT` | `5180` | 宿主机端口；修改时同步调整访问地址 |
| `SIMKEEP_BIND_ADDRESS` | `0.0.0.0` | 宿主机监听地址 |
| `SIMKEEP_SECURE_COOKIES` | `0` | HTTP 使用 `0`；通过 HTTPS 访问时使用 `1` |

数据保存于命名卷 `simkeep_simkeep-data` 中的 `/app/data/simkeep.db`。容器重启和镜像更新会保留数据。使用单个 Web worker 和一个提醒调度进程。

GitHub Actions 在推送 `main` 或 `v1.0.0` 这样的版本标签时自动构建并发布镜像，也支持手动触发。详见 [Docker 部署、自动构建与恢复说明](docs/DOCKER.md)。

## 通知配置

登录后进入 **通知设置**。每个渠道都有配置按钮，保存后立即生效，无需重启 Docker。

### Telegram

1. 在 [BotFather](https://t.me/BotFather) 创建 Bot，获取 Token。
2. 点击 **配置 Telegram**，填写 Token，然后 **保存并检查**。
3. 点击 **绑定 Telegram**，打开 Bot 并点击“开始”，回到网页检查绑定。
4. 开启 Telegram 提醒，选择提醒时间并 **保存设置**。

同一个 Bot Token 只用于一个账号，且需要由 SIMKEEP 独占 `getUpdates`。不要同时运行其他消费者或设置其他 webhook。更换 Token 后需要重新绑定。

### 邮件

1. 点击 **配置邮件**，填写 SMTP 服务器、端口、安全方式、发件邮箱、用户名和密码 / 授权码。
2. 点击 **保存并检查**。端口 `587` 通常使用 STARTTLS，`465` 通常使用 SSL / TLS；以邮件服务说明为准。
3. 保存接收邮箱，点击 **发送验证码**，填写邮件中的验证码。
4. 开启邮箱提醒，选择提醒时间并 **保存设置**。

支持无需登录认证的 SMTP，此时用户名留空。发件邮箱需是邮件服务允许使用的地址。

**保存并检查**只检查连接与认证，不发送消息。绑定或验证后可以点击 **发送测试** 检查真实投递。已保存的 Token / 密码不会回显，编辑时留空保留原值。

默认提前 7、3、1 天及到期当天提醒，也可开启每天一次的逾期提醒。提醒按各账号时区和时间运行，关闭网页后仍有效。

`.env` 中的通知凭据也可作为公共默认服务；个人配置优先。清除个人配置后，如果服务器配置了公共服务，会恢复使用公共服务。

## 备份与更新

使用 SQLite backup API 创建一致的备份：

```bash
docker compose exec -T web python scripts/backup.py
docker compose cp web:/app/data/backups ./docker-backups
```

备份包含账号、卡片、历史和个人通知密钥，应放在受保护的位置。不要只复制正在使用的主数据库文件而遗漏 WAL。

使用 GHCR 镜像时，拉取更新并重建容器：

```bash
docker compose pull web
docker compose up -d --wait web
```

如果旧 `.env` 设置了 `SIMKEEP_IMAGE=simkeep:local`，先改为 `ghcr.io/rest-rain/simkeep:latest`，再执行上述命令。使用源码镜像时，更新代码后先执行 `docker build -t simkeep:local .`，再执行 `docker compose up -d --wait web`。

修改 `.env` 后，需要重建容器加载新环境变量：

```bash
docker compose up -d --force-recreate --wait web
```

`docker compose restart` 不会加载修改后的 `.env`。不要执行 `docker compose down -v`，它会删除数据卷。

## 本地开发

后端使用 Python / FastAPI / SQLite，前端使用原生 JavaScript、HTML 和 CSS。

```bash
python3 -m pip install -r requirements.txt
npm run build
npm start
```

本地启动读取进程环境变量；`.env` 由 Docker Compose 加载，本地开发需要自行设置所需变量。

验证命令：

```bash
npm test
python3 -m unittest discover -s tests -p 'test_*.py' -q
node --check app.js
```

测试使用临时数据库和模拟投递边界，不需要真实 Telegram / SMTP 凭据。

## 使用范围

适合小规模单实例部署。当前包含卡片维护与提醒，不自动向运营商拨号、发短信或购买套餐，也不包含共享卡片、密码找回和管理员面板。

提醒失败会退避重试，最多尝试 5 次；修复凭据后当天未发送的失败任务可重新排队。外部服务已经接收消息、进程尚未写入成功记录时崩溃，恢复后可能重复一次；停机期间错过的历史提醒不会逐条补发。
