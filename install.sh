#!/usr/bin/env bash
set -Eeuo pipefail

DOWNLOAD_BASE='https://raw.githubusercontent.com/rest-rain/simkeep/main'
staging=''
docker_staging=''
root_command=()
docker_command=(docker)
root_ready=0

fail() {
  printf '错误：%s\n' "$*" >&2
  exit 1
}

cleanup() {
  local directory
  for directory in "$staging" "$docker_staging"; do
    if [[ -n "$directory" ]]; then
      rm -rf -- "$directory"
    fi
  done
}

usage() {
  cat <<'USAGE'
用法：bash install.sh [选项]

  --dir 目录            部署目录，默认当前目录下的 simkeep
  --port 端口           首次部署的端口，默认 5180
  --url HTTP地址        首次部署的访问地址，默认 http://localhost:端口
  --non-interactive     使用参数或默认值，不询问配置
  --help                显示帮助

需要 curl；Linux 上缺少 Docker / Compose 时会自动安装，需要 root 或 sudo 权限。
已有 .env 和 docker-compose.yml 会保留；端口、地址参数仅用于首次部署。
再次执行会按已有配置拉取镜像并更新容器，数据保存在原命名卷中。
USAGE
}

normalize_port() {
  [[ "$1" =~ ^[0-9]{1,5}$ ]] || fail '端口必须是 1 到 65535 的整数。'
  local value
  value=$((10#$1))
  ((value >= 1 && value <= 65535)) || fail '端口必须是 1 到 65535 的整数。'
  printf '%s' "$value"
}

validate_url() {
  local pattern='^http://(\[[0-9A-Fa-f:]+\]|[A-Za-z0-9][A-Za-z0-9._-]*)(:([0-9]{1,5}))?/?$'
  [[ "$1" =~ $pattern ]] || fail '访问地址请使用 http://服务器IP:端口 或 http://域名:端口。'
  if [[ -n "${BASH_REMATCH[3]}" ]]; then
    normalize_port "${BASH_REMATCH[3]}" >/dev/null
  fi
}

prompt() {
  local answer
  printf '%s [%s]：' "$1" "$2" >&3
  IFS= read -r answer <&3 || fail '未能读取配置，请使用 --non-interactive 和相应参数。'
  printf '%s' "${answer:-$2}"
}

download() {
  curl -fsSL --connect-timeout 15 --max-time 60 --retry 2 \
    -o "$staging/$1" "$DOWNLOAD_BASE/$1" || fail "下载 $1 失败，请检查 GitHub 网络后重试。"
  [[ -s "$staging/$1" ]] || fail "下载的 $1 为空，请重试。"
}

require_root() {
  if ((root_ready)); then
    return
  fi
  if [[ "$(id -u)" != '0' ]]; then
    command -v sudo >/dev/null 2>&1 || fail '自动安装或启动 Docker 需要 root 权限，请使用 root 或 sudo 运行。'
    if (($1)); then
      sudo -v || fail '无法取得 root 权限，请使用 root 或可用的 sudo 运行。'
      root_command=(sudo)
    else
      sudo -n true || fail '无人值守安装需要 root 或免密码 sudo 权限。'
      root_command=(sudo -n)
    fi
  fi
  root_ready=1
}

require_linux() {
  [[ "$(uname -s)" == 'Linux' ]] || fail '自动安装 Docker / Compose 仅支持 Linux；其他系统请先安装 Docker Desktop。'
  case "$(uname -m)" in
    x86_64|amd64|aarch64|arm64) ;;
    *) fail '自动安装目前支持 amd64 / arm64。' ;;
  esac
}

prepare_docker_downloads() {
  if [[ -z "$docker_staging" ]]; then
    docker_staging=$(
      umask 077
      mktemp -d "${TMPDIR:-/tmp}/simkeep-docker.XXXXXX"
    )
    trap cleanup EXIT
  fi
}

install_engine() {
  local distro
  require_linux
  [[ -r /etc/os-release ]] || fail '无法识别 Linux 发行版，请手动安装 Docker。'
  distro=$(awk -F= '$1 == "ID" { gsub(/"/, "", $2); print $2 }' /etc/os-release)
  case "$distro" in
    ubuntu|debian|centos|rocky|rhel|fedora) ;;
    *) fail "当前发行版 ${distro:-未知} 不支持自动安装，请手动安装 Docker 后重试。" ;;
  esac
  require_root "$1"
  prepare_docker_downloads
  printf '未检测到 Docker，正在使用 Docker 官方脚本安装。\n'
  curl -fsSL --connect-timeout 15 --max-time 60 --retry 2 \
    -o "$docker_staging/docker-install.sh" https://get.docker.com || fail 'Docker 官方安装脚本下载失败，请检查网络。'
  [[ -s "$docker_staging/docker-install.sh" ]] || fail 'Docker 官方安装脚本为空。'
  "${root_command[@]}" sh "$docker_staging/docker-install.sh" || fail 'Docker 自动安装失败，请检查安装输出后重试。'
  hash -r
  command -v docker >/dev/null 2>&1 || fail '安装完成后仍找不到 Docker 命令。'
}

install_compose() {
  local architecture filename expected actual directory='/usr/local/lib/docker/cli-plugins'
  require_linux
  command -v sha256sum >/dev/null 2>&1 || fail '安装 Compose 需要 sha256sum，请先安装 coreutils。'
  require_root "$1"
  prepare_docker_downloads
  case "$(uname -m)" in
    x86_64|amd64) architecture=x86_64 ;;
    aarch64|arm64) architecture=aarch64 ;;
  esac
  filename="docker-compose-linux-$architecture"
  printf '未检测到可用的 Compose 插件，正在下载官方版本。\n'
  curl -fsSL --connect-timeout 15 --max-time 180 --retry 2 \
    -o "$docker_staging/$filename" "https://github.com/docker/compose/releases/latest/download/$filename" || fail 'Compose 下载失败。'
  curl -fsSL --connect-timeout 15 --max-time 60 --retry 2 \
    -o "$docker_staging/$filename.sha256" "https://github.com/docker/compose/releases/latest/download/$filename.sha256" || fail 'Compose 校验文件下载失败。'
  expected=$(awk 'NR == 1 { print $1 }' "$docker_staging/$filename.sha256")
  actual=$(sha256sum "$docker_staging/$filename")
  actual=${actual%% *}
  [[ "$expected" =~ ^[[:xdigit:]]{64}$ && "$actual" == "$expected" ]] || fail 'Compose 文件校验失败，已停止安装，请重试。'
  "${root_command[@]}" install -d -m 0755 "$directory"
  "${root_command[@]}" install -m 0755 "$docker_staging/$filename" "$directory/docker-compose"
}

ensure_docker() {
  local context _attempt
  if ! command -v docker >/dev/null 2>&1; then
    [[ -z "${DOCKER_HOST:-}" && -z "${DOCKER_CONTEXT:-}" ]] || fail '已设置 DOCKER_HOST / DOCKER_CONTEXT，请先安装并配置所选 Docker 客户端。'
    install_engine "$1"
  fi
  if ! docker info >/dev/null 2>&1; then
    [[ -z "${DOCKER_HOST:-}" ]] || fail '无法连接 DOCKER_HOST 指定的 Docker，请检查连接配置。'
    context=$(docker context show 2>/dev/null) || fail '无法读取 Docker context，请检查 Docker 客户端。'
    [[ "$context" == 'default' ]] || fail "无法连接 Docker context $context，请先启动或修复该环境。"
    require_linux
    require_root "$1"
    docker_command=("${root_command[@]}" docker)
    if ! "${docker_command[@]}" info >/dev/null 2>&1; then
      printf '正在启动 Docker 服务。\n'
      if command -v systemctl >/dev/null 2>&1 && "${root_command[@]}" systemctl enable --now docker; then
        :
      elif command -v service >/dev/null 2>&1 && "${root_command[@]}" service docker start; then
        :
      else
        fail '无法启动 Docker 服务，请检查 Docker 安装与系统服务管理器。'
      fi
      for _attempt in {1..20}; do
        if "${docker_command[@]}" info >/dev/null 2>&1; then
          break
        fi
        sleep 1
      done
      "${docker_command[@]}" info >/dev/null 2>&1 || fail 'Docker 服务未就绪，请检查 Docker 服务日志。'
    fi
  fi
  if ! "${docker_command[@]}" compose version >/dev/null 2>&1; then
    install_compose "$1"
    "${docker_command[@]}" compose version >/dev/null 2>&1 || fail 'Compose 安装后仍不可用，请检查 Docker 客户端或已有插件。'
  fi
}

main() {
  local install_dir="$PWD/simkeep" port='' public_url='' interactive=1 has_terminal=0
  local new_env=1 new_compose=1
  while (($#)); do
    case "$1" in
      --dir|--port|--url)
        [[ $# -ge 2 && -n "$2" ]] || fail "$1 缺少参数。"
        case "$1" in
          --dir) install_dir=$2 ;;
          --port) port=$2 ;;
          --url) public_url=$2 ;;
        esac
        shift 2
        ;;
      --non-interactive) interactive=0; shift ;;
      --help|-h) usage; return ;;
      *) fail "未知选项：$1。使用 --help 查看帮助。" ;;
    esac
  done

  if [[ -n "$port" ]]; then
    port=$(normalize_port "$port")
  fi
  if [[ -n "$public_url" ]]; then
    validate_url "$public_url"
    public_url=${public_url%/}
  fi
  for dependency in curl awk; do
    command -v "$dependency" >/dev/null 2>&1 || fail "缺少 $dependency，请先安装。"
  done

  [[ ! -e "$install_dir" || -d "$install_dir" ]] || fail '部署目录已经存在，但不是文件夹。'
  for configuration in .env docker-compose.yml; do
    if [[ -e "$install_dir/$configuration" || -L "$install_dir/$configuration" ]]; then
      [[ -f "$install_dir/$configuration" ]] || fail "$configuration 已经存在，但不是可用文件。"
    fi
  done
  [[ ! -f "$install_dir/.env" ]] || new_env=0
  [[ ! -f "$install_dir/docker-compose.yml" ]] || new_compose=0

  if ((new_env)); then
    if ((interactive)) && { exec 3<>/dev/tty; } 2>/dev/null; then
      has_terminal=1
    fi
    if [[ -z "$port" ]]; then
      if ((has_terminal)); then
        port=$(prompt '宿主机端口' '5180')
      else
        port=5180
      fi
      port=$(normalize_port "$port")
    fi
    if [[ -z "$public_url" ]]; then
      if ((has_terminal)); then
        public_url=$(prompt 'HTTP 访问地址（远程部署时填写服务器 IP 或域名）' "http://localhost:$port")
      else
        public_url="http://localhost:$port"
      fi
      validate_url "$public_url"
      public_url=${public_url%/}
    fi
  else
    printf '保留已有 .env，按其中的配置部署；如需调整端口或地址，请编辑该文件。\n'
  fi

  ensure_docker "$interactive"
  umask 077
  mkdir -p -- "$install_dir"
  install_dir=$(cd -- "$install_dir" && pwd -P)
  staging=$(mktemp -d "$install_dir/.simkeep-install.XXXXXX")
  trap cleanup EXIT
  if ((new_compose)); then
    download docker-compose.yml
  fi
  if ((new_env)); then
    download .env.example
    awk -v port="$port" -v url="$public_url" '
      /^SIMKEEP_PORT=/ { print "SIMKEEP_PORT=" port; next }
      /^SIMKEEP_PUBLIC_URL=/ { print "SIMKEEP_PUBLIC_URL=" url; next }
      { print }
    ' "$staging/.env.example" > "$staging/.env"
  fi
  if ((new_compose)); then
    mv -- "$staging/docker-compose.yml" "$install_dir/docker-compose.yml"
  fi
  if ((new_env)); then
    if [[ ! -e "$install_dir/.env.example" && ! -L "$install_dir/.env.example" ]]; then
      mv -- "$staging/.env.example" "$install_dir/.env.example"
    fi
    mv -- "$staging/.env" "$install_dir/.env"
  fi
  chmod 600 -- "$install_dir/.env"

  local compose=("${docker_command[@]}" compose --project-directory "$install_dir" --env-file "$install_dir/.env" -f "$install_dir/docker-compose.yml")
  "${compose[@]}" config --quiet || fail 'Compose 配置验证失败，请检查部署目录中的配置文件。'
  "${compose[@]}" pull web || fail '镜像拉取失败，请检查网络和 .env 中的 SIMKEEP_IMAGE 后重试。'
  "${compose[@]}" up -d --wait --wait-timeout 120 web || fail '容器未通过健康检查，请在部署目录执行 docker compose logs --tail=100 web。'

  printf '\n部署完成。\n配置目录：%s\n' "$install_dir"
  if ((new_env)); then
    printf '访问地址：%s\n' "$public_url"
  else
    printf '访问地址以 .env 中的 SIMKEEP_PUBLIC_URL 为准。\n'
  fi
  printf '首次使用请在网页创建账号，再到通知设置配置 Telegram / 邮件。\n'
}

main "$@"
