#!/bin/bash
# 货币数据分析运行脚本

echo "🪙 货币数据分析工具"
echo "===================="

# 检查 Python 环境
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到 Python3，请先安装 Python3"
    exit 1
fi

# 检查必要的 Python 包
echo "📦 检查 Python 依赖..."
python3 -c "import aiomysql, asyncio, statistics, dataclasses" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "❌ 缺少必要的 Python 包，请安装："
    echo "pip install aiomysql python-dotenv"
    exit 1
fi

# 检查环境变量文件
if [ ! -f .env ]; then
    echo "❌ 未找到 .env 文件，请确保数据库配置正确"
    echo "需要设置 SQLALCHEMY_DATABASE_URL 环境变量"
    exit 1
fi

echo "✅ 环境检查通过，开始分析..."
echo ""

# 运行分析脚本
echo "🔍 步骤 1/2: 数据库分析..."
python3 script/coin_analysis.py

if [ $? -eq 0 ]; then
    echo ""
    echo "📊 步骤 2/2: 可视化分析..."
    python3 script/coin_visualizer.py

    echo ""
    echo "✅ 分析完成！"
    echo "📄 详细数据已保存到 coin_analysis_*.json 文件"
    echo "📖 查看完整报告请参考: COIN_ANALYSIS_REPORT.md"
    echo "📚 使用说明请参考: COIN_ANALYSIS_README.md"
else
    echo "❌ 数据库分析失败，请检查数据库连接"
    exit 1
fi
