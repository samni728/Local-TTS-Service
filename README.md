
# LocalTTS - 本地化、可配置的 TTS 语音服务 (兼容 OpenAI)

一个基于 Microsoft Edge TTS 引擎的本地语音合成服务。它提供了一个简洁的 Web 界面和一套兼容 OpenAI TTS API 格式的接口，允许您轻松地将高质量的文本转语音功能集成到任何应用中。

![项目截图](https://private-user-images.githubusercontent.com/68144774/455600738-2ca617f8-1431-45f8-aa57-ffa57b01dabf.jpg?jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3NTAwODgyNjEsIm5iZiI6MTc1MDA4Nzk2MSwicGF0aCI6Ii82ODE0NDc3NC80NTU2MDA3MzgtMmNhNjE3ZjgtMTQzMS00NWY4LWFhNTctZmZhNTdiMDFkYWJmLmpwZz9YLUFtei1BbGdvcml0aG09QVdTNC1ITUFDLVNIQTI1NiZYLUFtei1DcmVkZW50aWFsPUFLSUFWQ09EWUxTQTUzUFFLNFpBJTJGMjAyNTA2MTYlMkZ1cy1lYXN0LTElMkZzMyUyRmF3czRfcmVxdWVzdCZYLUFtei1EYXRlPTIwMjUwNjE2VDE1MzI0MVomWC1BbXotRXhwaXJlcz0zMDAmWC1BbXotU2lnbmF0dXJlPWJkODRjYWE5ZTMzMzkzYjY0M2UxYjhiMWI5OGJjNWVhMDdhOTUyZjhlZmE5ZWM3YjdjYWE0OTNkNGY4NjMzOGQmWC1BbXotU2lnbmVkSGVhZGVycz1ob3N0In0.yrwMZi6u68_96DVinOEczeIXyYL286qERhq2n-bYMR0)  

---

## ✨ 功能亮点

- **高质量语音**：利用 Microsoft Edge 强大的 `edge-tts` 引擎，提供多种自然流畅的语音。
- **多语言支持**：内置支持全球上百种语言和对应的音色。
- **WebUI 界面**：提供一个直观的网页界面，可以进行文本输入、语言和音色选择，并即时播放。
- **兼容 OpenAI API**：提供与 OpenAI TTS (`v1/audio/speech`) 完全兼容的 API 接口，可无缝替换现有应用。
- **高度可配置**：
  - **动态端口修改**：通过 WebUI 轻松设置服务运行的端口。
  - **自定义音色映射**：通过 WebUI 为 OpenAI 的标准音色 (`shimmer`, `alloy` 等) 灵活指定您喜欢的任何 `edge-tts` 语音。
- **智能 API 指引**：API 使用说明中的 `curl` 示例会根据您当前的访问地址（包括反向代理域名）自动生成，方便复制和测试。
- **纯本地部署**：所有核心服务均在本地运行，易于部署和管理。

## 🚀 快速开始

### 环境要求

- **Python**: 3.8 或更高版本
- **Conda**: 推荐使用 Conda 来管理环境

### 部署步骤

1.  **克隆或下载项目**
    将本项目代码下载到您的本地服务器。

2.  **创建并激活 Conda 环境**
    ```bash
    # 创建一个名为 local-tts 的新环境 (推荐使用 Python 3.10)
    conda create -n local-tts python=3.10 -y

    # 激活环境
    conda activate local-tts
    ```

3.  **安装依赖**
    进入项目根目录，然后运行：
    ```bash
    pip install -r requirements.txt
    ```

4.  **启动服务**
    ```bash
    python app.py
    ```
    服务启动时，会自动在项目根目录创建一个 `config.json` 文件。

5.  **访问 WebUI**
    打开浏览器，访问 `http://localhost:5050` (或您在 `config.json` 或 WebUI 中配置的其他端口)。

## ⚙️ WebUI 配置

通过访问 WebUI，您可以方便地进行以下配置：

1.  **服务端口**：
    - 在 “服务设置” -> “服务端口” 中输入您想要的端口号。
    - 点击 “保存设置”。
    - **注意**：端口修改需要**手动重启服务** (`Ctrl+C` 后再 `python app.py`) 才能生效。

2.  **OpenAI 音色映射**：
    - 在 “服务设置” -> “OpenAI 音色映射” 中，为每个 OpenAI 标准音色（如 `shimmer`）选择一个您喜欢的具体 EdgeTTS 语音。
    - 点击 “保存设置”。
    - **此项修改会立即生效**，无需重启服务。

## 📖 API 使用说明

API 指引部分已集成在 WebUI 中，并能根据您的访问地址动态生成，以下为通用说明。

### 端点

- `POST /v1/audio/speech`

### 请求格式

请求体为 JSON 格式，`Content-Type: application/json`。

#### 方式一：使用 OpenAI 兼容音色 (推荐)

这种方式会使用您在 WebUI 中配置的音色映射。

```json
{
  "model": "tts-1",
  "input": "你好，世界！",
  "voice": "shimmer"
}
```

#### 方式二：直接使用 EdgeTTS 音色

这种方式会直接调用指定的 EdgeTTS 语音，绕过您的自定义映射。

```json
{
  "model": "tts-1",
  "input": "Hello world!",
  "voice": "en-US-AvaNeural"
}
```

### `curl` 调用示例

```bash
# 使用 OpenAI 兼容音色
curl -X POST http://YOUR_SERVICE_URL/v1/audio/speech \
-H "Content-Type: application/json" \
-d '{
  "model": "tts-1",
  "input": "这是一个测试。",
  "voice": "shimmer"
}' --output test.mp3
```
*(提示: 请将 `http://YOUR_SERVICE_URL` 替换为您的实际服务地址)*


## 🤝 贡献

欢迎任何形式的贡献！如果您有任何想法、建议或发现 Bug，请随时提交一个 Issue。

如果您想贡献代码，请：

1.  Fork 本仓库
2.  创建您的新分支 (`git checkout -b feature/AmazingFeature`)
3.  提交您的更改 (`git commit -m 'Add some AmazingFeature'`)
4.  将您的分支推送到远程 (`git push origin feature/AmazingFeature`)
5.  创建一个 Pull Request

## 📄 许可

本项目采用 [MIT 许可证](LICENSE)。请随意使用，但请遵守相关服务（如 Microsoft Edge TTS）的使用条款。