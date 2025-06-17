document.addEventListener("DOMContentLoaded", () => {
  // 1. 全局变量
  let allVoices = [];
  let currentConfig = {};
  const OPENAI_VOICE_ALIASES = [
    "shimmer",
    "alloy",
    "fable",
    "onyx",
    "nova",
    "echo",
  ];

  // 2. DOM 元素获取
  const textInput = document.getElementById("text-input");
  const languageSelect = document.getElementById("language-select");
  const voiceSelect = document.getElementById("voice-select");
  const speakButton = document.getElementById("speak-button");
  const audioPlayer = document.getElementById("audio-player");
  const errorMessage = document.getElementById("error-message");
  const portInput = document.getElementById("port-input");
  const mappingsContainer = document.getElementById(
    "openai-mappings-container"
  );
  const saveSettingsButton = document.getElementById("save-settings-button");
  const settingsFeedback = document.getElementById("settings-feedback");
  const speakButtonText = speakButton.querySelector(".button-text");
  const speakButtonSpinner = speakButton.querySelector(".spinner");

  // NEW: 获取 API 指引中的代码块元素
  const apiEndpointDisplay = document.getElementById("api-endpoint-display");
  const curlExampleOpenAI = document.getElementById("curl-example-openai");
  const curlExampleDirect = document.getElementById("curl-example-direct");

  // 3. 功能函数
  const showMessage = (element, message, isError = false) => {
    element.textContent = message;
    element.className = isError ? "feedback error" : "feedback success";
    element.style.display = "block";
    setTimeout(() => {
      element.style.display = "none";
    }, 5000);
  };

  // NEW: 更新 API 指引中的 URL
  const updateApiExamples = () => {
    // 获取当前页面的源地址，例如 https://tts.123go.eu.org 或 http://localhost:5050
    const origin = window.location.origin;
    const apiUrl = `${origin}/v1/audio/speech`;

    if (apiEndpointDisplay) apiEndpointDisplay.textContent = apiUrl;

    if (curlExampleOpenAI) {
      curlExampleOpenAI.textContent = `curl -X POST ${apiUrl} \\
-H "Content-Type: application/json" \\
-d '{
  "model": "tts-1",
  "input": "你好，这是一个兼容 OpenAI 的测试。",
  "voice": "shimmer"
}' --output openai_test.mp3`;
    }

    if (curlExampleDirect) {
      curlExampleDirect.textContent = `curl -X POST ${apiUrl} \\
-H "Content-Type: application/json" \\
-d '{
  "model": "tts-1",
  "input": "Hello, this is a direct voice test.",
  "voice": "en-US-AriaNeural"
}' --output direct_test.mp3`;
    }
  };

  const updateVoiceList = (selectedLocale) => {
    voiceSelect.innerHTML = "";
    const filteredVoices = allVoices.filter((v) => v.locale === selectedLocale);
    if (filteredVoices.length === 0) {
      voiceSelect.innerHTML = "<option>无可用声音</option>";
      voiceSelect.disabled = true;
      return;
    }
    filteredVoices.forEach((voice) => {
      const option = document.createElement("option");
      option.value = voice.name;
      option.textContent = `${voice.short_name} (${voice.gender})`;
      voiceSelect.appendChild(option);
    });
    voiceSelect.disabled = false;
  };

  const populateSettingsForm = () => {
    portInput.value = currentConfig.port;
    mappingsContainer.innerHTML = "";
    OPENAI_VOICE_ALIASES.forEach((alias) => {
      const currentMapping = currentConfig.openai_voice_map[alias];
      const wrapper = document.createElement("div");
      wrapper.className = "form-group-inline";
      wrapper.innerHTML = `
                <label class="settings-label">${alias}</label>
                <select id="mapping-${alias}" class="settings-input"></select>
            `;
      const select = wrapper.querySelector("select");

      allVoices.forEach((voice) => {
        const option = document.createElement("option");
        option.value = voice.name;
        option.textContent = `${voice.name} (${voice.gender})`;
        if (voice.name === currentMapping) option.selected = true;
        select.appendChild(option);
      });
      mappingsContainer.appendChild(wrapper);
    });
  };

  const handleSaveSettings = async () => {
    const newConfig = {
      port: parseInt(portInput.value, 10),
      openai_voice_map: {},
    };
    OPENAI_VOICE_ALIASES.forEach((alias) => {
      newConfig.openai_voice_map[alias] = document.getElementById(
        `mapping-${alias}`
      ).value;
    });

    try {
      const response = await fetch("/v1/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newConfig),
      });
      const result = await response.json();
      showMessage(
        settingsFeedback,
        result.message || result.error,
        !response.ok
      );
      if (response.ok)
        currentConfig.openai_voice_map = newConfig.openai_voice_map;
    } catch (error) {
      showMessage(settingsFeedback, "保存失败: 无法连接到服务器。", true);
    }
  };

  const setLoading = (isLoading) => {
    speakButton.disabled = isLoading;
    speakButtonSpinner.style.display = isLoading ? "block" : "none";
    speakButtonText.style.display = isLoading ? "none" : "inline";
  };

  const handleSpeakClick = async () => {
    const text = textInput.value.trim();
    const voice = voiceSelect.value;
    if (!text) {
      showMessage(errorMessage, "请输入文本内容。", true);
      return;
    }
    if (!voice || voiceSelect.disabled) {
      showMessage(errorMessage, "请选择一个有效的声音。", true);
      return;
    }

    setLoading(true);
    errorMessage.style.display = "none";
    audioPlayer.style.display = "none";

    try {
      const response = await fetch("/v1/audio/speech", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: "tts-1", input: text, voice: voice }),
      });
      if (response.ok) {
        const blob = await response.blob();
        if (blob.size === 0) {
          throw new Error("服务器返回了空的音频文件。");
        }
        audioPlayer.src = URL.createObjectURL(blob);
        audioPlayer.style.display = "block";
        audioPlayer.play();
      } else {
        const errorData = await response.json();
        throw new Error(errorData.error?.message || "发生未知错误。");
      }
    } catch (error) {
      showMessage(errorMessage, `语音生成失败: ${error.message}`, true);
    } finally {
      setLoading(false);
    }
  };

  const initialize = async () => {
    try {
      const [voicesResponse, configResponse] = await Promise.all([
        fetch("/v1/audio/all_voices"),
        fetch("/v1/config"),
      ]);
      if (!voicesResponse.ok || !configResponse.ok)
        throw new Error("无法加载初始化数据。");

      allVoices = await voicesResponse.json();
      currentConfig = await configResponse.json();

      languageSelect.addEventListener("change", () =>
        updateVoiceList(languageSelect.value)
      );
      speakButton.addEventListener("click", handleSpeakClick);
      saveSettingsButton.addEventListener("click", handleSaveSettings);

      const defaultLang =
        Object.keys(currentConfig.openai_voice_map)
          .map((k) => currentConfig.openai_voice_map[k].substring(0, 5))
          .find((l) => l.startsWith("zh")) || "zh-CN";
      languageSelect.value = defaultLang;
      updateVoiceList(defaultLang);
      populateSettingsForm();

      // KEY CHANGE: 页面加载后立即更新 API 示例
      updateApiExamples();
    } catch (error) {
      showMessage(errorMessage, error.message, true);
    }
  };

  initialize();
});
