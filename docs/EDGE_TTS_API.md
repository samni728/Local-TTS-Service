# Local TTS Service：OpenAI 兼容与 Microsoft Edge 扩展 API

本服务保留 OpenAI 文本转语音的基础请求格式，并在同一个端点上增加 Microsoft Speech 的情绪、角色、风格强度、音调以及自动选音扩展。

## 端点

```text
POST /v1/audio/speech
```

当 `config.json` 配置了 `api_token` 时，需要请求头：

```text
Authorization: Bearer <API_TOKEN>
Content-Type: application/json
```

成功响应为 `audio/mpeg`。响应头 `X-TTS-Voice` 会返回最终使用的完整音色名；`X-TTS-Chunks` 和 `X-TTS-Chunk-Size` 可用于观察实际请求块数和分块上限。使用情绪或角色时，还会返回 `X-TTS-Style` 和 `X-TTS-Role`。如果使用 WebUI 保存的 OpenAI 音色预设，`X-TTS-Preset` 会返回对应别名。

## 1. OpenAI 兼容基础调用

```bash
curl -X POST http://127.0.0.1:5050/v1/audio/speech \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <API_TOKEN>" \
  -d '{
    "model": "tts-1",
    "input": "你好，这是一段基础语音。",
    "voice": "shimmer"
  }' \
  --output speech.mp3
```

`shimmer`、`alloy`、`fable`、`onyx`、`nova`、`echo` 会按 WebUI 中保存的 OpenAI 音色预设转换。完整预设包含实际 Microsoft 音色、风格、角色、风格强度、语速、音调和文本过滤规则。

### 在 WebUI 中保存完整预设

1. 在试听区选择语言和音色。
2. 调整风格、角色、强度、语速、音调与文本过滤并试听。
3. 在“保存为 OpenAI 标准音色”中选择 `shimmer` 等别名。
4. 点击“保存当前试听配置并替换映射”。

之后外部程序只需发送上面的 OpenAI 标准请求。完整预设默认具有优先级，避免某些 SDK 自动发送 `speed: 1.0` 时覆盖 WebUI 中保存的语速。需要临时使用请求中的扩展参数覆盖预设时，可传入 `"override_preset": true`。

## 2. OpenAI 格式的情绪扩展

```bash
curl -X POST http://127.0.0.1:5050/v1/audio/speech \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <API_TOKEN>" \
  -d '{
    "model": "tts-1",
    "input": "今天的结果很不错，我们继续保持。",
    "voice": "shimmer",
    "style": "cheerful",
    "style_degree": 1.25,
    "speed": 1.05,
    "strict_capabilities": true
  }' \
  --output cheerful.mp3
```

`emotion` 是 `style` 的兼容别名；`emotion_intensity`、`styleDegree` 是 `style_degree` 的兼容别名。新代码推荐使用蛇形命名 `style_degree`。

## 3. 完整 Edge/Azure 音色调用

```bash
curl -X POST http://127.0.0.1:5050/v1/audio/speech \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <API_TOKEN>" \
  -d '{
    "model": "tts-1",
    "input": "这是一段同时使用角色和情绪强度的语音。",
    "voice": "zh-CN-XiaomoNeural",
    "style": "cheerful",
    "role": "YoungAdultFemale",
    "style_degree": 1.35,
    "speed": 1.05,
    "pitch": 1.0,
    "strict_capabilities": true,
    "stream": false
  }' \
  --output role.mp3
```

情绪、角色和风格强度通过同一个 Microsoft `mstts:express-as` 元素生成；语速和音调通过 `prosody` 生成。

## 4. 按国家/语言、性别和能力自动选音

当 `voice` 为 `auto` 时，服务会根据条件筛选音色。`locale` 必填；`gender`、`style`、`role` 和 `voice_type` 可选。

```bash
curl -X POST http://127.0.0.1:5050/v1/audio/speech \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <API_TOKEN>" \
  -d '{
    "model": "tts-1",
    "input": "系统会自动选择一个支持开朗情绪的中文女声。",
    "voice": "auto",
    "locale": "zh-CN",
    "gender": "Female",
    "style": "cheerful",
    "style_degree": 1.2,
    "edge_available_only": true,
    "stream": true
  }' \
  --output auto.mp3
```

可用性优先级为：满足全部条件的旧 Edge 清单音色优先，其次是 Azure 文档新增音色。

## 参数说明

| 字段 | 类型 | 默认值 | 范围/说明 |
| --- | --- | --- | --- |
| `model` | string | `tts-1` | 保留 OpenAI 兼容字段 |
| `input` | string | 必填 | 要合成的纯文本或可清洗文本 |
| `voice` | string | 必填 | OpenAI 别名、完整音色名或 `auto` |
| `locale` | string | - | `voice=auto` 时必填，例如 `zh-CN`、`en-US` |
| `gender` | string | - | `Female`、`Male`、`Neutral`；自动选音或严格校验时使用 |
| `voice_type` | string | - | `Standard`、`Multilingual`、`Neural HD`、`Neural HD Flash`、`Neural HD Omni`、`MAI Voice` |
| `style` / `emotion` | string | `general` | 当前音色支持的情绪或场景风格 |
| `style_degree` | number | `1.0` | 情绪/风格强度，`0.01-2.0` |
| `role` | string | 空 | 当前音色支持的角色 |
| `speed` | number | `1.0` | 语速倍率，API 接受 `0.25-4.0`；WebUI 为保证听感限制到 `0.25-2.0` |
| `pitch` | number | `1.0` | 音调倍率，`0.5-1.5` |
| `strict_capabilities` | boolean | `false` | 为 `true` 时，不支持的情绪、角色或性别组合直接返回 HTTP 400 |
| `edge_available_only` | boolean | `false` | 自动选音时只选择旧 Edge 清单内音色 |
| `stream` | boolean | `false` | 是否流式返回 MP3 数据 |
| `chunk_size` | integer | WebUI 设置 | 语义分块上限，`50-2000`；长文建议 `250-500` |
| `sync_chunks` | integer | WebUI 设置 | 流式返回时先顺序生成的块数，`0-20`，一般保持 `1` |
| `max_concurrent_requests` | integer | WebUI 设置 | 单次请求的最大并发，`1-32`；VPS 建议从 `4-8` 开始 |
| `cleaning_options` | object | - | API 过滤同步关闭时使用的文本清洗设置 |
| `override_preset` | boolean | `false` | 使用 OpenAI 别名时，允许请求参数临时覆盖 WebUI 保存的完整预设 |

分段不是简单按字符数截断。服务会优先使用句号、问号、感叹号、逗号、分号、冒号和英文单词边界，并保护小数与百分比。多个短段落会在不超过上限时合并为一次请求，段落边界仍会保留；Microsoft SSML 路径会把边界转成短停顿。

## 查询音色及能力

### 查询完整能力目录

```text
GET /v1/voices
```

支持的查询参数：

- `locale=zh-CN`
- `gender=Female`
- `voice_type=Standard`
- `style=cheerful`
- `role=YoungAdultFemale`
- `supports_style=true`
- `supports_role=true`
- `edge_available=true`
- `q=xiaoxiao`

示例：

```bash
curl "http://127.0.0.1:5050/v1/voices?locale=zh-CN&gender=Female&supports_style=true" \
  -H "Authorization: Bearer <API_TOKEN>"
```

### 查询单个音色

```bash
curl "http://127.0.0.1:5050/v1/voices/zh-CN-XiaomoNeural" \
  -H "Authorization: Bearer <API_TOKEN>"
```

返回数据中的重要字段：

- `styles`：该音色支持的情绪/场景风格。
- `roles`：该音色支持的角色。
- `supports_style_degree`：是否支持风格强度。
- `gender`：音色本身的性别。
- `voice_type`：标准、多语言、HD、HD Omni、HD Flash 或 MAI。
- `edge_available`：是否存在于项目原有 Edge 音色清单。
- `azure_documented`：是否来自 Azure 语言支持文档。

## 常见角色值

- `Girl`
- `Boy`
- `YoungAdultFemale`
- `YoungAdultMale`
- `OlderAdultFemale`
- `OlderAdultMale`
- `SeniorFemale`
- `SeniorMale`
- `Narrator`

角色和情绪都是“按音色支持”的能力，不能假设每个音色都支持。推荐先查询 `/v1/voices/<voice>`，或者在请求中启用 `strict_capabilities`。

## 兼容性与限制

1. Azure 文档中的新音色不一定全部能通过当前 Edge-compatible 端点调用；可用性可能受微软区域、账户、预览状态或接口策略影响。
2. 带 `style` 或 `role` 的流式请求会使用 Microsoft SSML 路径，避免 `edge-tts` 基础调用忽略情绪参数。
3. 不启用 `strict_capabilities` 时保持旧版兼容行为：Microsoft 可能忽略无效风格并退回中性语音。
4. 音色目录在服务启动时从本地 Azure 文档和 `tts_data/voices_list.txt` 构建，不依赖启动时联网。

## Microsoft 官方参考

- [Azure Speech 语言和音色支持](https://learn.microsoft.com/azure/ai-services/speech-service/language-support)
- [使用 SSML 配置声音、风格、角色和韵律](https://learn.microsoft.com/azure/ai-services/speech-service/speech-synthesis-markup-voice)
- [SSML 概览](https://learn.microsoft.com/azure/ai-services/speech-service/speech-synthesis-markup)
