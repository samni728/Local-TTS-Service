# 本地 TTS (文字转语音) 服务

一个基于 Microsoft Edge TTS 引擎的本地语音合成服务，提供高质量的中文语音合成，并兼容 OpenAI TTS API 格式。

## 功能特点

- 支持多个中文声音角色
- 兼容 OpenAI TTS API 调用格式
- 完全本地服务，无需 API Key
- 支持异步处理
- 返回标准 MP3 格式音频

## 安装步骤

1. 安装依赖：

```bash
pip install -r requirements.txt
```

2. 启动服务：

```bash
python func_tts.py
```

服务默认运行在 `http://localhost:5000`

## API 使用说明

### 1. 生成语音

**请求格式：**

```http
POST http://localhost:5000/v1/audio/speech
Content-Type: application/json

{
    "model": "tts-1",
    "voice": "xiaoxiao",
    "input": "要转换的文本"
}
```

### 2. 获取可用声音列表

**请求格式：**

```http
GET http://localhost:5000/v1/audio/voices
```

## 支持的声音列表

| 声音 ID    | 名称 | 特点描述           |
| ---------- | ---- | ------------------ |
| xiaoxiao   | 晓晓 | 温暖女声，通用场景 |
| xiaoyi     | 晓伊 | 温柔女声，适合对话 |
| yunjian    | 云健 | 成熟男声，商务场景 |
| yunxi      | 云希 | 年轻男声，活力风格 |
| yunxia     | 云夏 | 女声，自然清新     |
| yunyang    | 云扬 | 新闻男声，庄重有力 |
| xiaomeng   | 晓梦 | 女声，甜美动听     |
| xiaomo     | 晓墨 | 女声，知性优雅     |
| xiaorui    | 晓睿 | 女声，自然流畅     |
| xiaoshuang | 晓双 | 儿童声音，活泼可爱 |

## 代码示例

### Python 调用示例

```python
import requests

def generate_speech(text, voice="xiaoxiao"):
    response = requests.post(
        "http://localhost:5000/v1/audio/speech",
        json={
            "model": "tts-1",
            "voice": voice,
            "input": text
        }
    )

    if response.status_code == 200:
        with open("output.mp3", "wb") as f:
            f.write(response.content)
        print("语音文件已保存为 output.mp3")
    else:
        print("错误:", response.json())

# 使用示例
generate_speech("你好，这是一个测试文本", "xiaoxiao")
```

### JavaScript 调用示例

```javascript
async function generateSpeech(text, voice = "xiaoxiao") {
  try {
    const response = await fetch("http://localhost:5000/v1/audio/speech", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "tts-1",
        voice: voice,
        input: text,
      }),
    });

    if (response.ok) {
      const blob = await response.blob();
      const audio = new Audio(URL.createObjectURL(blob));
      audio.play();
    } else {
      const error = await response.json();
      console.error("TTS 错误:", error);
    }
  } catch (error) {
    console.error("请求错误:", error);
  }
}

// 使用示例
generateSpeech("你好，这是一个测试文本", "xiaoxiao");
```

## 错误处理

服务返回标准的 HTTP 状态码：

- 200: 请求成功
- 400: 请求参数错误
- 500: 服务器内部错误

错误响应格式：

```json
{
  "error": {
    "message": "错误描述",
    "type": "error_type",
    "code": "error_code"
  }
}
```

## 注意事项

1. 需要网络连接（edge-tts 依赖微软服务）
2. 生成的音频文件为 MP3 格式
3. 支持中文和英文文本输入
4. 每次请求都会生成新的音频文件
5. 默认使用 "xiaoxiao" (晓晓) 声音
6. 服务使用异步处理，支持并发请求

## 依赖说明

主要依赖包：

- edge-tts: Microsoft Edge TTS 引擎
- flask: Web 服务框架
- asgiref: 异步支持
- python-dotenv: 环境变量管理

## 许可说明

本项目仅供学习和研究使用，请遵守相关服务和 API 的使用条款。
