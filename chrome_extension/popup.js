let config = {};
let allVoices = [];

const serverInput = document.getElementById('server-url');
const apiKeyInput = document.getElementById('api-key');
const langSelect = document.getElementById('language-select');
const voiceSelect = document.getElementById('voice-select');
const audio = document.getElementById('audio');

async function init() {
    config = await chrome.storage.local.get({
        apiUrl: 'http://127.0.0.1:5050',
        apiToken: '',
        language: '',
        voice: ''
    });
    serverInput.value = config.apiUrl;
    apiKeyInput.value = config.apiToken;
    await fetchVoices();
    if (config.language) {
        langSelect.value = config.language;
        updateVoiceOptions(config.language);
        if (config.voice) voiceSelect.value = config.voice;
    }
}

async function fetchVoices() {
    const url = serverInput.value.replace(/\/$/, '');
    try {
        const res = await fetch(`${url}/v1/audio/all_voices`, {
            headers: apiKeyInput.value ? { 'Authorization': 'Bearer ' + apiKeyInput.value } : {}
        });
        allVoices = await res.json();
        const locales = [...new Set(allVoices.map(v => v.locale))];
        langSelect.innerHTML = locales.map(l => `<option value="${l}">${l}</option>`).join('');
    } catch (e) {
        console.error('Failed to fetch voices', e);
        langSelect.innerHTML = '';
        voiceSelect.innerHTML = '';
    }
}

function updateVoiceOptions(locale) {
    const voices = allVoices.filter(v => v.locale === locale);
    voiceSelect.innerHTML = voices.map(v => `<option value="${v.name}">${v.short_name} (${v.gender})</option>`).join('');
}

serverInput.addEventListener('change', async () => {
    await chrome.storage.local.set({ apiUrl: serverInput.value });
    config.apiUrl = serverInput.value;
    fetchVoices();
});

apiKeyInput.addEventListener('change', async () => {
    await chrome.storage.local.set({ apiToken: apiKeyInput.value });
    config.apiToken = apiKeyInput.value;
    fetchVoices();
});

langSelect.addEventListener('change', async () => {
    updateVoiceOptions(langSelect.value);
    await chrome.storage.local.set({ language: langSelect.value });
    config.language = langSelect.value;
});

voiceSelect.addEventListener('change', async () => {
    await chrome.storage.local.set({ voice: voiceSelect.value });
    config.voice = voiceSelect.value;
});

async function capture(tabId, func) {
    const [{ result }] = await chrome.scripting.executeScript({ target: { tabId }, func });
    return result;
}

async function speakText(text) {
    if (!text) return;
    const url = serverInput.value.replace(/\/$/, '');
    const headers = { 'Content-Type': 'application/json' };
    if (apiKeyInput.value) headers['Authorization'] = 'Bearer ' + apiKeyInput.value;
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

init();
