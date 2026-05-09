@echo off
REM Solana Bot Analyzer 一键运行脚本 (Windows)

echo ========================================
echo Solana 机器人地址分析工具 - 一键运行
echo ========================================

REM 检查 Python
set PYTHON_CMD=python
python --version >nul 2>&1
if errorlevel 1 (
    py -3 --version >nul 2>&1
    if errorlevel 1 (
        echo 错误: 未找到 Python，请先安装 Python 3.9 或更高版本。
        pause
        exit /b 1
    )
    set PYTHON_CMD=py -3
)

REM 检查并创建虚拟环境（可选）
if not exist venv (
    echo 创建虚拟环境 venv...
    %PYTHON_CMD% -m venv venv
)

REM 激活虚拟环境
call venv\Scripts\activate.bat

REM 安装依赖
echo 安装依赖库 (requirements.txt)...
pip install --upgrade pip
pip install -r requirements.txt

REM 检查 .env 文件
if not exist .env (
    echo 提示: 未找到 .env 文件，将使用环境变量或默认配置。
    echo 如需设置 Helius API Key，请创建 .env 文件并添加:
    echo HELIUS_API_KEY=your_api_key_here
    echo MODE=feb
)

REM 运行主程序
echo 开始运行 main.py ...
python main.py

echo 运行完成！输出文件保存在 output\ 目录下。
pause
