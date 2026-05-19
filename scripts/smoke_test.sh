#!/bin/bash
set -e
PASS=0
FAIL=0

check() {
  if eval "$2" &>/dev/null; then
    echo "  ✓ $1"
    PASS=$((PASS+1))
  else
    echo "  ✗ $1  <-- FAILED"
    FAIL=$((FAIL+1))
  fi
}

echo ""
echo "=== image-factory smoke test ==="
echo ""
echo "[System]"
check "Ubuntu 24.04"         "lsb_release -r | grep -q '24.04'"
check "Python 3.12"          "python3 --version | grep -q '3.12'"
check "pip available"        "pip --version"
check "git installed"        "git --version"

echo ""
echo "[Proxy]"
check "apt proxy configured" "cat /etc/apt/apt.conf.d/99proxy | grep -q '10.93.144.53'"
check "git proxy configured" "git config --global http.proxy | grep -q '10.93.144.53'"
check "pip proxy configured" "cat ~/.config/pip/pip.conf | grep -q '10.93.144.53'"
check "internet reachable"   "curl -s --proxy http://10.93.144.53:8080 https://google.com -o /dev/null"

echo ""
echo "[Project structure]"
check "packer/ exists"       "[ -d ~/image-factory/packer ]"
check "ansible/ exists"      "[ -d ~/image-factory/ansible ]"
check "docker/ exists"       "[ -d ~/image-factory/docker ]"
check "ai-agent/ exists"     "[ -d ~/image-factory/ai-agent ]"
check "docs/adr/ exists"     "[ -d ~/image-factory/docs/adr ]"
check "requirements.txt"     "[ -f ~/image-factory/requirements.txt ]"
check ".gitignore"           "[ -f ~/image-factory/.gitignore ]"

echo ""
echo "[Python packages]"
check "requests importable"  "python3 -c 'import requests'"
check "pydantic importable"  "python3 -c 'import pydantic'"
check "sqlalchemy importable" "python3 -c 'import sqlalchemy'"
check "minio importable"     "python3 -c 'import minio'"

echo ""
echo "================================"
echo "  Passed: $PASS  |  Failed: $FAIL"
echo "================================"
echo ""
[ $FAIL -eq 0 ] && echo "M1 EXIT GATE: PASSED ✓" || echo "M1 EXIT GATE: FAILED — fix the items marked ✗"
echo ""
