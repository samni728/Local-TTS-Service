(function(){
  if (window.TTSPlayerInitialized) return;
  window.TTSPlayerInitialized = true;

  const langUI = {
    en: { close: 'Close', speed: 'Speed' },
    zh: { close: '\u5173\u95ed', speed: '\u901f\u5ea6' }
  };

  const currentLang = navigator.language.startsWith('zh') ? 'zh' : 'en';

  function createFloatingPlayer() {
    if (document.getElementById('tts-floating-player')) return;
    const wrapper = document.createElement('div');
    wrapper.id = 'tts-floating-player';
    wrapper.style.cssText = 'position:fixed; bottom:20px; right:20px; z-index:999999; background:white; padding:10px; border-radius:8px; box-shadow:0 2px 10px rgba(0,0,0,0.1); width:300px;';
    wrapper.innerHTML = `
      <div id="tts-header" style="cursor:move;background:#eee;padding:2px 5px;text-align:right;">
        <button id="tts-close">\u00d7</button>
      </div>
      <audio id="tts-audio" controls style="width:100%;"></audio>
      <label style="font-size:12px;display:block;margin-top:4px;">${langUI[currentLang].speed}
        <input id="tts-speed" type="range" min="0.5" max="2" step="0.25" value="1">
      </label>`;
    document.body.appendChild(wrapper);

    const header = wrapper.querySelector('#tts-header');
    header.addEventListener('mousedown', startDrag);
    wrapper.querySelector('#tts-close').addEventListener('click', () => {
      wrapper.remove();
      window.TTSPlayerInitialized = false;
    });

    const speedInput = wrapper.querySelector('#tts-speed');
    const audio = wrapper.querySelector('#tts-audio');
    speedInput.addEventListener('input', () => {
      audio.playbackRate = speedInput.value;
    });
  }

  let dragOffsetX = 0, dragOffsetY = 0;
  function startDrag(e) {
    e.preventDefault();
    const rect = this.parentElement.getBoundingClientRect();
    dragOffsetX = e.clientX - rect.left;
    dragOffsetY = e.clientY - rect.top;
    document.addEventListener('mousemove', onDrag);
    document.addEventListener('mouseup', stopDrag);
  }
  function onDrag(e) {
    const wrapper = document.getElementById('tts-floating-player');
    if (!wrapper) return;
    wrapper.style.left = (e.clientX - dragOffsetX) + 'px';
    wrapper.style.top = (e.clientY - dragOffsetY) + 'px';
    wrapper.style.bottom = 'auto';
    wrapper.style.right = 'auto';
  }
  function stopDrag() {
    document.removeEventListener('mousemove', onDrag);
    document.removeEventListener('mouseup', stopDrag);
  }

  window.createFloatingTTSPlayer = createFloatingPlayer;

  window.playTTS = async function(cfg, text) {
    createFloatingPlayer();
    const audio = document.getElementById('tts-audio');
    if (!text) return;
    const url = cfg.apiUrl.replace(/\/$/, '');
    const headers = { 'Content-Type': 'application/json' };
    if (cfg.apiToken) headers['Authorization'] = 'Bearer ' + cfg.apiToken;
    const body = JSON.stringify({ model: 'tts-1', input: text, voice: cfg.voice, stream: true });
    const response = await fetch(`${url}/v1/audio/speech`, { method: 'POST', headers, body });

    const mediaSource = new MediaSource();
    audio.src = URL.createObjectURL(mediaSource);
    audio.playbackRate = document.getElementById('tts-speed').value;
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
  };
})();
