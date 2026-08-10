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
  const voiceFilters = document.getElementById("voice-filters");
  const voiceSearch = document.getElementById("voice-search");
  const voiceGenderFilter = document.getElementById("voice-gender-filter");
  const voiceTypeFilter = document.getElementById("voice-type-filter");
  const filterSupportsStyle = document.getElementById(
    "filter-supports-style"
  );
  const filterSupportsRole = document.getElementById("filter-supports-role");
  const filterEdgeAvailable = document.getElementById(
    "filter-edge-available"
  );
  const voiceResultCount = document.getElementById("voice-result-count");
  const voiceCapabilitySummary = document.getElementById(
    "voice-capability-summary"
  );
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
  const openaiPresetAlias = document.getElementById("openai-preset-alias");
  const saveOpenaiPresetButton = document.getElementById(
    "save-openai-preset-button"
  );
  const loadOpenaiPresetButton = document.getElementById(
    "load-openai-preset-button"
  );
  const openaiPresetSummary = document.getElementById(
    "openai-preset-summary"
  );
  const openaiPresetFeedback = document.getElementById(
    "openai-preset-feedback"
  );
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
  const customVoiceManagement = document.getElementById(
    "custom-voice-management"
  );
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

  const STYLE_LABELS = {
    angry: "愤怒",
    calm: "平静",
    cheerful: "开朗",
    conversation: "对话",
    empathetic: "同理心",
    excited: "兴奋",
    fearful: "害怕",
    friendly: "友好",
    gentle: "温柔",
    hopeful: "希望",
    "narration-professional": "专业旁白",
    "narration-relaxed": "轻松旁白",
    newscast: "新闻播报",
    sad: "悲伤",
    serious: "严肃",
    shouting: "呐喊",
    whispering: "耳语",
  };
  const ROLE_LABELS = {
    Boy: "男孩",
    Girl: "女孩",
    Narrator: "旁白",
    YoungAdultFemale: "年轻女性",
    YoungAdultMale: "年轻男性",
    OlderAdultFemale: "成年女性",
    OlderAdultMale: "成年男性",
    SeniorFemale: "老年女性",
    SeniorMale: "老年男性",
  };

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
      curlExampleOpenAI.textContent = `curl -X POST ${apiUrl}${authHeader} \\\n-H "Content-Type: application/json" \\\n-d '{\n  "model": "tts-1",\n  "input": "你好，这将自动使用 WebUI 中保存的 shimmer 完整音色预设。",\n  "voice": "shimmer"\n}' --output openai_test.mp3`;
    if (curlExampleDirect)
      curlExampleDirect.textContent = `curl -X POST ${apiUrl}${authHeader} \\\n-H "Content-Type: application/json" \\\n-d '{\n  "model": "tts-1",\n  "input": "这是一段带角色和语气强度的测试。",\n  "voice": "zh-CN-XiaomoNeural",\n  "style": "cheerful",\n  "role": "YoungAdultFemale",\n  "style_degree": 1.35,\n  "speed": 1.05,\n  "pitch": 1.0,\n  "strict_capabilities": true\n}' --output direct_test.mp3`;
  };

  // 获取当前声音配置
  const getVoiceConfig = () => {
    const selectedLocale = languageSelect.value;
    const selectedVoice =
      voiceSelect.value ||
      (selectedLocale === "custom" ? customVoiceName.value.trim() : "");
    return {
      voice: selectedVoice || "zh-CN-XiaoxiaoNeural",
      style: voiceStyle.value || "general",
      role: voiceRole.value || "",
      styleDegree: parseFloat(styleDegree.value) || 1.0,
      speed: parseFloat(speed.value) || 1.0,
      pitch: parseFloat(pitch.value) || 1.0,
    };
  };

  const getCleaningOptions = () => {
    const cleaningOptions = {};
    document
      .querySelectorAll('#cleaning-options input[type="checkbox"]')
      .forEach((checkbox) => {
        cleaningOptions[checkbox.name] = checkbox.checked;
      });
    cleaningOptions.custom_keywords =
      document.getElementById("custom-keywords").value;
    return cleaningOptions;
  };

  const getOpenaiPreset = (alias) => {
    const preset = currentConfig.openai_voice_presets?.[alias];
    if (preset && typeof preset === "object") return preset;
    const legacyVoice = currentConfig.openai_voice_map?.[alias];
    return legacyVoice ? { voice: legacyVoice } : null;
  };

  const formatPresetSummary = (alias, preset) => {
    if (!preset?.voice) return `${alias} 尚未配置。`;
    const styleLabel =
      !preset.style || preset.style === "general"
        ? "默认风格"
        : STYLE_LABELS[preset.style] || preset.style;
    const roleLabel = preset.role
      ? ROLE_LABELS[preset.role] || preset.role
      : "默认角色";
    const speedText = Number(preset.speed ?? 1).toFixed(2);
    const pitchText = Number(preset.pitch ?? 1).toFixed(2);
    const degreeText = Number(preset.style_degree ?? 1).toFixed(2);
    const filterText = preset.cleaning_options
      ? "已保存文本过滤"
      : "使用全局文本过滤";
    return `${alias} → ${preset.voice} · ${styleLabel} · ${roleLabel} · 强度 ${degreeText} · 语速 ${speedText} · 音调 ${pitchText} · ${filterText}`;
  };

  const refreshOpenaiPresetSummary = () => {
    const alias = openaiPresetAlias.value;
    const preset = getOpenaiPreset(alias);
    openaiPresetSummary.textContent = formatPresetSummary(alias, preset);
    loadOpenaiPresetButton.disabled = !preset?.voice;
  };

  const populateCapabilitySelect = (
    select,
    values,
    defaultLabel,
    labels = {}
  ) => {
    const previousValue = select.value;
    select.innerHTML = "";
    const defaultOption = document.createElement("option");
    defaultOption.value = "";
    defaultOption.textContent = defaultLabel;
    select.appendChild(defaultOption);
    values.forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = labels[value] ? `${labels[value]} (${value})` : value;
      select.appendChild(option);
    });
    select.value = values.includes(previousValue) ? previousValue : "";
    select.disabled = values.length === 0;
  };

  const updateVoiceCapabilities = () => {
    const isCustom = languageSelect.value === "custom";
    const selectedVoice = allVoices.find(
      (voice) => voice.name === voiceSelect.value
    );
    customVoiceConfig.classList.toggle(
      "hidden",
      !isCustom && !selectedVoice
    );
    customVoiceManagement.classList.toggle("hidden", !isCustom);

    const allStyles = [
      ...new Set(allVoices.flatMap((voice) => voice.styles || [])),
    ].sort();
    const allRoles = [
      ...new Set(allVoices.flatMap((voice) => voice.roles || [])),
    ].sort();
    const styles = isCustom ? allStyles : selectedVoice?.styles || [];
    const roles = isCustom ? allRoles : selectedVoice?.roles || [];
    populateCapabilitySelect(voiceStyle, styles, "默认风格", STYLE_LABELS);
    populateCapabilitySelect(voiceRole, roles, "默认角色", ROLE_LABELS);
    styleDegree.disabled = voiceStyle.disabled || !voiceStyle.value;

    if (!isCustom && selectedVoice) {
      const source = selectedVoice.edge_available
        ? "Edge 清单 + Azure 文档"
        : "Azure 文档（实际可用性取决于微软端点/区域）";
      const styleText = selectedVoice.styles.length
        ? `情绪 ${selectedVoice.styles.length} 种`
        : "不支持情绪";
      const roleText = selectedVoice.roles.length
        ? `角色 ${selectedVoice.roles.length} 种`
        : "不支持角色";
      voiceCapabilitySummary.textContent = `${selectedVoice.gender} · ${selectedVoice.voice_type} · ${styleText} · ${roleText} · ${source}`;
      voiceCapabilitySummary.classList.remove("hidden");
    } else if (isCustom) {
      voiceCapabilitySummary.textContent =
        "自定义音色能力未知；请选择微软实际支持的情绪和角色参数。";
      voiceCapabilitySummary.classList.remove("hidden");
    } else {
      voiceCapabilitySummary.classList.add("hidden");
    }
  };

  const updateVoiceList = (selectedLocale) => {
    const previousVoice = voiceSelect.value;
    voiceSelect.innerHTML = "";

    // 如果是自定义配置，显示自定义面板
    if (selectedLocale === "custom") {
      customVoiceConfig.classList.remove("hidden");
      customVoiceManagement.classList.remove("hidden");
      voiceFilters.classList.add("hidden");

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
      customVoiceManagement.classList.add("hidden");
      voiceFilters.classList.toggle("hidden", !selectedLocale);
    }

    let filteredVoices = allVoices.filter((v) => v.locale === selectedLocale);
    if (voiceGenderFilter.value) {
      filteredVoices = filteredVoices.filter(
        (voice) => voice.gender === voiceGenderFilter.value
      );
    }
    if (voiceTypeFilter.value) {
      filteredVoices = filteredVoices.filter(
        (voice) => voice.voice_type === voiceTypeFilter.value
      );
    }
    if (filterSupportsStyle.checked) {
      filteredVoices = filteredVoices.filter((voice) => voice.supports_style);
    }
    if (filterSupportsRole.checked) {
      filteredVoices = filteredVoices.filter((voice) => voice.supports_role);
    }
    if (filterEdgeAvailable.checked) {
      filteredVoices = filteredVoices.filter((voice) => voice.edge_available);
    }
    const query = voiceSearch.value.trim().toLowerCase();
    if (query) {
      filteredVoices = filteredVoices.filter((voice) =>
        [
          voice.name,
          voice.short_name,
          voice.voice_type,
          ...(voice.styles || []),
          ...(voice.roles || []),
        ]
          .join(" ")
          .toLowerCase()
          .includes(query)
      );
    }

    // 添加标准音色
    filteredVoices.forEach((voice) => {
      const option = document.createElement("option");
      option.value = voice.name;
      const capabilities = [
        voice.supports_style ? "情绪" : "",
        voice.supports_role ? "角色" : "",
      ]
        .filter(Boolean)
        .join("+");
      option.textContent = `${voice.short_name} · ${voice.gender} · ${voice.voice_type}${capabilities ? ` · ${capabilities}` : ""}`;
      voiceSelect.appendChild(option);
    });
    voiceResultCount.textContent = selectedLocale
      ? `显示 ${filteredVoices.length} 个音色`
      : "";

    // 注意：自定义音色只在"自定义音色配置"模式下显示，不在普通语言选择中显示

    if (voiceSelect.children.length === 0) {
      voiceSelect.innerHTML = "<option>无可用声音</option>";
      voiceSelect.disabled = true;
      updateVoiceCapabilities();
      return;
    }

    voiceSelect.disabled = false;
    if ([...voiceSelect.options].some((option) => option.value === previousVoice)) {
      voiceSelect.value = previousVoice;
    }
    updateVoiceCapabilities();
  };

  const applyOpenaiPresetToForm = (alias) => {
    const preset = getOpenaiPreset(alias);
    if (!preset?.voice) {
      showMessage(openaiPresetFeedback, `${alias} 尚未配置。`, true);
      return;
    }

    const catalogVoice = allVoices.find((voice) => voice.name === preset.voice);
    languageSelect.value = catalogVoice?.locale || "custom";
    updateVoiceList(languageSelect.value);
    if ([...voiceSelect.options].some((option) => option.value === preset.voice)) {
      voiceSelect.value = preset.voice;
    } else if (languageSelect.value === "custom") {
      customVoiceName.value = preset.voice;
    }
    updateVoiceCapabilities();

    voiceStyle.value =
      preset.style && preset.style !== "general" ? preset.style : "";
    voiceRole.value = preset.role || "";
    styleDegree.value = String(preset.style_degree ?? 1);
    styleDegreeValue.textContent = Number(styleDegree.value).toFixed(2);
    styleDegree.disabled = !voiceStyle.value;
    speed.value = String(preset.speed ?? 1);
    speedValue.textContent = Number(speed.value).toFixed(2);
    pitch.value = String(preset.pitch ?? 1);
    pitchValue.textContent = Number(pitch.value).toFixed(2);

    if (preset.cleaning_options) {
      document
        .querySelectorAll('#cleaning-options input[type="checkbox"]')
        .forEach((checkbox) => {
          checkbox.checked = Boolean(preset.cleaning_options[checkbox.name]);
        });
      document.getElementById("custom-keywords").value =
        preset.cleaning_options.custom_keywords || "";
    }
    showMessage(openaiPresetFeedback, `已载入 ${alias} 的完整配置。`);
  };

  const renderOpenaiMappings = () => {
    mappingsContainer.innerHTML = "";
    OPENAI_VOICE_ALIASES.forEach((alias) => {
      const preset = getOpenaiPreset(alias);
      const wrapper = document.createElement("div");
      wrapper.className =
        "flex flex-col md:flex-row md:items-center gap-2 p-2 bg-gray-50 dark:bg-gray-700 rounded-xl";

      const aliasLabel = document.createElement("span");
      aliasLabel.className = "md:w-20 font-semibold";
      aliasLabel.textContent = alias;

      const summary = document.createElement("span");
      summary.className = "flex-1 text-sm break-all";
      summary.textContent = formatPresetSummary(alias, preset);

      const loadButton = document.createElement("button");
      loadButton.type = "button";
      loadButton.className =
        "bg-gray-500 hover:bg-gray-600 text-white px-3 py-1 rounded-lg text-sm";
      loadButton.textContent = "载入试听区";
      loadButton.disabled = !preset?.voice;
      loadButton.addEventListener("click", () => {
        openaiPresetAlias.value = alias;
        refreshOpenaiPresetSummary();
        applyOpenaiPresetToForm(alias);
      });

      wrapper.append(aliasLabel, summary, loadButton);
      mappingsContainer.appendChild(wrapper);
    });
  };

  const saveCurrentAsOpenaiPreset = async () => {
    const alias = openaiPresetAlias.value;
    const voiceConfig = getVoiceConfig();
    if (!voiceConfig.voice || voiceSelect.disabled) {
      showMessage(openaiPresetFeedback, "请先选择并试听一个有效音色。", true);
      return;
    }

    saveOpenaiPresetButton.disabled = true;
    try {
      const response = await fetch(
        `/v1/openai-voice-presets/${encodeURIComponent(alias)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            voice: voiceConfig.voice,
            style: voiceConfig.style,
            role: voiceConfig.role,
            style_degree: voiceConfig.styleDegree,
            speed: voiceConfig.speed,
            pitch: voiceConfig.pitch,
            cleaning_options: getCleaningOptions(),
          }),
        }
      );
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "保存失败");

      currentConfig.openai_voice_presets ||= {};
      currentConfig.openai_voice_map ||= {};
      currentConfig.openai_voice_presets[alias] = result.preset;
      currentConfig.openai_voice_map[alias] = result.preset.voice;
      refreshOpenaiPresetSummary();
      renderOpenaiMappings();
      showMessage(
        openaiPresetFeedback,
        `${alias} 已映射到当前试听配置，标准 OpenAI API 调用将自动应用。`
      );
    } catch (error) {
      showMessage(openaiPresetFeedback, `保存失败：${error.message}`, true);
    } finally {
      saveOpenaiPresetButton.disabled = false;
    }
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

    renderOpenaiMappings();
    refreshOpenaiPresetSummary();

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
      openai_voice_map: { ...(currentConfig.openai_voice_map || {}) },
      openai_voice_presets: {
        ...(currentConfig.openai_voice_presets || {}),
      },
    };
    document
      .querySelectorAll('#cleaning-options input[type="checkbox"]')
      .forEach((checkbox) => {
        newConfig.default_cleaning_options[checkbox.name] = checkbox.checked;
      });
    newConfig.default_cleaning_options["custom_keywords"] =
      document.getElementById("custom-keywords").value;
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
        currentConfig = { ...currentConfig, ...newConfig };
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

      const cleaningOptions = getCleaningOptions();

      const requestBody = {
        model: "tts-1",
        input: text,
        voice: voiceConfig.voice,
        speed: voiceConfig.speed,
        pitch: voiceConfig.pitch,
        style_degree: voiceConfig.styleDegree,
        strict_capabilities: languageSelect.value !== "custom",
        cleaning_options: cleaningOptions,
        stream: streamPlayCheckbox.checked && mediaSourceSupported,
      };

      if (voiceConfig.style && voiceConfig.style !== "general") {
        requestBody.style = voiceConfig.style;
      }
      if (voiceConfig.role) {
        requestBody.role = voiceConfig.role;
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

      const voiceTypes = [
        ...new Set(allVoices.map((voice) => voice.voice_type).filter(Boolean)),
      ];
      voiceTypes.forEach((voiceType) => {
        const option = document.createElement("option");
        option.value = voiceType;
        option.textContent = voiceType;
        voiceTypeFilter.appendChild(option);
      });

      textInput.addEventListener("input", updateCharCount);
      languageSelect.addEventListener("change", () =>
        updateVoiceList(languageSelect.value)
      );

      // 声音选择变化事件 - 当选择自定义音色时，自动填入输入框
      voiceSelect.addEventListener("change", () => {
        if (languageSelect.value === "custom" && voiceSelect.value) {
          customVoiceName.value = voiceSelect.value;
        }
        updateVoiceCapabilities();
      });
      [voiceGenderFilter, voiceTypeFilter].forEach((element) =>
        element.addEventListener("change", () =>
          updateVoiceList(languageSelect.value)
        )
      );
      [filterSupportsStyle, filterSupportsRole, filterEdgeAvailable].forEach(
        (element) =>
          element.addEventListener("change", () =>
            updateVoiceList(languageSelect.value)
          )
      );
      voiceSearch.addEventListener("input", () =>
        updateVoiceList(languageSelect.value)
      );
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
      openaiPresetAlias.addEventListener("change", refreshOpenaiPresetSummary);
      saveOpenaiPresetButton.addEventListener(
        "click",
        saveCurrentAsOpenaiPreset
      );
      loadOpenaiPresetButton.addEventListener("click", () =>
        applyOpenaiPresetToForm(openaiPresetAlias.value)
      );

      // 风格强度滑块事件监听器
      styleDegree.addEventListener("input", () => {
        styleDegreeValue.textContent = parseFloat(styleDegree.value).toFixed(2);
      });
      voiceStyle.addEventListener("change", () => {
        styleDegree.disabled = !voiceStyle.value;
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
