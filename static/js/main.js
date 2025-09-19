document.addEventListener("DOMContentLoaded", () => {
  // 1. 全局变量
  let allVoices = [];
  let currentConfig = {};
  let lastGeneratedBlobUrl = null;
  let progressInterval = null;
  let totalChunks = 0;
  let completedChunks = 0;
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
  const saveFilteringButton = document.getElementById("save-filtering-button");
  const filteringFeedback = document.getElementById("filtering-feedback");
  const charCounter = document.getElementById("char-counter");
  const autoPlayCheckbox = document.getElementById("auto-play");
  const streamPlayCheckbox = document.getElementById("stream-play");
  const concurrencyInput = document.getElementById("concurrency-input");
  const chunkSizeInput = document.getElementById("chunk-size-input");
  const syncChunksInput = document.getElementById("sync-chunks-input");
  const progressContainer = document.getElementById("progress-container");
  const progressBar = document.getElementById("progress-bar");
  const progressText = document.getElementById("progress-text");
  const cleaningOptionsPanel = document.getElementById(
    "cleaning-options-panel"
  );
  const syncApiFilteringCheckbox =
    document.getElementById("sync-api-filtering");

  // 自定义声音配置元素
  const customVoiceConfig = document.getElementById("custom-voice-config");
  const customVoiceName = document.getElementById("custom-voice-name");
  const voiceStyle = document.getElementById("voice-style");
  const customVoiceRemark = document.getElementById("custom-voice-remark");
  const voiceRole = document.getElementById("voice-role");
  const styleDegree = document.getElementById("style-degree");
  const styleDegreeValue = document.getElementById("style-degree-value");
  const speed = document.getElementById("speed");
  const speedValue = document.getElementById("speed-value");
  const pitch = document.getElementById("pitch");
  const pitchValue = document.getElementById("pitch-value");
  const addCustomVoiceBtn = document.getElementById("add-custom-voice-btn");
  const deleteCustomVoiceBtn = document.getElementById(
    "delete-custom-voice-btn"
  );
  const customVoiceMappingsContainer = document.getElementById(
    "custom-voice-mappings-container"
  );

  const mediaSourceSupported =
    typeof window.MediaSource !== "undefined" &&
    !/iphone|ipad|ipod/i.test(navigator.userAgent.toLowerCase());
  if (!mediaSourceSupported) {
    streamPlayCheckbox.checked = false;
    streamPlayCheckbox.disabled = true;
  }

  // 3. 功能函数
  const showMessage = (element, message, isError = false) => {
    element.textContent = message;
    element.className = isError ? "feedback error" : "feedback success";
    element.style.display = "block";
    setTimeout(() => {
      element.style.display = "none";
    }, 3000);
  };

  const setLoading = (isLoading, chunkProgress = null) => {
    speakButton.disabled = isLoading;
    const buttonText = speakButton.querySelector(".button-text");

    if (isLoading) {
      progressContainer.style.display = "flex";
      completedChunks = 0;

      if (chunkProgress) {
        // 基于实际块完成情况的进度
        totalChunks = chunkProgress.total;
        completedChunks = chunkProgress.completed;
        const progress =
          totalChunks > 0
            ? Math.round((completedChunks / totalChunks) * 100)
            : 0;
        progressBar.style.width = `${progress}%`;
        progressText.textContent = `${progress}%`;
      } else {
        // 传统的模拟进度条（作为后备）
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
      }
    } else {
      if (progressInterval) clearInterval(progressInterval);
      progressBar.style.width = "100%";
      progressText.textContent = "100%";
      setTimeout(() => {
        progressContainer.style.display = "none";
      }, 1000);
      // 重置计数器
      totalChunks = 0;
      completedChunks = 0;
    }
  };

  // 新增：更新基于块完成情况的进度
  const updateChunkProgress = (completed, total) => {
    completedChunks = completed;
    totalChunks = total;
    if (totalChunks > 0) {
      const progress = Math.round((completedChunks / totalChunks) * 100);
      progressBar.style.width = `${progress}%`;
      progressText.textContent = `${progress}%`;
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

  // 获取当前声音配置
  const getVoiceConfig = () => {
    const selectedLocale = languageSelect.value;

    if (selectedLocale === "custom") {
      // 优先使用选择声音下拉框中的值，如果没有选择则使用输入框中的值
      const selectedVoice = voiceSelect.value || customVoiceName.value.trim();
      return {
        voice: selectedVoice || "zh-CN-XiaoxiaoNeural",
        style: voiceStyle.value || "general",
        role: voiceRole.value || "",
        styleDegree: parseFloat(styleDegree.value) || 1.0,
        speed: parseFloat(speed.value) || 1.0,
        pitch: parseFloat(pitch.value) || 1.0,
      };
    } else {
      return {
        voice: voiceSelect.value,
        style: "general",
        role: "",
        styleDegree: 1.0,
        speed: parseFloat(speed.value) || 1.0,
        pitch: parseFloat(pitch.value) || 1.0,
      };
    }
  };

  const updateVoiceList = (selectedLocale) => {
    voiceSelect.innerHTML = "";

    // 如果是自定义配置，显示自定义面板
    if (selectedLocale === "custom") {
      customVoiceConfig.classList.remove("hidden");

      // 添加自定义音色到下拉框
      const customVoices = currentConfig.custom_voices || {};
      Object.keys(customVoices).forEach((voiceName) => {
        const option = document.createElement("option");
        option.value = voiceName;
        const display = customVoices[voiceName] || voiceName;
        option.textContent = `${display} (自定义)`;
        voiceSelect.appendChild(option);
      });

      voiceSelect.disabled = false;
    } else {
      customVoiceConfig.classList.add("hidden");
    }

    const filteredVoices = allVoices.filter((v) => v.locale === selectedLocale);

    // 添加标准音色
    filteredVoices.forEach((voice) => {
      const option = document.createElement("option");
      option.value = voice.name;
      option.textContent = `${voice.short_name} (${voice.gender})`;
      voiceSelect.appendChild(option);
    });

    // 注意：自定义音色只在"自定义音色配置"模式下显示，不在普通语言选择中显示

    if (voiceSelect.children.length === 0) {
      voiceSelect.innerHTML = "<option>无可用声音</option>";
      voiceSelect.disabled = true;
      return;
    }

    voiceSelect.disabled = false;
  };

  const populateSettingsForm = () => {
    portInput.value = currentConfig.port;
    apiTokenInput.value = currentConfig.api_token || "";
    concurrencyInput.value = currentConfig.max_concurrent_requests;
    chunkSizeInput.value = currentConfig.chunk_size;
    syncChunksInput.value = currentConfig.sync_chunks;
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
      wrapper.className = "flex items-center gap-2";
      wrapper.innerHTML = `<span class="w-28 text-right font-semibold">${alias}</span><select id="mapping-${alias}" class="flex-1 p-2 border rounded-xl dark:bg-gray-700 dark:border-gray-600"></select>`;
      const select = wrapper.querySelector("select");

      // 添加标准音色选项
      allVoices.forEach((voice) => {
        const option = document.createElement("option");
        option.value = voice.name;
        option.textContent = `${voice.name} (${voice.gender})`;
        if (voice.name === currentMapping) option.selected = true;
        select.appendChild(option);
      });

      // 添加自定义音色选项
      const customVoices = currentConfig.custom_voices || {};
      Object.keys(customVoices).forEach((voiceName) => {
        const option = document.createElement("option");
        option.value = voiceName;
        option.textContent = `${voiceName} (自定义)`;
        if (voiceName === currentMapping) option.selected = true;
        select.appendChild(option);
      });

      mappingsContainer.appendChild(wrapper);
    });

    // 加载自定义音色映射
    loadCustomVoiceMappings();
    updateApiExamples();
    // 更新当前语言下的音色列表
    updateVoiceList(languageSelect.value);
  };

  const loadCustomVoiceMappings = () => {
    customVoiceMappingsContainer.innerHTML = "";
    const customVoices = currentConfig.custom_voices || {};

    if (Object.keys(customVoices).length === 0) {
      customVoiceMappingsContainer.innerHTML =
        '<p class="text-gray-500 text-sm">暂无自定义音色</p>';
      return;
    }

    Object.entries(customVoices).forEach(([voiceName, displayName]) => {
      const wrapper = document.createElement("div");
      wrapper.className =
        "flex items-center gap-2 p-2 bg-gray-50 dark:bg-gray-700 rounded";
      wrapper.innerHTML = `
        <span class="flex-1 text-sm">${displayName || voiceName}</span>
        <button 
          class="delete-custom-voice-btn bg-red-500 hover:bg-red-600 text-white px-2 py-1 rounded text-xs"
          data-voice-name="${voiceName}"
        >
          删除
        </button>
      `;
      customVoiceMappingsContainer.appendChild(wrapper);
    });
  };

  const clearCustomVoiceConfig = () => {
    // 清空自定义音色名称输入框
    customVoiceName.value = "";

    // 重置所有配置参数为默认值
    voiceStyle.value = "";
    voiceRole.value = "";
    styleDegree.value = "1.0";
    styleDegreeValue.textContent = "1.0";
    speed.value = "1.0";
    speedValue.textContent = "1.00";
    pitch.value = "1.0";
    pitchValue.textContent = "1.00";
  };

  const addCustomVoice = async () => {
    const voiceName = customVoiceName.value.trim();
    const remark = customVoiceRemark.value.trim();
    if (!voiceName) {
      showMessage(errorMessage, "请输入音色名称", true);
      return;
    }

    try {
      const response = await fetch("/v1/custom-voices", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          voice_name: voiceName,
          display_name: remark || voiceName,
        }),
      });

      if (response.ok) {
        const result = await response.json();
        showMessage(errorMessage, "自定义音色添加成功！", false);
        customVoiceName.value = "";
        customVoiceRemark.value = "";
        // 重新加载配置和映射
        await loadConfig();
        populateSettingsForm();
        // 更新音色列表（包括自定义音色）
        updateVoiceList(languageSelect.value);
      } else {
        const errorData = await response.json();
        throw new Error(errorData.error || "添加失败");
      }
    } catch (error) {
      showMessage(errorMessage, `添加自定义音色失败: ${error.message}`, true);
    }
  };

  const deleteCustomVoice = async (voiceName) => {
    if (!confirm(`确定要删除自定义音色 "${voiceName}" 吗？`)) {
      return;
    }

    try {
      const response = await fetch(
        `/v1/custom-voices/${encodeURIComponent(voiceName)}`,
        {
          method: "DELETE",
        }
      );

      if (response.ok) {
        showMessage(errorMessage, "自定义音色删除成功！", false);
        // 重新加载配置和映射
        await loadConfig();
        populateSettingsForm();
        // 更新音色列表（包括自定义音色）
        updateVoiceList(languageSelect.value);
      } else {
        const errorData = await response.json();
        throw new Error(errorData.error || "删除失败");
      }
    } catch (error) {
      showMessage(errorMessage, `删除自定义音色失败: ${error.message}`, true);
    }
  };

  const loadConfig = async () => {
    try {
      const response = await fetch("/v1/config");
      if (response.ok) {
        currentConfig = await response.json();
      }
    } catch (error) {
      console.error("Error loading config:", error);
    }
  };

  const collectConfig = () => {
    const newConfig = {
      port: parseInt(portInput.value, 10),
      api_token: apiTokenInput.value.trim(),
      chunk_size: parseInt(chunkSizeInput.value, 10),
      sync_chunks: parseInt(syncChunksInput.value, 10),
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

  const saveConfig = (feedbackTarget) => {
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
        showMessage(feedbackTarget, "设置已保存");
      })
      .catch((error) => {
        console.error("Error saving config:", error);
        showMessage(feedbackTarget, "保存设置失败!", true);
      });
  };

  const handleSpeakClick = async () => {
    const text = textInput.value;
    if (!text.trim()) {
      showMessage(errorMessage, "请输入文本内容。", true);
      return;
    }

    const voiceConfig = getVoiceConfig();
    if (
      !voiceConfig.voice ||
      (languageSelect.value !== "custom" && voiceSelect.disabled)
    ) {
      showMessage(errorMessage, "请选择一个有效的声音。", true);
      return;
    }

    setLoading(true);
    errorMessage.style.display = "none";
    audioContainer.style.display = "none";
    downloadLink.style.display =
      streamPlayCheckbox.checked && mediaSourceSupported ? "none" : "";

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

      const requestBody = {
        model: "tts-1",
        input: text,
        voice: voiceConfig.voice,
        speed: voiceConfig.speed,
        pitch: voiceConfig.pitch,
        cleaning_options: cleaningOptions,
        stream: streamPlayCheckbox.checked && mediaSourceSupported,
      };

      // 添加自定义声音参数
      if (languageSelect.value === "custom") {
        requestBody.style = voiceConfig.style;
        requestBody.role = voiceConfig.role;
        requestBody.styleDegree = voiceConfig.styleDegree;
      }

      const response = await fetch("/v1/audio/speech", {
        method: "POST",
        headers: headers,
        body: JSON.stringify(requestBody),
      });

      if (response.status >= 400) {
        const errorData = await response.json();
        throw new Error(
          errorData.error?.message ||
            `服务器返回错误 (状态码: ${response.status})`
        );
      }
      if (response.ok) {
        audioContainer.style.display = "flex";
        if (streamPlayCheckbox.checked && mediaSourceSupported) {
          const mediaSource = new MediaSource();
          if (lastGeneratedBlobUrl) URL.revokeObjectURL(lastGeneratedBlobUrl);
          lastGeneratedBlobUrl = URL.createObjectURL(mediaSource);
          audioPlayer.src = lastGeneratedBlobUrl;
          audioPlayer.play();

          // 流式播放进度跟踪
          let receivedChunks = 0;
          const estimatedTotalChunks = Math.ceil(text.length / 300); // 基于文本长度估算
          let streamTimeout = null;
          let progressStartTime = Date.now();

          mediaSource.addEventListener("sourceopen", () => {
            const sourceBuffer = mediaSource.addSourceBuffer("audio/mpeg");
            const reader = response.body.getReader();

            // 设置流式播放超时机制（基于文本长度动态调整）
            const timeoutDuration = Math.max(30000, text.length * 10); // 最少30秒，每字符10ms
            streamTimeout = setTimeout(() => {
              console.warn("流式播放超时，强制完成");
              setLoading(false);
            }, timeoutDuration);

            const pump = () => {
              reader
                .read()
                .then(({ done, value }) => {
                  if (done) {
                    const finalize = () => {
                      if (streamTimeout) clearTimeout(streamTimeout);
                      mediaSource.endOfStream();
                      setLoading(false);
                    };
                    if (sourceBuffer.updating) {
                      sourceBuffer.addEventListener("updateend", finalize, {
                        once: true,
                      });
                    } else {
                      finalize();
                    }
                    return;
                  }

                  // 智能进度更新
                  receivedChunks++;
                  const elapsedTime = Date.now() - progressStartTime;

                  // 基于接收到的块数和时间估算进度
                  let progress = Math.min(
                    95,
                    Math.round((receivedChunks / estimatedTotalChunks) * 100)
                  );

                  // 如果时间较长但进度较低，使用时间估算作为后备
                  if (elapsedTime > 10000 && progress < 50) {
                    // 10秒后如果进度还很低
                    const timeBasedProgress = Math.min(
                      90,
                      Math.round((elapsedTime / (text.length * 0.02)) * 100)
                    ); // 每字符20ms估算
                    progress = Math.max(progress, timeBasedProgress);
                  }

                  progressBar.style.width = `${progress}%`;
                  progressText.textContent = `${progress}%`;

                  sourceBuffer.appendBuffer(value);
                  if (sourceBuffer.updating) {
                    sourceBuffer.addEventListener("updateend", pump, {
                      once: true,
                    });
                  } else {
                    pump();
                  }
                })
                .catch((error) => {
                  console.error("流式播放读取错误:", error);
                  if (streamTimeout) clearTimeout(streamTimeout);
                  setLoading(false);
                });
            };
            pump();
          });
        } else {
          const blob = await response.blob();
          if (blob.size === 0) throw new Error("服务器返回了空的音频文件。");
          if (lastGeneratedBlobUrl) URL.revokeObjectURL(lastGeneratedBlobUrl);
          lastGeneratedBlobUrl = URL.createObjectURL(blob);
          audioPlayer.src = lastGeneratedBlobUrl;
          downloadLink.href = lastGeneratedBlobUrl;
          if (autoPlayCheckbox.checked) audioPlayer.play();
          setLoading(false);
        }
      } else {
        throw new Error("发生未知网络错误。");
      }
    } catch (error) {
      setLoading(false);
      showMessage(errorMessage, `语音生成失败: ${error.message}`, true);
    }
  };

  const updateCharCount = () => {
    const lang = window.currentLang || "zh";
    const label =
      (window.translations && window.translations[lang]?.char_count) || "字数:";
    charCounter.textContent = `${label} ${textInput.value.length}`;
  };

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

      // 声音选择变化事件 - 当选择自定义音色时，自动填入输入框
      voiceSelect.addEventListener("change", () => {
        if (languageSelect.value === "custom" && voiceSelect.value) {
          customVoiceName.value = voiceSelect.value;
        }
      });
      speakButton.addEventListener("click", handleSpeakClick);
      generateTokenButton.addEventListener("click", () => {
        apiTokenInput.value = generateRandomToken();
        updateApiExamples();
      });
      apiTokenInput.addEventListener("input", updateApiExamples);
      autoPlayCheckbox.addEventListener("change", () => {
        if (autoPlayCheckbox.checked) {
          streamPlayCheckbox.checked = false;
          downloadLink.style.display = "";
        }
      });
      streamPlayCheckbox.addEventListener("change", () => {
        if (streamPlayCheckbox.checked && !mediaSourceSupported) {
          streamPlayCheckbox.checked = false;
          return;
        }
        if (streamPlayCheckbox.checked) {
          autoPlayCheckbox.checked = false;
          downloadLink.style.display = "none";
        } else {
          downloadLink.style.display = "";
        }
      });
      saveSettingsButton.addEventListener("click", () =>
        saveConfig(settingsFeedback)
      );
      saveFilteringButton.addEventListener("click", () =>
        saveConfig(filteringFeedback)
      );

      // 风格强度滑块事件监听器
      styleDegree.addEventListener("input", () => {
        styleDegreeValue.textContent = parseFloat(styleDegree.value).toFixed(2);
      });

      // 语速滑块事件监听器
      speed.addEventListener("input", () => {
        speedValue.textContent = parseFloat(speed.value).toFixed(2);
      });

      // 音调滑块事件监听器
      pitch.addEventListener("input", () => {
        pitchValue.textContent = parseFloat(pitch.value).toFixed(2);
      });

      // 添加自定义音色按钮事件监听器
      addCustomVoiceBtn.addEventListener("click", addCustomVoice);

      // 自定义音色名称输入框回车事件
      customVoiceName.addEventListener("keypress", (e) => {
        if (e.key === "Enter") {
          addCustomVoice();
        }
      });

      // 删除自定义音色按钮事件监听器
      deleteCustomVoiceBtn.addEventListener("click", () => {
        const voiceName = customVoiceName.value.trim();
        if (voiceName) {
          deleteCustomVoice(voiceName);
          // 清空自定义音色配置
          clearCustomVoiceConfig();
        } else {
          showMessage(errorMessage, "请先输入要删除的音色名称", true);
        }
      });

      // 删除自定义音色按钮事件监听器（使用事件委托）
      customVoiceMappingsContainer.addEventListener("click", (e) => {
        if (e.target.classList.contains("delete-custom-voice-btn")) {
          const voiceName = e.target.getAttribute("data-voice-name");
          deleteCustomVoice(voiceName);
          // 清空自定义音色配置
          clearCustomVoiceConfig();
        }
      });

      const defaultLang = "zh-CN";
      languageSelect.value = defaultLang;
      populateSettingsForm();
      // 在配置完全加载后再更新音色列表
      updateVoiceList(defaultLang);
    } catch (error) {
      showMessage(errorMessage, error.message, true);
    }
  };

  initialize();
});
