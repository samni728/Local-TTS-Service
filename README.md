# 🚀 LocalTTS - 高性能、高可靠的本地化 TTS 语音服务

一个基于 Microsoft Edge TTS 引擎的本地语音合成服务，经过深度优化，能以极高的效率和可靠性处理长文本。它提供了一个简洁的 Web 界面和一套兼容 OpenAI TTS API 格式的接口，让您可以轻松地将高质量、高效率的文本转语音功能集成到任何应用中。

![LocalTTS WebUI 界面](./static/screen/1.jpg)

---

## ✨ 功能亮点

- **极致性能与可靠性**:

  - **高级文本处理**: 采用先进算法对输入文本进行**净化和重组**，能智能处理不合理的换行符和空格，并正确识别小数点，从源头上保证语音的自然流畅。
  - **智能分块**: 在文本预处理的基础上，将长文本智能地合并成大小适中、语义连贯的块，**极大减少了拼接点**，显著提升了听感。
  - **并发控制与可靠重试**: 使用异步信号量精确控制并发请求数量（默认为 20），既能享受并发带来的高效率，又避免了因请求过多而导致的“并发风暴”和服务器限流。
  - **闪电般拼接**: 使用系统级的 **FFmpeg** 进行音频流的无损拼接，速度是纯 Python 实现的数十倍，彻底解决超长文本合成时的本地处理瓶颈。
  - **快速输出**: 3 万字生成大概 1.5 小时的 mp3，每万字文本的速度大约是 15 秒。

- **安全与易用**:

  - **API 密钥保护**: 支持通过 WebUI 设置 API 密钥，保护您的服务不被滥用。
  - **智能 API 指引**: API 使用说明中的 `curl` 示例会根据您的设置，**自动**包含或移除密钥认证头，方便复制和测试。
  - **一键 Docker 部署**: 提供 `docker-compose` 配置，一条命令即可启动包含所有依赖（包括 FFmpeg）的完整服务。

- **高度可配置**:
  - **动态端口与密钥设置**: 通过 WebUI 轻松设置服务运行的端口和 API 密钥。
  - **自定义音色映射**: 通过 WebUI 为 OpenAI 的标准音色 (`shimmer`, `alloy` 等) 灵活指定您喜欢的任何 `edge-tts` 语音。
    ![LocalTTS 映射 端口 配置 key 界面](./static/screen/2.jpg)

## 🐳 使用 Docker 部署 (推荐)

这是最简单、最可靠的部署方式，推荐所有用户使用。**Docker 方案已内置 FFmpeg，您无需任何额外安装。**

### 环境要求

- **Docker**: [安装 Docker Desktop](https://www.docker.com/products/docker-desktop/) (适用于 Windows, macOS, 和 Linux)

### 部署步骤

1.  **下载项目**
    克隆或下载本项目所有文件到您的本地。

2.  **创建并配置 `.env` 文件**

    - 项目中包含一个 `.env.example` 文件作为模板。请先将其复制为 `.env` 文件：

      ```bash
      # 在 Linux / macOS 上
      cp .env.example .env

      # 在 Windows PowerShell 上
      copy .env.example .env
      ```

    - **端口配置 (可选)**: 编辑您的 `.env` 文件，修改 `TTS_PORT` 的值来指定端口（默认为 `5050`）。
    - **国内用户网络优化 (重要)**: 如果您在中国大陆地区的服务器上部署或在本地遇到网络问题，请编辑 `.env` 文件，**取消 `PIP_INDEX_URL` 这一行的注释**。这将极大地加速依赖安装过程。
      ```env
      # 取消下面这行的注释
      PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
      ```

3.  **构建并启动服务 仅在第一次构建时需要**
    在项目根目录下，打开终端或 PowerShell 并运行：

    ```bash
    docker-compose up --build -d
    ```

4.  **访问 WebUI**
    - 打开浏览器，访问 `http://localhost:5050` (或您在 `.env` 中配置的端口)。
    - **重要**: 首次启动后，强烈建议您进入 **服务设置**，设置您的 **API 密钥**并保存。

### Docker 管理命令

- **启动服务**: `docker-compose up -d`
- **停止服务**: `docker-compose down`
- **查看运行状态**: `docker ps`
- **查看服务日志**: `docker-compose logs -f`

---

## 🛠️ 手动部署 (高级)

如果您不想或不能使用 Docker，也可以通过传统方式部署。

### 环境要求

- **Python**: 3.8 或更高版本
- **FFmpeg**: **必须在您的系统中安装 FFmpeg。** 它是项目进行高性能音频拼接的核心依赖。
- **Conda**: (推荐) 用于管理 Python 环境。

### 1. 安装 FFmpeg (关键步骤)

您必须先在您的操作系统上安装 FFmpeg：

- #### **Windows (使用 Scoop 或 Chocolatey 包管理器)**

  **方法一: Scoop (推荐)**

  ```powershell
  scoop install ffmpeg
  ```

  **方法二: Chocolatey**

  ```powershell
  choco install ffmpeg
  ```

  **方法三: 手动下载**
  从 [FFmpeg 官网](https://ffmpeg.org/download.html) 下载适用于 Windows 的预编译文件，解压后将 `bin` 目录的完整路径添加到系统的 `PATH` 环境变量中。

- #### **macOS (使用 Homebrew)**

  ```bash
  brew install ffmpeg
  ```

- #### **Linux (使用系统包管理器)**
  - **Debian / Ubuntu**:
    ```bash
    sudo apt update && sudo apt install ffmpeg
    ```
  - **CentOS / RHEL / Fedora**:
    `bash
sudo dnf install ffmpeg
`
    安装完成后，可以在终端或命令行中运行 `ffmpeg -version` 来验证是否安装成功。

### 2. 部署 Python 环境

1.  **创建并激活 Conda 环境**:
    ```bash
    conda create -n local-tts python=3.10 -y
    conda activate local-tts
    ```
2.  **安装 Python 依赖**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **启动服务**:
    ```bash
    python app.py
    ```
    服务将根据 `config.json` 文件中的设置启动，默认端口为 `5050`。

---

## 📖 API 使用说明

![LocalTTS api指引界面](./static/screen/3.jpg)
API 指引部分已集成在 WebUI 中，并能根据您的访问地址动态生成。

### 端点

- `POST /v1/audio/speech`

### 请求格式

- **Headers**:
  - `Content-Type: application/json`
  - `Authorization: Bearer <Your-API-Token>` (如果已在 WebUI 中设置)
- **Body**:
  ```json
  {
    "model": "tts-1",
    "input": "要转换的文本。",
    "voice": "shimmer"
  }
  ```
  - `voice`: 可以是 OpenAI 的标准音色 (`shimmer`, `alloy` 等)，也可以是任意 EdgeTTS 的完整音色名称 (如 `zh-CN-XiaoxiaoNeural`)。

---

## 🤝 贡献

欢迎任何形式的贡献！如果您有任何想法、建议或发现 Bug，请随时提交一个 Issue。

## 📄 许可

本项目采用 [MIT 许可证](LICENSE)。

```

```
