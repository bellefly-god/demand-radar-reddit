#!/bin/bash

# ============================================
# Reddit Scraper API 一键安装脚本
# ============================================

set -e

echo "=========================================="
echo "  Reddit Scraper API 安装中..."
echo "=========================================="

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 检查 Python
echo -e "\n${YELLOW}[1/4] 检查 Python...${NC}"
if command -v python3 &> /dev/null; then
    PYTHON="python3"
elif command -v python &> /dev/null; then
    PYTHON="python"
else
    echo -e "${RED}错误: 未找到 Python${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python: $($PYTHON --version)${NC}"

# 安装依赖
echo -e "\n${YELLOW}[2/4] 安装 Python 依赖...${NC}"
$PYTHON -m pip install -r "$SCRIPT_DIR/requirements.txt" --quiet
echo -e "${GREEN}✓ 依赖安装完成${NC}"

# 下载 YARS
echo -e "\n${YELLOW}[3/4] 下载 YARS 爬虫库...${NC}"
YARS_DIR="$SCRIPT_DIR/YARS"
if [ -d "$YARS_DIR" ]; then
    echo "YARS 已存在，更新..."
    cd "$YARS_DIR" && git pull --quiet
else
    git clone https://github.com/datavorous/YARS.git "$YARS_DIR" --quiet
fi
echo -e "${GREEN}✓ YARS 下载完成${NC}"

# 创建虚拟环境（可选）
echo -e "\n${YELLOW}[4/4] 创建虚拟环境...${NC}"
if [ ! -d "$SCRIPT_DIR/venv" ]; then
    $PYTHON -m venv "$SCRIPT_DIR/venv"
    source "$SCRIPT_DIR/venv/bin/activate"
    pip install -r "$SCRIPT_DIR/requirements.txt" --quiet
fi
echo -e "${GREEN}✓ 虚拟环境创建完成${NC}"

# 完成
echo -e "\n${GREEN}"
echo "=========================================="
echo "  安装完成!"
echo "=========================================="
echo ""
echo "启动服务:"
echo "  cd $SCRIPT_DIR"
echo "  source venv/bin/activate"
echo "  python api_server.py"
echo ""
echo "测试:"
echo "  curl 'http://localhost:8000/scrape?keyword=startup+problems'"
echo ""
echo "部署到服务器:"
echo "  nohup python api_server.py > api.log 2>&1 &"
echo ""
echo -e "${NC}"