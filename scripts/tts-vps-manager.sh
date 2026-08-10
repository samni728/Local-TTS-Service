#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_VERSION="1.0.0"
COMMAND="update"
REPO_DIR=""
BACKUP_ROOT=""
RESTORE_TARGET="latest"
REMOTE_NAME="${UPDATE_REMOTE:-origin}"
UPDATE_BRANCH="${UPDATE_BRANCH:-}"
HEALTH_TIMEOUT="${TTS_HEALTH_TIMEOUT:-120}"
ROLLBACK_ACTIVE=0
PREVIOUS_COMMIT=""
UPDATE_BACKUP=""
LOCK_DIR=""
COMPOSE=()

log() {
    printf '[LocalTTS] %s\n' "$*" >&2
}

die() {
    log "错误：$*"
    exit 1
}

usage() {
    cat <<'EOF'
LocalTTS VPS 备份、更新与恢复工具

用法：
  tts-vps-manager.sh update  [--repo PATH] [--backup-dir PATH]
  tts-vps-manager.sh backup  [--repo PATH] [--backup-dir PATH]
  tts-vps-manager.sh list    [--repo PATH] [--backup-dir PATH]
  tts-vps-manager.sh restore [latest|BACKUP_PATH] [--repo PATH] [--backup-dir PATH]
  tts-vps-manager.sh status  [--repo PATH]

选项：
  --repo PATH        Local-TTS-Service 仓库路径
  --backup-dir PATH  仓库外的备份目录
  --branch NAME      更新分支，默认使用当前分支
  --remote NAME      Git 远程名，默认 origin
  --timeout SECONDS  容器健康检查超时，默认 120 秒
  -h, --help         显示帮助
  --version          显示版本

默认 update 流程：预检查、备份、拉取、恢复私有配置、补齐 .env 新变量、
重建容器并等待健康状态。任何步骤失败都会自动回滚到更新前版本。
EOF
}

parse_arguments() {
    local command_seen=0
    while (($#)); do
        case "$1" in
            update|backup|list|restore|status)
                ((command_seen == 0)) || die "只能指定一个命令"
                COMMAND="$1"
                command_seen=1
                ;;
            --repo)
                shift
                (($#)) || die "--repo 缺少路径"
                REPO_DIR="$1"
                ;;
            --backup-dir)
                shift
                (($#)) || die "--backup-dir 缺少路径"
                BACKUP_ROOT="$1"
                ;;
            --branch)
                shift
                (($#)) || die "--branch 缺少名称"
                UPDATE_BRANCH="$1"
                ;;
            --remote)
                shift
                (($#)) || die "--remote 缺少名称"
                REMOTE_NAME="$1"
                ;;
            --timeout)
                shift
                (($#)) || die "--timeout 缺少秒数"
                HEALTH_TIMEOUT="$1"
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            --version)
                printf '%s\n' "$SCRIPT_VERSION"
                exit 0
                ;;
            *)
                if [[ "$COMMAND" == "restore" && "$RESTORE_TARGET" == "latest" ]]; then
                    RESTORE_TARGET="$1"
                else
                    die "未知参数：$1"
                fi
                ;;
        esac
        shift
    done
}

resolve_repo_dir() {
    local script_dir
    script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"

    if [[ -z "$REPO_DIR" ]]; then
        if git -C "$PWD" rev-parse --show-toplevel >/dev/null 2>&1; then
            REPO_DIR="$(git -C "$PWD" rev-parse --show-toplevel)"
        elif git -C "$script_dir/.." rev-parse --show-toplevel >/dev/null 2>&1; then
            REPO_DIR="$(git -C "$script_dir/.." rev-parse --show-toplevel)"
        else
            die "无法定位项目，请使用 --repo /path/to/Local-TTS-Service"
        fi
    fi

    [[ -d "$REPO_DIR" ]] || die "项目目录不存在：$REPO_DIR"
    REPO_DIR="$(cd -- "$REPO_DIR" && pwd -P)"
    git -C "$REPO_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
        || die "不是 Git 仓库：$REPO_DIR"
    [[ -f "$REPO_DIR/docker-compose.yml" ]] \
        || die "未找到 docker-compose.yml：$REPO_DIR"

    if [[ -z "$BACKUP_ROOT" ]]; then
        BACKUP_ROOT="$(dirname -- "$REPO_DIR")/$(basename -- "$REPO_DIR")-backups"
    fi
    mkdir -p -- "$BACKUP_ROOT"
    BACKUP_ROOT="$(cd -- "$BACKUP_ROOT" && pwd -P)"
    case "$BACKUP_ROOT/" in
        "$REPO_DIR/"*) die "备份目录必须位于 Git 仓库之外：$BACKUP_ROOT" ;;
    esac
    chmod 700 "$BACKUP_ROOT" 2>/dev/null || true
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "缺少命令：$1"
}

detect_compose() {
    require_command docker
    if docker compose version >/dev/null 2>&1; then
        COMPOSE=(docker compose)
    elif command -v docker-compose >/dev/null 2>&1; then
        COMPOSE=(docker-compose)
    else
        die "未安装 docker compose 或 docker-compose"
    fi
}

compose() {
    (cd -- "$REPO_DIR" && "${COMPOSE[@]}" "$@")
}

acquire_lock() {
    LOCK_DIR="$BACKUP_ROOT/.operation-lock"
    if ! mkdir -- "$LOCK_DIR" 2>/dev/null; then
        die "另一个更新或恢复任务正在运行：$LOCK_DIR"
    fi
}

release_lock() {
    if [[ -n "$LOCK_DIR" && -d "$LOCK_DIR" ]]; then
        rmdir -- "$LOCK_DIR" 2>/dev/null || true
    fi
}

assert_safe_worktree() {
    local unexpected
    unexpected="$(
        git -C "$REPO_DIR" status --porcelain --untracked-files=no \
            | awk 'substr($0,4) != "config.json" { print }'
    )"
    if [[ -n "$unexpected" ]]; then
        log "检测到 config.json 以外的未提交修改："
        printf '%s\n' "$unexpected" >&2
        die "为避免覆盖代码，请先提交、暂存或处理这些修改"
    fi
}

create_backup() {
    local label="${1:-manual}"
    local timestamp backup_path commit branch
    timestamp="$(date '+%Y%m%d-%H%M%S')"
    backup_path="$BACKUP_ROOT/${timestamp}-${label}-$$"
    commit="$(git -C "$REPO_DIR" rev-parse HEAD)"
    branch="$(git -C "$REPO_DIR" branch --show-current)"

    umask 077
    mkdir -p -- "$backup_path/tts_data" "$backup_path/certs"
    [[ -f "$REPO_DIR/config.json" ]] && cp -p -- "$REPO_DIR/config.json" "$backup_path/config.json"
    [[ -f "$REPO_DIR/.env" ]] && cp -p -- "$REPO_DIR/.env" "$backup_path/.env"
    if [[ -f "$REPO_DIR/tts_data/.flask_secret_key" ]]; then
        cp -p -- "$REPO_DIR/tts_data/.flask_secret_key" "$backup_path/tts_data/.flask_secret_key"
    fi
    if [[ -d "$REPO_DIR/certs" ]]; then
        cp -a -- "$REPO_DIR/certs/." "$backup_path/certs/"
    fi
    cat >"$backup_path/manifest" <<EOF
commit=$commit
branch=$branch
created_at=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
label=$label
EOF
    chmod -R go-rwx "$backup_path" 2>/dev/null || true
    log "备份完成：$backup_path"
    printf '%s\n' "$backup_path"
}

restore_private_files() {
    local backup_path="$1"
    [[ -d "$backup_path" ]] || die "备份不存在：$backup_path"

    [[ -f "$backup_path/config.json" ]] && cp -p -- "$backup_path/config.json" "$REPO_DIR/config.json"
    [[ -f "$backup_path/.env" ]] && cp -p -- "$backup_path/.env" "$REPO_DIR/.env"
    if [[ -f "$backup_path/tts_data/.flask_secret_key" ]]; then
        mkdir -p -- "$REPO_DIR/tts_data"
        cp -p -- "$backup_path/tts_data/.flask_secret_key" "$REPO_DIR/tts_data/.flask_secret_key"
    fi
    if [[ -d "$backup_path/certs" ]]; then
        mkdir -p -- "$REPO_DIR/certs"
        cp -a -- "$backup_path/certs/." "$REPO_DIR/certs/"
    fi
}

merge_missing_env_keys() {
    local example_file="$REPO_DIR/.env.example"
    local env_file="$REPO_DIR/.env"
    local line key added=0
    [[ -f "$example_file" ]] || return 0
    [[ -f "$env_file" ]] || : >"$env_file"
    chmod 600 "$env_file" 2>/dev/null || true

    while IFS= read -r line || [[ -n "$line" ]]; do
        [[ "$line" =~ ^[A-Z][A-Z0-9_]*= ]] || continue
        key="${line%%=*}"
        if ! grep -q "^${key}=" "$env_file"; then
            printf '\n%s\n' "$line" >>"$env_file"
            log "已向 .env 补充新增变量：$key"
            added=$((added + 1))
        fi
    done <"$example_file"
    log ".env 检查完成，新增 $added 个变量；原有值未被覆盖"
}

wait_for_service() {
    local deadline container_id state health
    deadline=$((SECONDS + HEALTH_TIMEOUT))
    while ((SECONDS < deadline)); do
        container_id="$(compose ps -q tts-service 2>/dev/null || true)"
        if [[ -n "$container_id" ]]; then
            state="$(docker inspect --format '{{.State.Status}}' "$container_id" 2>/dev/null || true)"
            health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id" 2>/dev/null || true)"
            if [[ "$state" == "running" && ("$health" == "healthy" || "$health" == "none") ]]; then
                log "服务状态正常：state=$state health=$health"
                return 0
            fi
            if [[ "$state" == "exited" || "$state" == "dead" || "$health" == "unhealthy" ]]; then
                log "服务启动失败：state=$state health=$health"
                compose logs --tail=100 tts-service >&2 || true
                return 1
            fi
        fi
        sleep 3
    done
    log "等待健康状态超时（${HEALTH_TIMEOUT} 秒）"
    compose logs --tail=100 tts-service >&2 || true
    return 1
}

rollback_update() {
    local failed_status="$1"
    trap - ERR
    ROLLBACK_ACTIVE=0
    log "更新失败（状态码 ${failed_status}），开始自动回滚……"
    git -C "$REPO_DIR" reset --hard "$PREVIOUS_COMMIT" >&2
    restore_private_files "$UPDATE_BACKUP"
    compose config --quiet
    compose up -d --build --remove-orphans
    if wait_for_service; then
        log "已恢复到更新前版本：$PREVIOUS_COMMIT"
    else
        log "自动回滚后的服务仍不健康，请运行："
        log "  cd '${REPO_DIR}' && ${COMPOSE[*]} logs --tail=200 tts-service"
    fi
}

on_error() {
    local status="$1" line="$2"
    trap - ERR
    if ((ROLLBACK_ACTIVE)); then
        log "第 $line 行发生错误，触发自动回滚"
        rollback_update "$status" || true
    fi
    exit "$status"
}

run_update() {
    local current_branch
    detect_compose
    assert_safe_worktree
    acquire_lock

    current_branch="$(git -C "$REPO_DIR" branch --show-current)"
    [[ -n "$current_branch" ]] || die "当前处于 detached HEAD，请先切换到部署分支"
    [[ -n "$UPDATE_BRANCH" ]] || UPDATE_BRANCH="$current_branch"
    git -C "$REPO_DIR" remote get-url "$REMOTE_NAME" >/dev/null 2>&1 \
        || die "Git 远程不存在：$REMOTE_NAME"

    PREVIOUS_COMMIT="$(git -C "$REPO_DIR" rev-parse HEAD)"
    UPDATE_BACKUP="$(create_backup pre-update)"
    ROLLBACK_ACTIVE=1

    log "获取 ${REMOTE_NAME}/${UPDATE_BRANCH}……"
    git -C "$REPO_DIR" restore --staged --worktree -- config.json
    git -C "$REPO_DIR" fetch --prune "$REMOTE_NAME" "$UPDATE_BRANCH"
    git -C "$REPO_DIR" merge --ff-only "$REMOTE_NAME/$UPDATE_BRANCH"

    restore_private_files "$UPDATE_BACKUP"
    merge_missing_env_keys
    compose config --quiet
    compose up -d --build --remove-orphans
    wait_for_service

    ROLLBACK_ACTIVE=0
    log "更新成功：$PREVIOUS_COMMIT -> $(git -C "$REPO_DIR" rev-parse HEAD)"
    log "备份位置：$UPDATE_BACKUP"
}

find_latest_backup() {
    local latest="" candidate
    for candidate in "$BACKUP_ROOT"/*; do
        [[ -d "$candidate" && -f "$candidate/manifest" ]] || continue
        latest="$candidate"
    done
    [[ -n "$latest" ]] || die "没有可用备份：$BACKUP_ROOT"
    printf '%s\n' "$latest"
}

resolve_backup_target() {
    if [[ "$RESTORE_TARGET" == "latest" ]]; then
        find_latest_backup
    elif [[ -d "$RESTORE_TARGET" ]]; then
        (cd -- "$RESTORE_TARGET" && pwd -P)
    elif [[ -d "$BACKUP_ROOT/$RESTORE_TARGET" ]]; then
        (cd -- "$BACKUP_ROOT/$RESTORE_TARGET" && pwd -P)
    else
        die "找不到备份：$RESTORE_TARGET"
    fi
}

manifest_value() {
    local manifest="$1" key="$2"
    awk -F= -v wanted="$key" '$1 == wanted {sub(/^[^=]*=/, ""); print; exit}' "$manifest"
}

run_restore() {
    local backup_path commit rescue_backup
    detect_compose
    assert_safe_worktree
    acquire_lock
    backup_path="$(resolve_backup_target)"
    [[ -f "$backup_path/manifest" ]] || die "备份缺少 manifest：$backup_path"
    commit="$(manifest_value "$backup_path/manifest" commit)"
    [[ "$commit" =~ ^[0-9a-fA-F]{7,40}$ ]] || die "备份中的 Git commit 无效"

    rescue_backup="$(create_backup pre-restore)"
    log "恢复 Git 版本：$commit"
    git -C "$REPO_DIR" reset --hard "$commit"
    restore_private_files "$backup_path"
    compose config --quiet
    compose up -d --build --remove-orphans
    wait_for_service
    log "恢复成功：$backup_path"
    log "恢复前状态另存为：$rescue_backup"
}

run_backup() {
    assert_safe_worktree
    acquire_lock
    create_backup manual >/dev/null
}

run_list() {
    local found=0 candidate commit created label
    printf '%-42s %-12s %-20s %s\n' "BACKUP" "COMMIT" "CREATED" "LABEL"
    for candidate in "$BACKUP_ROOT"/*; do
        [[ -d "$candidate" && -f "$candidate/manifest" ]] || continue
        found=1
        commit="$(manifest_value "$candidate/manifest" commit)"
        created="$(manifest_value "$candidate/manifest" created_at)"
        label="$(manifest_value "$candidate/manifest" label)"
        printf '%-42s %-12s %-20s %s\n' "$(basename -- "$candidate")" "${commit:0:12}" "$created" "$label"
    done
    ((found)) || log "暂无备份：$BACKUP_ROOT"
}

run_status() {
    detect_compose
    log "仓库：$REPO_DIR"
    log "版本：$(git -C "$REPO_DIR" rev-parse --short HEAD)"
    log "分支：$(git -C "$REPO_DIR" branch --show-current)"
    log "备份：$BACKUP_ROOT"
    compose ps
}

main() {
    parse_arguments "$@"
    require_command git
    require_command awk
    require_command grep
    [[ "$HEALTH_TIMEOUT" =~ ^[1-9][0-9]*$ ]] || die "--timeout 必须是正整数"
    resolve_repo_dir
    trap release_lock EXIT
    trap 'on_error $? $LINENO' ERR

    case "$COMMAND" in
        update) run_update ;;
        backup) run_backup ;;
        list) run_list ;;
        restore) run_restore ;;
        status) run_status ;;
    esac
}

main "$@"
