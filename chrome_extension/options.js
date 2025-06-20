async function fetchVoices(url, token) {
  try {
    const res = await fetch(`${url}/v1/audio/all_voices`, {
      headers: token ? { 'Authorization': 'Bearer ' + token } : {}
    });
    return await res.json();
  } catch (e) {
    console.error('Failed to fetch voices', e);
    return [];
  }
}

function populateLocales(voices, languageSelect) {
  const locales = [...new Set(voices.map(v => v.locale))];
  languageSelect.innerHTML = locales.map(l => `<option value="${l}">${l}</option>`).join('');
}

function populateVoices(voices, locale, voiceSelect) {
  const filtered = voices.filter(v => v.locale === locale);
  voiceSelect.innerHTML = filtered.map(v => `<option value="${v.name}">${v.short_name} (${v.gender})</option>`).join('');
}

document.addEventListener('DOMContentLoaded', async () => {
  applyOptionsI18n();
  const urlInput = document.getElementById('api-url');
  const tokenInput = document.getElementById('api-token');
  const languageSelect = document.getElementById('language-select');
  const voiceSelect = document.getElementById('voice-select');
  const saveBtn = document.getElementById('save-btn');
  const refreshBtn = document.getElementById('refresh-btn');

  let allVoices = [];

  async function loadConfig() {
    const cfg = await chrome.storage.local.get({
      apiUrl: 'http://127.0.0.1:5050',
      apiToken: '',
      language: '',
      voice: ''
    });
    urlInput.value = cfg.apiUrl;
    tokenInput.value = cfg.apiToken;
    allVoices = await fetchVoices(cfg.apiUrl, cfg.apiToken);
    populateLocales(allVoices, languageSelect);
    if (cfg.language) {
      languageSelect.value = cfg.language;
      populateVoices(allVoices, cfg.language, voiceSelect);
      if (cfg.voice) voiceSelect.value = cfg.voice;
    }
  }

  languageSelect.addEventListener('change', () => {
    populateVoices(allVoices, languageSelect.value, voiceSelect);
  });

  refreshBtn.addEventListener('click', async () => {
    allVoices = await fetchVoices(urlInput.value, tokenInput.value);
    populateLocales(allVoices, languageSelect);
    populateVoices(allVoices, languageSelect.value, voiceSelect);
  });

  saveBtn.addEventListener('click', async () => {
    await chrome.storage.local.set({
      apiUrl: urlInput.value,
      apiToken: tokenInput.value,
      language: languageSelect.value,
      voice: voiceSelect.value
    });
    const lang = getCurrentUILang();
    alert(lang === 'zh' ? '设置已保存' : 'Saved');
  });

  loadConfig();
});
