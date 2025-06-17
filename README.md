# LocalTTS - 本地化、可配置的 TTS 语音服务 (兼容 OpenAI)

一个基于 Microsoft Edge TTS 引擎的本地语音合成服务。它提供了一个简洁的 Web 界面和一套兼容 OpenAI TTS API 格式的接口，允许您轻松地将高质量的文本转语音功能集成到任何应用中。

![项目截图](https://private-user-images.githubusercontent.com/68144774/455600738-2ca617f8-1431-45f8-aa57-ffa57b01dabf.jpg?jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3NTAwODgyNjEsIm5iZiI6MTc1MDA4Nzk2MSwicGF0aCI6Ii82ODE0NDc3NC80NTU2MDA3MzgtMmNhNjE3ZjgtMTQzMS00NWY4LWFhNTctZmZhNTdiMDFkYWJmLmpwZz9YLUFtei1BbGdvcml0aG09QVdTNC1ITUFDLVNIQTI1NiZYLUFtei1DcmVkZW50aWFsPUFLSUFWQ09EWUxTQTUzUFFLNFpBJTJGMjAyNTA2MTYlMkZ1cy1lYXN0LTElMkZzMyUyRmF3czRfcmVxdWVzdCZYLUFtei1EYXRlPTIwMjUwNjE2VDE1MzI0MVomWC1BbXotRXhwaXJlcz0zMDAmWC1BbXotU2lnbmF0dXJlPWJkODRjYWE5ZTMzMzkzYjY0M2UxYjhiMWI5OGJjNWVhMDdhOTUyZjhlZmE5ZWM3YjdjYWE0OTNkNGY4NjMzOGQmWC1BbXotU2lnbmVkSGVhZGVycz1ob3N0In0.yrwMZi6u68_96DVinOEczeIXyYL286qERhq2n-bYMR0)

---

## ✨ 功能亮点

- **极致性能**:

  - **长文本并发处理**: 采用先进的异步并发模型，将长文本智能分段后同时请求。实测处理 **10000 字** 的文章仅需约 **35-40 秒**，即可生成超过 **30 分钟** 的高质量音频，性能卓越。
  - **专业音频拼接**: 使用 `pydub` 库确保所有并发生成的音频片段被无缝、正确地拼接，保证最终音频的完整性和播放质量。

- **高质量与多选择**:

  - **微软 Edge TTS 引擎**: 利用 `edge-tts` 提供多种自然、流畅、媲美真人的语音。
  - **海量语言与音色**: 内置支持全球上百种语言和数百种音色，满足多样化需求。

- **易用性与灵活性**:
  - **一键 Docker 部署**: 提供 `docker-compose` 配置，一条命令即可启动完整服务，无需关心环境和依赖。
  - **WebUI 友好界面**: 提供直观的网页界面，可进行文本输入、语言和音色选择，并即时播放。
  - **兼容 OpenAI API**: 提供与 OpenAI TTS (`v1/audio/speech`) 完全兼容的 API 接口，可作为本地、免费、不限速的平替方案。
  - **高度可配置**:
    - **动态端口修改**: 通过 `.env` 文件或 WebUI 轻松设置服务运行的端口。
    - **自定义音色映射**: 通过 WebUI 为 OpenAI 的标准音色 (`shimmer`, `alloy` 等) 灵活指定您喜欢的任何 `edge-tts` 语音。
  - **智能 API 指引**: API 使用说明中的 `curl` 示例会根据您的访问地址（包括反向代理域名）自动生成，方便复制和测试。

## 🐳 使用 Docker 部署 (推荐)

这是最简单、最可靠的部署方式，推荐所有用户使用。**默认端口为 `5050`**。

### 环境要求

- **Docker**: [安装 Docker Desktop](https://www.docker.com/products/docker-desktop/)

### 部署步骤

1.  **下载项目**
    克隆或下载本项目所有文件到您的本地。

2.  **创建并配置 `.env` 文件**

    - 项目中包含一个 `.env.example` 文件作为模板。请先将其复制为 `.env` 文件：
      ```bash
      cp .env.example .env
      ```
    - **端口配置 (可选)**: 编辑您的 `.env` 文件，修改 `TTS_PORT` 的值来指定端口。
    - **国内用户网络优化 (重要)**: 如果您在中国大陆地区的服务器上部署或在本地遇到网络问题，请编辑 `.env` 文件，**取消 `PIP_INDEX_URL` 这一行的注释**。这将极大地加速依赖安装过程。
      ```env
      # 取消下面这行的注释
      PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
      ```

3.  **构建并启动服务**
    在项目根目录下，打开终端并运行：

    ```bash
    docker-compose up --build -d
    ```

    - `docker-compose` 会自动构建镜像并以后台模式 (`-d`) 启动服务。

4.  **访问 WebUI**
    打开浏览器，访问 `http://localhost:5050` (或您在 `.env` 文件中配置的端口)。

### Docker 管理命令

- **停止服务**: `docker-compose down`
- **查看运行状态**: `docker ps`
- **查看服务日志**: `docker-compose logs -f`

---

## 📖 API 使用说明

API 指引部分已集成在 WebUI 中，并能根据您的访问地址动态生成，以下为通用说明。

### 端点

- `POST /v1/audio/speech`

### 请求格式

请求体为 JSON 格式，`Content-Type: application/json`。

#### 方式一：使用 OpenAI 兼容音色 (推荐)

```json
{
  "model": "tts-1",
  "input": "你好，世界！",
  "voice": "shimmer"
}
```

#### 方式二：直接使用 EdgeTTS 音色

```json
{
  "model": "tts-1",
  "input": "Hello world!",
  "voice": "en-US-AvaNeural"
}
```

---

## 🛠️ 手动部署 (高级)

如果您不想使用 Docker，也可以通过传统方式部署。

### 环境要求

- **Python**: 3.8 或更高版本
- **Conda**: 推荐使用 Conda 来管理环境

### 部署步骤

1.  **创建并激活 Conda 环境**:
    ```bash
    conda create -n local-tts python=3.10 -y
    conda activate local-tts
    ```
2.  **安装依赖**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **启动服务**:
    ```bash
    python app.py
    ```
    服务将根据 `config.json` 文件中的设置启动，默认端口为 `5050`。

---

## 🤝 贡献

欢迎任何形式的贡献！如果您有任何想法、建议或发现 Bug，请随时提交一个 Issue。

## 📄 许可

本项目采用 [MIT 许可证](LICENSE)。

```

```
