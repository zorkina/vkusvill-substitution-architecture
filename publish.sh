#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
project_root="$PWD"
repo_name=vkusvill-substitution-architecture
expected_owner="${GITHUB_OWNER:-zorkina}"

for tool in git gh python3; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        printf 'Не найден %s. Публикация не выполнена.\n' "$tool" >&2
        exit 1
    fi
done
python3 scripts/check.py

if ! current_owner="$(gh api user --jq .login)"; then
    printf 'GitHub не авторизован. Команда входа: gh auth login\n' >&2
    exit 1
fi
if [ "$current_owner" != "$expected_owner" ]; then
    printf 'Активный аккаунт: %s. Ожидается: %s. Публикация остановлена.\n' "$current_owner" "$expected_owner" >&2
    printf 'Переключение аккаунта: gh auth switch --user %s\n' "$expected_owner" >&2
    exit 1
fi
repo="$expected_owner/$repo_name"
printf 'Аккаунт: %s\nПубличный репозиторий: https://github.com/%s\n' "$current_owner" "$repo"

if [ ! -d .git ]; then
    if gh repo view "$repo" --json name >/dev/null 2>&1; then
        printf 'Репозиторий уже существует. Новый архив не заменяет его историю автоматически.\n' >&2
        exit 1
    fi
    git init -b main
fi
actual_root="$(git rev-parse --show-toplevel)"
if [ "$actual_root" != "$project_root" ]; then
    printf 'Git-каталог не совпадает с папкой проекта. Публикация остановлена.\n' >&2
    exit 1
fi
if [ "$(git branch --show-current)" != main ]; then
    printf 'Ожидалась ветка main. Текущая ветка оставлена без изменений.\n' >&2
    exit 1
fi
if git remote get-url origin >/dev/null 2>&1; then
    remote_url="$(git remote get-url origin)"
    case "$remote_url" in
        "https://github.com/$repo.git"|"https://github.com/$repo"|"git@github.com:$repo.git") ;;
        *) printf 'origin указывает на другой репозиторий. Публикация остановлена.\n' >&2; exit 1 ;;
    esac
fi
if ! git config user.name >/dev/null; then
    git config --local user.name "$current_owner"
fi
if ! git config user.email >/dev/null; then
    account_id="$(gh api user --jq .id)"
    git config --local user.email "$account_id+$current_owner@users.noreply.github.com"
fi

git add -- README.md .gitignore Makefile diagrams scripts publish.sh
if ! git diff --cached --quiet; then
    git commit -m 'Архитектура подбора замены товара'
fi
if git remote get-url origin >/dev/null 2>&1; then
    git push --set-upstream origin main
else
    gh repo create "$repo" --public --source . --remote origin --push \
        --description 'Подбор замены товара во ВкусВилл: BPMN и три уровня C4'
fi
visibility="$(gh repo view "$repo" --json visibility --jq .visibility)"
if [ "$visibility" != PUBLIC ]; then
    printf 'Репозиторий не публичный. Проверка публикации не пройдена.\n' >&2
    exit 1
fi
printf '\nГотово. Ссылка для сдачи: https://github.com/%s\n' "$repo"
