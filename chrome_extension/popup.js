let config = {};
let allVoices = [];
const audio = document.getElementById('audio');
const langSelect = document.getElementById('language-select');
const voiceSelect = document.getElementById('voice-select');

async function loadConfig() {
  config = await chrome.storage.local.get({
    apiUrl: 'http://127.0.0.1:5050',
    apiToken: '',
    language: '',
    voice: ''
  });
  await fetchVoices();
  if (config.language) {
    langSelect.value = config.language;
    updateVoiceOptions(config.language);
    voiceSelect.value = config.voice;
  }
}

async function fetchVoices() {
  try {
    const res = await fetch(`${config.apiUrl.replace(/\/$/, '')}/v1/audio/all_voices`, {
      headers: config.apiToken ? { 'Authorization': 'Bearer ' + config.apiToken } : {}
    });
    allVoices = await res.json();
    const locales = [...new Set(allVoices.map(v => v.locale))];
    langSelect.innerHTML = locales.map(l => `<option value="${l}">${l}</option>`).join('');
  } catch(e) {
    console.error(e);
  }
}

function updateVoiceOptions(locale) {
  const voices = allVoices.filter(v => v.locale === locale);
  voiceSelect.innerHTML = voices.map(v => `<option value="${v.name}">${v.short_name} (${v.gender})</option>`).join('');
}

langSelect.addEventListener('change', () => updateVoiceOptions(langSelect.value));

async function capture(tabId, func) {
  const [{ result }] = await chrome.scripting.executeScript({ target: { tabId }, func });
  return result;
}

async function speakText(text) {
  if (!text) return;
  const url = config.apiUrl.replace(/\/$/, '');
  const headers = { 'Content-Type': 'application/json' };
  if (config.apiToken) headers['Authorization'] = 'Bearer ' + config.apiToken;
  const body = JSON.stringify({ model: 'tts-1', input: text, voice: voiceSelect.value, stream: true });
  const response = await fetch(`${url}/v1/audio/speech`, { method: 'POST', headers, body });
  const mediaSource = new MediaSource();
  audio.src = URL.createObjectURL(mediaSource);
  audio.play();
  mediaSource.addEventListener('sourceopen', () => {
    const sourceBuffer = mediaSource.addSourceBuffer('audio/mpeg');
    const reader = response.body.getReader();
    const pump = () => reader.read().then(({ done, value }) => {
      if (done) {
        if (sourceBuffer.updating) {
          sourceBuffer.addEventListener('updateend', () => mediaSource.endOfStream(), { once: true });
        } else {
          mediaSource.endOfStream();
        }
        return;
      }
      sourceBuffer.appendBuffer(value);
      if (sourceBuffer.updating) {
        sourceBuffer.addEventListener('updateend', pump, { once: true });
      } else {
        pump();
      }
    });
    pump();
  });
}

document.getElementById('read-selection').addEventListener('click', async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const text = await capture(tab.id, () => window.getSelection().toString());
  speakText(text);
});

document.getElementById('read-page').addEventListener('click', async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const text = await capture(tab.id, () => document.body.innerText);
  speakText(text);
});

chrome.storage.local.get('pendingText').then(data => {
  if (data.pendingText) {
    speakText(data.pendingText);
    chrome.storage.local.remove('pendingText');
  }
});

loadConfig();
