document.addEventListener("DOMContentLoaded", () => {
  // 1. 全局变量
  let allVoices = [];
  let currentConfig = {};
  let lastGeneratedBlobUrl = null;
  let progressInterval = null;
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
  const audioContainer = document.getElementById("audio-container");
  const audioPlayer = document.getElementById("audio-player");
  const downloadLink = document.getElementById("download-link");
  const errorMessage = document.getElementById("error-message");
  const portInput = document.getElementById("port-input");
  const apiTokenInput = document.getElementById("api-token-input");
  const generateTokenButton = document.getElementById("generate-token-button");
  const mappingsContainer = document.getElementById(
    "openai-mappings-container"
  );
  const settingsFeedback = document.getElementById("settings-feedback");
  const saveSettingsButton = document.getElementById("save-settings-button");
  const charCounter = document.getElementById("char-counter");
  const autoPlayCheckbox = document.getElementById("auto-play");
  const concurrencyInput = document.getElementById("concurrency-input");
  const progressContainer = document.getElementById("progress-container");
  const progressBar = document.getElementById("progress-bar");
  const progressText = document.getElementById("progress-text");
  const cleaningOptionsPanel = document.getElementById(
    "cleaning-options-panel"
  );
  const syncApiFilteringCheckbox =
    document.getElementById("sync-api-filtering");

  // 3. 功能函数
  const showMessage = (element, message, isError = false) => {
    element.textContent = message;
    element.className = isError ? "feedback error" : "feedback success";
    element.style.display = "block";
    setTimeout(() => {
      element.style.display = "none";
    }, 3000);
  };

  const setLoading = (isLoading) => {
    speakButton.disabled = isLoading;
    const buttonText = speakButton.querySelector(".button-text");
    if (isLoading) {
      progressContainer.style.display = "flex";
      let progress = 0;
      progressBar.style.width = "0%";
      progressText.textContent = "0%";
      if (progressInterval) clearInterval(progressInterval);
      progressInterval = setInterval(() => {
        if (progress < 95) {
          const increment = progress < 50 ? 1 : progress < 80 ? 0.5 : 0.2;
          progress = Math.min(progress + increment, 95);
          progressBar.style.width = `${progress}%`;
          progressText.textContent = `${Math.floor(progress)}%`;
        }
      }, 500);
    } else {
      if (progressInterval) clearInterval(progressInterval);
      progressBar.style.width = "100%";
      progressText.textContent = "100%";
      setTimeout(() => {
        progressContainer.style.display = "none";
      }, 1000);
    }
  };

  const updateApiExamples = () => {
    const origin = window.location.origin;
    const apiUrl = `${origin}/v1/audio/speech`;
    const apiEndpointDisplay = document.getElementById("api-endpoint-display");
    const curlExampleOpenAI = document.getElementById("curl-example-openai");
    const curlExampleDirect = document.getElementById("curl-example-direct");
    const token = apiTokenInput.value.trim();
    const authHeader = token ? ` \\\n-H "Authorization: Bearer ${token}"` : "";
    if (apiEndpointDisplay) apiEndpointDisplay.textContent = apiUrl;
    if (curlExampleOpenAI)
      curlExampleOpenAI.textContent = `curl -X POST ${apiUrl}${authHeader} \\\n-H "Content-Type: application/json" \\\n-d '{\n  "model": "tts-1",\n  "input": "你好，这是一个兼容 OpenAI 的测试。",\n  "voice": "shimmer"\n}' --output openai_test.mp3`;
    if (curlExampleDirect)
      curlExampleDirect.textContent = `curl -X POST ${apiUrl}${authHeader} \\\n-H "Content-Type: application/json" \\\n-d '{\n  "model": "tts-1",\n  "input": "Hello, this is a direct voice test.",\n  "voice": "en-US-AriaNeural"\n}' --output direct_test.mp3`;
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
    apiTokenInput.value = currentConfig.api_token || "";
    concurrencyInput.value = currentConfig.max_concurrent_requests;
    syncApiFilteringCheckbox.checked = currentConfig.sync_api_filtering;

    const opts = currentConfig.default_cleaning_options || {};
    document
      .querySelectorAll('#cleaning-options input[type="checkbox"]')
      .forEach((checkbox) => {
        checkbox.checked = opts[checkbox.name] || false;
      });
    document.getElementById("custom-keywords").value =
      opts.custom_keywords || "";

    mappingsContainer.innerHTML = "";
    OPENAI_VOICE_ALIASES.forEach((alias) => {
      const currentMapping = currentConfig.openai_voice_map[alias];
      const wrapper = document.createElement("div");
      wrapper.className = "form-group-inline";
      wrapper.innerHTML = `<label class="settings-label">${alias}</label><select id="mapping-${alias}" class="settings-input"></select>`;
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
    updateApiExamples();
  };

  const collectConfig = () => {
    const newConfig = {
      port: parseInt(portInput.value, 10),
      api_token: apiTokenInput.value.trim(),
      max_concurrent_requests: parseInt(concurrencyInput.value, 10),
      sync_api_filtering: syncApiFilteringCheckbox.checked,
      default_cleaning_options: {},
      openai_voice_map: {},
    };
    document
      .querySelectorAll('#cleaning-options input[type="checkbox"]')
      .forEach((checkbox) => {
        newConfig.default_cleaning_options[checkbox.name] = checkbox.checked;
      });
    newConfig.default_cleaning_options["custom_keywords"] =
      document.getElementById("custom-keywords").value;
    OPENAI_VOICE_ALIASES.forEach((alias) => {
      const select = document.getElementById(`mapping-${alias}`);
      if (select) newConfig.openai_voice_map[alias] = select.value;
    });

    return newConfig;
  };

  const saveConfig = () => {
    const newConfig = collectConfig();

    fetch("/v1/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(newConfig),
    })
      .then((response) => {
        if (!response.ok) throw new Error("Failed to save config");
        return response.json();
      })
      .then((result) => {
        console.log("Config saved:", result.message);
        currentConfig = newConfig;
        showMessage(settingsFeedback, "设置已保存");
      })
      .catch((error) =>
        showMessage(settingsFeedback, "保存设置失败!", true)
      );
  };

  const handleSpeakClick = async () => {
    const text = textInput.value;
    const voice = voiceSelect.value;
    if (!text.trim()) {
      showMessage(errorMessage, "请输入文本内容。", true);
      return;
    }
    if (!voice || voiceSelect.disabled) {
      showMessage(errorMessage, "请选择一个有效的声音。", true);
      return;
    }

    setLoading(true);
    errorMessage.style.display = "none";
    audioContainer.style.display = "none";

    try {
      const headers = { "Content-Type": "application/json" };
      if (currentConfig.api_token) {
        headers["Authorization"] = `Bearer ${currentConfig.api_token}`;
      }

      const cleaningOptions = {};
      document
        .querySelectorAll('#cleaning-options input[type="checkbox"]')
        .forEach((checkbox) => {
          cleaningOptions[checkbox.name] = checkbox.checked;
        });
      cleaningOptions["custom_keywords"] =
        document.getElementById("custom-keywords").value;

      const response = await fetch("/v1/audio/speech", {
        method: "POST",
        headers: headers,
        body: JSON.stringify({
          model: "tts-1",
          input: text,
          voice: voice,
          cleaning_options: cleaningOptions,
        }),
      });

      setLoading(false);

      if (response.status >= 400) {
        const errorData = await response.json();
        throw new Error(
          errorData.error?.message ||
            `服务器返回错误 (状态码: ${response.status})`
        );
      }
      if (response.ok) {
        const blob = await response.blob();
        if (blob.size === 0) throw new Error("服务器返回了空的音频文件。");
        if (lastGeneratedBlobUrl) URL.revokeObjectURL(lastGeneratedBlobUrl);
        lastGeneratedBlobUrl = URL.createObjectURL(blob);
        audioPlayer.src = lastGeneratedBlobUrl;
        downloadLink.href = lastGeneratedBlobUrl;
        audioContainer.style.display = "flex";
        if (autoPlayCheckbox.checked) audioPlayer.play();
      } else {
        throw new Error("发生未知网络错误。");
      }
    } catch (error) {
      setLoading(false);
      showMessage(errorMessage, `语音生成失败: ${error.message}`, true);
    }
  };

  const updateCharCount = () =>
    (charCounter.textContent = `字数: ${textInput.value.length}`);

  const generateRandomToken = () => {
    const array = new Uint8Array(16);
    window.crypto.getRandomValues(array);
    return Array.from(array, (byte) => byte.toString(16).padStart(2, "0")).join(
      ""
    );
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

      textInput.addEventListener("input", updateCharCount);
      languageSelect.addEventListener("change", () =>
        updateVoiceList(languageSelect.value)
      );
      speakButton.addEventListener("click", handleSpeakClick);
      generateTokenButton.addEventListener("click", () => {
        apiTokenInput.value = generateRandomToken();
        updateApiExamples();
      });
      apiTokenInput.addEventListener("input", updateApiExamples);

      saveSettingsButton.addEventListener("click", saveConfig);

      const defaultLang = "zh-CN";
      languageSelect.value = defaultLang;
      updateVoiceList(defaultLang);
      populateSettingsForm();
    } catch (error) {
      showMessage(errorMessage, error.message, true);
    }
  };

  initialize();
});
