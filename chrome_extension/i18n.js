const langUI = {
  en: {
    readSelected: 'Read Selected Text',
    readPage: 'Read Entire Page',
    server: 'TTS Server Address',
    key: 'API Key',
    lang: 'Language',
    voice: 'Voice',
    refresh: 'Refresh Voices',
    save: 'Save'
  },
  zh: {
    readSelected: '\u6717\u8bfb\u9009\u4e2d\u6587\u672c',
    readPage: '\u6717\u8bfb\u6574\u9875\u5185\u5bb9',
    server: '\u8bed\u97f3\u670d\u52a1\u5668\u5730\u5740',
    key: 'API \u5bc6\u94a5',
    lang: '\u8bed\u8a00',
    voice: '\u97f3\u8272',
    refresh: '\u5237\u65b0\u8bed\u97f3\u5217\u8868',
    save: '\u4fdd\u5b58'
  }
};

function getCurrentUILang() {
  return navigator.language.startsWith('zh') ? 'zh' : 'en';
}

function applyPopupI18n() {
  const lang = getCurrentUILang();
  document.querySelector('label[for="server-url"]').textContent = langUI[lang].server;
  document.querySelector('label[for="api-key"]').textContent = langUI[lang].key;
  document.querySelector('label[for="language-select"]').textContent = langUI[lang].lang;
  document.querySelector('label[for="voice-select"]').textContent = langUI[lang].voice;
  document.getElementById('read-selection').textContent = langUI[lang].readSelected;
  document.getElementById('read-page').textContent = langUI[lang].readPage;
}

function applyOptionsI18n() {
  const lang = getCurrentUILang();
  document.querySelector('h2').textContent = lang === 'zh' ? 'LocalTTS \u8bbe\u7f6e' : 'LocalTTS Options';
  document.getElementById('label-api-url').childNodes[0].nodeValue = langUI[lang].server + ': ';
  document.getElementById('label-api-token').childNodes[0].nodeValue = langUI[lang].key + ': ';
  document.getElementById('label-language-select').childNodes[0].nodeValue = langUI[lang].lang + ': ';
  document.getElementById('label-voice-select').childNodes[0].nodeValue = langUI[lang].voice + ': ';
  document.getElementById('refresh-btn').textContent = langUI[lang].refresh;
  document.getElementById('save-btn').textContent = langUI[lang].save;
}
