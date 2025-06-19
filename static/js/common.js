function initCommon() {
  const translations = {
    zh: {
      title: '本地多语言 TTS 服务',
      desc: '基于 Microsoft Edge TTS 引擎，支持多种语言和音色。',
      input_label: '输入文本:',
      input_placeholder: '在这里输入要转换为语音的文本...',
      char_count: '字数:',
      filter_options: '文本过滤选项',
      api_sync_note: '对所有 API 调用应用以下过滤规则。',
      api_sync_save: '修改后需点击下方保存按钮才会生效',
      remove_markdown: '移除 Markdown 语法',
      remove_emoji: '移除表情符号',
      remove_url: '移除 URL 链接',
      merge_line: '合并为单行文本',
      custom_keywords: '自定义移除关键词 (用英文逗号,分隔):',
      custom_placeholder: '例如：附注,图表,免责声明',
      save_filter: '保存过滤设置',
      select_lang: '选择语言:',
      select_lang_option: '-- 选择语言 --',
      select_voice: '选择声音:',
      choose_lang_first: '请先选择语言',
      auto_play: '生成后自动播放',
      gen_speech: '🎵 生成语音',
      download_audio: '下载音频',
      service_settings: '服务设置',
      service_port: '服务端口:',
      concurrency: '并发数:',
      chunk_size: '分块大小:',
      port_hint: '端口修改需重启服务。并发数保存后立即对新请求生效。',
      api_token: 'API 密钥 (留空则不验证):',
      empty_api_hint: '留空则任何人都可以调用 API',
      gen_token: '生成随机密钥',
      openai_map: 'OpenAI 音色映射',
      save_settings: '保存设置',
      api_guide: 'API 配置指引',
      api_endpoint: 'API 端点',
      api_post: '所有请求都使用 POST 方法发送到以下地址:',
      guide_openai: '1. OpenAI 兼容格式 (推荐)',
      openai_tip: '使用 OpenAI 的标准音色名 (`shimmer`, `alloy` 等) 调用，服务会自动映射到您在上面设置中选择的音色。',
      generating_example: '正在生成示例...',
      guide_direct: '2. EdgeTTS 直接格式',
      direct_tip: '直接使用 EdgeTTS 的完整音色名称进行调用。这种方式会绕过您的 OpenAI 音色映射设置。',
      login_title: '登录 - 本地 TTS 服务',
      login_header: '登录到 TTS 服务',
      login_tip: '此服务已启用密码保护。',
      password_label: '密码:',
      login_button: '登 录'
    },
    en: {
      title: 'Local Multi-language TTS Service',
      desc: 'Powered by Microsoft Edge TTS engine with multiple languages and voices.',
      input_label: 'Input text:',
      input_placeholder: 'Type the text to convert into speech here...',
      char_count: 'Characters:',
      filter_options: 'Text Cleaning Options',
      api_sync_note: 'Apply these filters to all API calls.',
      api_sync_save: 'Changes take effect after saving below',
      remove_markdown: 'Remove Markdown syntax',
      remove_emoji: 'Remove emoji',
      remove_url: 'Remove URL links',
      merge_line: 'Merge lines into one',
      custom_keywords: 'Custom keywords to remove (comma separated):',
      custom_placeholder: 'e.g. note,diagram,disclaimer',
      save_filter: 'Save filter settings',
      select_lang: 'Select language:',
      select_lang_option: '-- Select language --',
      select_voice: 'Select voice:',
      choose_lang_first: 'Please select a language first',
      auto_play: 'Auto play after generation',
      gen_speech: '🎵 Generate Speech',
      download_audio: 'Download audio',
      service_settings: 'Service Settings',
      service_port: 'Service Port:',
      concurrency: 'Concurrency:',
      chunk_size: 'Chunk size:',
      port_hint: 'Port change requires restart. Concurrency takes effect immediately.',
      api_token: 'API token (leave blank to disable auth):',
      empty_api_hint: 'Leave empty to allow anyone to call API',
      gen_token: 'Generate random token',
      openai_map: 'OpenAI Voice Mapping',
      save_settings: 'Save Settings',
      api_guide: 'API Usage Guide',
      api_endpoint: 'API Endpoint',
      api_post: 'Send POST requests to this endpoint:',
      guide_openai: '1. OpenAI compatible format (recommended)',
      openai_tip: 'Use standard OpenAI voice names (e.g. shimmer, alloy). They will be mapped to your selected voices.',
      generating_example: 'Generating example...',
      guide_direct: '2. EdgeTTS direct format',
      direct_tip: 'Call using the full EdgeTTS voice name directly. This bypasses your OpenAI mapping.',
      login_title: 'Login - Local TTS Service',
      login_header: 'Login to TTS Service',
      login_tip: 'This service is password protected.',
      password_label: 'Password:',
      login_button: 'Log in'
    }
  };
  window.translations = translations;

  const langToggle = document.getElementById('lang-toggle');
  const themeToggle = document.getElementById('theme-toggle');

  let currentLang = localStorage.getItem('lang') || 'zh';
  window.currentLang = currentLang;
  applyLang(currentLang);
  if (langToggle) {
    langToggle.textContent = currentLang === 'zh' ? 'EN' : '中文';
    langToggle.addEventListener('click', () => {
      currentLang = currentLang === 'zh' ? 'en' : 'zh';
      localStorage.setItem('lang', currentLang);
      applyLang(currentLang);
      window.currentLang = currentLang;
      langToggle.textContent = currentLang === 'zh' ? 'EN' : '中文';
    });
  }

  let currentTheme = localStorage.getItem('theme') || 'light';
  window.currentTheme = currentTheme;
  applyTheme(currentTheme);
  if (themeToggle) {
    themeToggle.textContent = currentTheme === 'dark' ? '☀' : '🌙';
    themeToggle.addEventListener('click', () => {
      currentTheme = currentTheme === 'light' ? 'dark' : 'light';
      localStorage.setItem('theme', currentTheme);
      applyTheme(currentTheme);
      window.currentTheme = currentTheme;
      themeToggle.textContent = currentTheme === 'dark' ? '☀' : '🌙';
    });
  }

  function applyTheme(theme) {
    document.body.classList.toggle('dark-theme', theme === 'dark');
    document.documentElement.classList.toggle('dark', theme === 'dark');
  }

  function applyLang(lang) {
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
    document.querySelectorAll('[data-i18n]').forEach((el) => {
      const key = el.getAttribute('data-i18n');
      if (translations[lang] && translations[lang][key]) {
        if (el.id === 'char-counter') {
          el.textContent = `${translations[lang][key]} ${document.getElementById('text-input')?.value.length || 0}`;
        } else {
          el.textContent = translations[lang][key];
        }
      }
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach((el) => {
      const key = el.getAttribute('data-i18n-placeholder');
      if (translations[lang] && translations[lang][key]) {
        el.setAttribute('placeholder', translations[lang][key]);
      }
    });
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initCommon);
} else {
  initCommon();
}
