"""
ÆONIX PRISM // Sovereign POCO Tactile Push-to-Talk (PTT) Operator Console
Single-file, mobile-first, high-contrast, offline-first Web UI.
Zero external CDNs, zero cloud analytics, zero tracking.
Operates on POCO localhost (127.0.0.1:8080) for sovereign tactile voice command and Sentinel authorization.
"""

def get_ptt_console_html(api_token: str = "") -> str:
    """Returns the complete HTML5 operator console string."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>ÆONIX PRISM // Sovereign PTT Console</title>
<style>
  :root {{
    --bg-dark: #080c10;
    --card-bg: #121820;
    --card-border: #1e293b;
    --text-primary: #f1f5f9;
    --text-secondary: #94a3b8;
    --accent-cyan: #00e5ff;
    --accent-blue: #3b82f6;
    --accent-amber: #f59e0b;
    --accent-red: #ef4444;
    --accent-green: #10b981;
    --touch-min: 48px;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
  body {{
    background-color: var(--bg-dark);
    color: var(--text-primary);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    padding: 12px;
    user-select: none;
    -webkit-user-select: none;
  }}
  header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--card-border);
  }}
  .brand {{ font-size: 1.1rem; font-weight: 700; letter-spacing: 0.05em; color: var(--accent-cyan); }}
  .badge {{
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 600;
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    color: var(--text-secondary);
  }}
  .badge.online {{ border-color: var(--accent-green); color: var(--accent-green); }}
  .badge.recording {{ border-color: var(--accent-red); color: var(--accent-red); animation: pulse 1s infinite; }}
  .badge.lockdown {{ background: var(--accent-red); color: #fff; }}
  @keyframes pulse {{ 0% {{ opacity: 1; }} 50% {{ opacity: 0.4; }} 100% {{ opacity: 1; }} }}

  .hero {{
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    padding: 24px 0;
    text-align: center;
  }}
  .indicator-box {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 16px;
    font-size: 0.85rem;
    font-weight: 600;
  }}
  .red-dot {{
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background-color: var(--accent-red);
    display: none;
  }}
  .red-dot.active {{ display: inline-block; animation: pulse 0.8s infinite; }}

  /* Tactile PTT Button */
  .ptt-container {{
    position: relative;
    width: 220px;
    height: 220px;
    display: flex;
    justify-content: center;
    align-items: center;
  }}
  #ptt-btn {{
    width: 200px;
    height: 200px;
    border-radius: 50%;
    border: 4px solid var(--accent-cyan);
    background: radial-gradient(circle, #1e293b 0%, #0f172a 100%);
    color: var(--text-primary);
    font-size: 1.1rem;
    font-weight: 700;
    cursor: pointer;
    box-shadow: 0 0 25px rgba(0, 229, 255, 0.2);
    transition: all 0.15s ease;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    gap: 8px;
    outline: none;
  }}
  #ptt-btn:active, #ptt-btn.active {{
    border-color: var(--accent-red);
    box-shadow: 0 0 40px rgba(239, 68, 68, 0.6);
    transform: scale(0.96);
    background: radial-gradient(circle, #331015 0%, #1f0b0e 100%);
  }}
  .mic-icon {{ font-size: 2rem; }}
  
  .controls-row {{
    display: flex;
    gap: 12px;
    margin-top: 16px;
    align-items: center;
  }}
  .toggle-label {{ font-size: 0.85rem; color: var(--text-secondary); display: flex; align-items: center; gap: 6px; cursor: pointer; }}

  /* Cards and Status Sections */
  .section {{
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 8px;
    padding: 12px;
    margin-top: 12px;
  }}
  .section-title {{
    font-size: 0.8rem;
    font-weight: 700;
    text-transform: uppercase;
    color: var(--text-secondary);
    letter-spacing: 0.05em;
    margin-bottom: 8px;
    display: flex;
    justify-content: space-between;
  }}
  .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
  .stat-card {{ background: #0b0f15; padding: 8px; border-radius: 6px; border: 1px solid #1a2230; }}
  .stat-label {{ font-size: 0.7rem; color: var(--text-secondary); }}
  .stat-val {{ font-size: 0.9rem; font-weight: 600; margin-top: 2px; }}

  /* Sentinel Deck */
  .sentinel-item {{
    background: #18120b;
    border: 1px solid #45260a;
    border-radius: 6px;
    padding: 10px;
    margin-bottom: 8px;
  }}
  .btn-row {{ display: flex; gap: 8px; margin-top: 8px; }}
  button.action-btn {{
    flex: 1;
    min-height: var(--touch-min);
    border: none;
    border-radius: 4px;
    font-weight: 600;
    font-size: 0.85rem;
    cursor: pointer;
  }}
  .btn-approve {{ background: var(--accent-green); color: #fff; }}
  .btn-deny {{ background: #334155; color: #fff; }}
  .btn-emergency {{ background: var(--accent-red); color: #fff; width: 100%; min-height: var(--touch-min); margin-top: 12px; font-weight: 700; }}

  /* Notice Banner */
  #notice-banner {{
    padding: 10px;
    border-radius: 6px;
    margin-top: 12px;
    font-size: 0.85rem;
    display: none;
  }}
  #notice-banner.error {{ background: #331015; border: 1px solid var(--accent-red); color: #fca5a5; display: block; }}
  #notice-banner.info {{ background: #0f2238; border: 1px solid var(--accent-blue); color: #93c5fd; display: block; }}

  /* Speech output */
  #speech-card {{
    background: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 6px;
    padding: 10px;
    font-size: 0.9rem;
    color: #e2e8f0;
    min-height: 48px;
  }}
</style>
</head>
<body>

<header>
  <div class="brand">ÆONIX PRISM</div>
  <div style="display:flex; gap:6px; align-items:center;">
    <span id="tv-status-badge" class="badge">TV: --</span>
    <span id="lockdown-badge" class="badge">DEFENSE: --</span>
    <button id="session-logout-btn" style="display:none; background:none; border:1px solid var(--accent-red); color:var(--accent-red); padding:3px 6px; border-radius:4px; font-size:0.7rem; cursor:pointer;">EXIT</button>
  </div>
</header>

<div id="notice-banner"></div>

<main class="hero">
  <div class="indicator-box">
    <span id="rec-indicator" class="red-dot"></span>
    <span id="state-text">IDLE</span>
    <span id="timer-text" style="color:var(--text-secondary); margin-left:4px;">(0.0s / 15.0s)</span>
  </div>

  <div class="ptt-container">
    <button id="ptt-btn" aria-label="Push-to-Talk microphone button" aria-pressed="false">
      <span class="mic-icon">🎙️</span>
      <span id="btn-label">HOLD TO TALK</span>
    </button>
  </div>

  <div class="controls-row">
    <label class="toggle-label">
      <input type="checkbox" id="toggle-mode-cb">
      <span>Toggle Mode (Tap to Start/Stop)</span>
    </label>
  </div>
</main>

<section class="section">
  <div class="section-title">Latest Intent & Speech</div>
  <div id="speech-card" aria-live="polite">Awaiting voice command...</div>
</section>

<section class="section" id="sentinel-deck">
  <div class="section-title">Sentinel Approval Deck <span id="pending-count" class="badge">0</span></div>
  <div id="pending-list" style="font-size:0.85rem; color:var(--text-secondary);">--</div>
</section>

<section class="section">
  <div class="section-title">System Status</div>
  <div class="grid-2">
    <div class="stat-card">
      <div class="stat-label">Model Engine</div>
      <div class="stat-val" id="model-val">--</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">RAM Queue</div>
      <div class="stat-val" id="queue-val">--</div>
    </div>
  </div>
  <button id="sanctuary-btn" class="btn-emergency">ACTIVATE SANCTUARY LOCKDOWN</button>
</section>

<!-- Volatile In-Memory Authentication Overlay -->
<div id="auth-overlay" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(8,12,16,0.96); z-index:9999; flex-direction:column; justify-content:center; align-items:center; padding:20px;">
  <div style="background:var(--card-bg); border:1px solid var(--accent-cyan); border-radius:8px; padding:24px; max-width:400px; width:100%; text-align:center;">
    <div style="color:var(--accent-cyan); font-weight:700; margin-bottom:12px; font-size:1.1rem; letter-spacing:0.05em;">OPERATOR AUTHENTICATION</div>
    <div style="color:var(--text-secondary); font-size:0.85rem; margin-bottom:16px;">
      Enter single-use 128-bit bootstrap secret from POCO Termux CLI (<code style="color:var(--accent-cyan);">python3 scripts/bootstrap_ptt_operator.py</code>).
    </div>
    <input id="auth-code-input" type="text" placeholder="32-character hex secret" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" style="width:100%; padding:12px; border-radius:4px; border:1px solid var(--card-border); background:#080c10; color:#fff; font-size:0.95rem; margin-bottom:12px; text-align:center;">
    <button id="auth-submit-btn" style="width:100%; padding:12px; border-radius:4px; border:none; background:var(--accent-cyan); color:#080c10; font-weight:700; font-size:1rem; cursor:pointer;">AUTHENTICATE SESSION</button>
    <div id="auth-error-msg" style="color:var(--accent-red); font-size:0.8rem; margin-top:10px; display:none;"></div>
  </div>
</div>

<script>
  let isRecording = false;
  let timerInterval = null;
  let startTime = null;
  let token = "{api_token}";
  let sessionExpiryTimer = null;

  const authOverlay = document.getElementById('auth-overlay');
  const authInput = document.getElementById('auth-code-input');
  const authBtn = document.getElementById('auth-submit-btn');
  const authError = document.getElementById('auth-error-msg');
  const logoutBtn = document.getElementById('session-logout-btn');

  function checkAuthRequirement() {{
    if (!token) {{
      authOverlay.style.display = 'flex';
      if (logoutBtn) logoutBtn.style.display = 'none';
    }} else {{
      authOverlay.style.display = 'none';
      if (logoutBtn) logoutBtn.style.display = 'inline-block';
    }}
  }}

  // Shared cleanup path for explicit logout, session expiry, and authentication failure
  function cleanupSession(reason = 'logout', noticeMsg = 'Session closed.') {{
    if (sessionExpiryTimer) {{
      clearTimeout(sessionExpiryTimer);
      sessionExpiryTimer = null;
    }}
    if (isRecording) {{
      isRecording = false;
      if (timerInterval) {{
        clearInterval(timerInterval);
        timerInterval = null;
      }}
      if (typeof pttBtn !== 'undefined' && pttBtn) {{
        pttBtn.classList.remove('active');
        pttBtn.setAttribute('aria-pressed', 'false');
      }}
      if (typeof recIndicator !== 'undefined' && recIndicator) recIndicator.classList.remove('active');
      if (typeof btnLabel !== 'undefined' && btnLabel) btnLabel.textContent = 'HOLD TO TALK';
      if (typeof stateText !== 'undefined' && stateText) stateText.textContent = 'IDLE';
    }}
    capturedChunks = [];
    releaseMicHardware();
    token = '';
    if (typeof tvBadge !== 'undefined' && tvBadge) {{
      tvBadge.textContent = 'TV: --';
      tvBadge.className = 'badge';
    }}
    if (typeof lockdownBadge !== 'undefined' && lockdownBadge) {{
      lockdownBadge.textContent = 'DEFENSE: --';
      lockdownBadge.className = 'badge';
    }}
    if (typeof modelVal !== 'undefined' && modelVal) modelVal.textContent = '--';
    if (typeof queueVal !== 'undefined' && queueVal) queueVal.textContent = '--';
    if (typeof pendingList !== 'undefined' && pendingList) pendingList.textContent = '--';
    checkAuthRequirement();
    if (noticeMsg) {{
      showNotice(noticeMsg, reason === 'error' || reason === 'auth_failure' || reason === 'expired' ? 'error' : 'info');
    }}
  }}

  authBtn.addEventListener('click', async () => {{
    const val = authInput.value.trim();
    if (!val) {{
      authError.textContent = 'Please enter a 32-character hex bootstrap secret.';
      authError.style.display = 'block';
      return;
    }}
    if (!/^[0-9a-fA-F]{{32}}$/.test(val)) {{
      authError.textContent = 'Invalid format: Secret must be exactly 32 hexadecimal characters.';
      authError.style.display = 'block';
      return;
    }}
    authError.style.display = 'none';
    authBtn.textContent = 'VERIFYING...';
    authBtn.disabled = true;

    try {{
      // Route 100% of modal submissions strictly through POST /api/ptt/bootstrap
      const res = await fetch('/api/ptt/bootstrap', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ secret: val }})
      }});
      const data = await res.json();
      if (data.token) {{
        token = data.token;
        authInput.value = '';
        authOverlay.style.display = 'none';
        if (logoutBtn) logoutBtn.style.display = 'inline-block';
        showNotice('PTT Operator session authenticated (volatile memory).', 'info');
        if (sessionExpiryTimer) clearTimeout(sessionExpiryTimer);
        const ttlSec = (data.expires_in && typeof data.expires_in === 'number') ? data.expires_in : 900;
        sessionExpiryTimer = setTimeout(() => {{
          cleanupSession('expired', 'Session expired (15-min limit reached). Please generate a new bootstrap secret.');
        }}, ttlSec * 1000);
        refreshStatus();
      }} else {{
        authError.textContent = data.detail || 'Invalid or expired bootstrap secret.';
        authError.style.display = 'block';
      }}
    }} catch (err) {{
      authError.textContent = 'Connection error: ' + err.message;
      authError.style.display = 'block';
    }} finally {{
      authBtn.textContent = 'AUTHENTICATE SESSION';
      authBtn.disabled = false;
    }}
  }});

  if (logoutBtn) {{
    logoutBtn.addEventListener('click', async () => {{
      const activeToken = token;
      cleanupSession('logout', 'Session closed and token revoked.');
      if (activeToken) {{
        try {{
          await fetch('/api/ptt/logout', {{
            method: 'POST',
            headers: {{ 'Authorization': 'Bearer ' + activeToken }}
          }});
        }} catch(e) {{}}
      }}
    }});
  }}

  const pttBtn = document.getElementById('ptt-btn');
  const btnLabel = document.getElementById('btn-label');
  const recIndicator = document.getElementById('rec-indicator');
  const stateText = document.getElementById('state-text');
  const timerText = document.getElementById('timer-text');
  const toggleCb = document.getElementById('toggle-mode-cb');
  const speechCard = document.getElementById('speech-card');
  const noticeBanner = document.getElementById('notice-banner');
  const sanctuaryBtn = document.getElementById('sanctuary-btn');
  const pendingList = document.getElementById('pending-list');
  const pendingCount = document.getElementById('pending-count');
  const modelVal = document.getElementById('model-val');
  const queueVal = document.getElementById('queue-val');
  const tvBadge = document.getElementById('tv-status-badge');
  const lockdownBadge = document.getElementById('lockdown-badge');

  async function apiCall(endpoint, method = 'GET', body = null) {{
    try {{
      const headers = {{ 'Content-Type': 'application/json' }};
      if (token) headers['Authorization'] = 'Bearer ' + token;
      const opts = {{ method, headers }};
      if (body) opts.body = JSON.stringify(body);
      const res = await fetch(endpoint, opts);
      return await res.json();
    }} catch (e) {{
      return {{ error: e.message }};
    }}
  }}

  function updateTimer() {{
    if (!startTime) return;
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    timerText.textContent = `(${{elapsed}}s / 15.0s)`;
    if (elapsed >= 15.0) {{
      stopPtt('timeout');
    }}
  }}

  let mediaStream = null;
  let audioCtx = null;
  let scriptNode = null;
  let sourceNode = null;
  let capturedChunks = [];
  let actualSampleRate = 16000;

  function releaseMicHardware() {{
    if (scriptNode) {{
      try {{ scriptNode.disconnect(); }} catch(e) {{}}
      scriptNode = null;
    }}
    if (sourceNode) {{
      try {{ sourceNode.disconnect(); }} catch(e) {{}}
      sourceNode = null;
    }}
    if (audioCtx) {{
      try {{ audioCtx.close(); }} catch(e) {{}}
      audioCtx = null;
    }}
    if (mediaStream) {{
      try {{
        mediaStream.getTracks().forEach(t => t.stop());
      }} catch(e) {{}}
      mediaStream = null;
    }}
  }}

  function resampleTo16k(float32Audio, inputRate) {{
    if (inputRate === 16000) return float32Audio;
    const targetRate = 16000;
    const ratio = inputRate / targetRate;
    const newLength = Math.round(float32Audio.length / ratio);
    const result = new Float32Array(newLength);
    for (let i = 0; i < newLength; i++) {{
      const srcIdx = i * ratio;
      const idx = Math.floor(srcIdx);
      const frac = srcIdx - idx;
      const s0 = float32Audio[idx] || 0.0;
      const s1 = float32Audio[idx + 1] || s0;
      result[i] = (1.0 - frac) * s0 + frac * s1;
    }}
    return result;
  }}

  function encodeWav(samples, sampleRate) {{
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);
    function writeStr(offset, str) {{
      for (let i = 0; i < str.length; i++) {{
        view.setUint8(offset + i, str.charCodeAt(i));
      }}
    }}
    writeStr(0, 'RIFF');
    view.setUint32(4, 36 + samples.length * 2, true);
    writeStr(8, 'WAVE');
    writeStr(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true); // PCM format
    view.setUint16(22, 1, true); // 1 channel (mono)
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true); // byte rate (sampleRate * 1 * 2)
    view.setUint16(32, 2, true); // block align
    view.setUint16(34, 16, true); // bits per sample (16)
    writeStr(36, 'data');
    view.setUint32(40, samples.length * 2, true);
    for (let i = 0; i < samples.length; i++) {{
      view.setInt16(44 + i * 2, samples[i], true);
    }}
    return new Blob([view], {{ type: 'audio/wav' }});
  }}

  async function startPtt() {{
    if (isRecording) return;
    noticeBanner.className = '';
    noticeBanner.style.display = 'none';

    // 1. Secure context check
    if (!window.isSecureContext && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {{
      showNotice('Browser security requires HTTPS for microphone access.', 'error');
      stateText.textContent = 'INSECURE CONTEXT';
      return;
    }}
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {{
      showNotice('getUserMedia is not supported by this browser.', 'error');
      stateText.textContent = 'NO MIC SUPPORT';
      return;
    }}

    stateText.textContent = 'REQUESTING PERMISSION';

    // 2. Request microphone stream strictly on explicit user gesture
    try {{
      mediaStream = await navigator.mediaDevices.getUserMedia({{
        audio: {{
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true
        }}
      }});
    }} catch (err) {{
      showNotice('Microphone access denied or unavailable: ' + err.message, 'error');
      stateText.textContent = 'PERMISSION DENIED';
      releaseMicHardware();
      return;
    }}

    // 3. Initialize AudioContext and capture node
    try {{
      const AudioCtxClass = window.AudioContext || window.webkitAudioContext;
      audioCtx = new AudioCtxClass();
      actualSampleRate = audioCtx.sampleRate;
      sourceNode = audioCtx.createMediaStreamSource(mediaStream);
      scriptNode = audioCtx.createScriptProcessor(4096, 1, 1);
      capturedChunks = [];
      scriptNode.onaudioprocess = (e) => {{
        if (!isRecording) return;
        const input = e.inputBuffer.getChannelData(0);
        capturedChunks.push(new Float32Array(input));
      }};
      sourceNode.connect(scriptNode);
      scriptNode.connect(audioCtx.destination);
    }} catch (ctxErr) {{
      showNotice('Failed to initialize audio capture: ' + ctxErr.message, 'error');
      stateText.textContent = 'CAPTURE ERROR';
      releaseMicHardware();
      return;
    }}

    // 4. Notify server of PTT start
    const data = await apiCall('/api/ptt/start', 'POST');
    if (data.status === 'recording') {{
      isRecording = true;
      startTime = Date.now();
      timerInterval = setInterval(updateTimer, 100);
      pttBtn.classList.add('active');
      pttBtn.setAttribute('aria-pressed', 'true');
      recIndicator.classList.add('active');
      btnLabel.textContent = toggleCb.checked ? 'TAP TO STOP' : 'RECORDING...';
      stateText.textContent = 'RECORDING';
    }} else if (data.status === 'blocked_lockdown') {{
      releaseMicHardware();
      showNotice(data.error || 'Sanctuary Lockdown is active.', 'error');
      stateText.textContent = 'LOCKDOWN';
    }} else {{
      releaseMicHardware();
      showNotice(data.error || 'Unable to start recording.', 'error');
      stateText.textContent = 'IDLE';
    }}
  }}

  async function stopPtt(reason = 'release') {{
    if (!isRecording) return;
    isRecording = false;
    clearInterval(timerInterval);
    timerInterval = null;
    startTime = null;
    timerText.textContent = '(0.0s / 15.0s)';

    pttBtn.classList.remove('active');
    pttBtn.setAttribute('aria-pressed', 'false');
    recIndicator.classList.remove('active');
    btnLabel.textContent = toggleCb.checked ? 'TAP TO SPEAK' : 'HOLD TO TALK';
    stateText.textContent = 'PROCESSING';

    // 1. Immediately disconnect audio nodes and stop physical microphone tracks
    const chunks = capturedChunks;
    capturedChunks = [];
    releaseMicHardware();

    // 2. Process audio if captured
    let wavBlob = null;
    if (chunks.length > 0 && reason !== 'background' && reason !== 'cancel') {{
      try {{
        const totalSamples = chunks.reduce((acc, c) => acc + c.length, 0);
        const flat = new Float32Array(totalSamples);
        let offset = 0;
        for (const c of chunks) {{
          flat.set(c, offset);
          offset += c.length;
        }}
        const resampled = resampleTo16k(flat, actualSampleRate);
        const maxSamples = 15 * 16000;
        const clamped = resampled.length > maxSamples ? resampled.subarray(0, maxSamples) : resampled;
        const pcm16 = new Int16Array(clamped.length);
        for (let i = 0; i < clamped.length; i++) {{
          const s = Math.max(-1, Math.min(1, clamped[i]));
          pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }}
        wavBlob = encodeWav(pcm16, 16000);
      }} catch (encErr) {{
        console.error('Audio encoding failed:', encErr);
      }}
    }}

    let data;
    if (wavBlob) {{
      try {{
        const stopUrl = '/api/ptt/stop?reason=' + encodeURIComponent(reason);
        const headers = {{
          'Content-Type': 'audio/wav',
          'X-Audio-Sample-Rate': '16000',
          'X-Audio-Channels': '1'
        }};
        if (token) headers['Authorization'] = 'Bearer ' + token;
        const response = await fetch(stopUrl, {{
          method: 'POST',
          headers: headers,
          body: wavBlob
        }});
        data = await response.json();
      }} catch (netErr) {{
        data = {{ error: netErr.message }};
      }}
    }} else {{
      data = await apiCall('/api/ptt/stop', 'POST', {{ reason }});
    }}

    if (data && data.pipeline) {{
      const p = data.pipeline;
      stateText.textContent = p.status.toUpperCase();
      speechCard.textContent = p.speech || '[No speech response]';
      if (p.requires_sentinel_approval) {{
        showNotice('Consequential action held at Sentinel Gate. Authorization required below.', 'info');
      }}
    }} else if (data && data.error) {{
      showNotice(data.error, 'error');
      stateText.textContent = 'ERROR';
    }} else {{
      stateText.textContent = 'IDLE';
    }}
    refreshStatus();
  }}

  function showNotice(msg, type = 'info') {{
    noticeBanner.textContent = msg;
    noticeBanner.className = type;
    noticeBanner.style.display = 'block';
  }}

  // Event Listeners for Touch / Mouse
  pttBtn.addEventListener('touchstart', (e) => {{
    e.preventDefault();
    if (!toggleCb.checked) startPtt();
  }});
  pttBtn.addEventListener('touchend', (e) => {{
    e.preventDefault();
    if (!toggleCb.checked) stopPtt('release');
    else if (isRecording) stopPtt('release');
    else startPtt();
  }});
  pttBtn.addEventListener('mousedown', () => {{
    if (!toggleCb.checked) startPtt();
  }});
  pttBtn.addEventListener('mouseup', () => {{
    if (!toggleCb.checked) stopPtt('release');
    else if (isRecording) stopPtt('release');
    else startPtt();
  }});

  // Safety: Focus loss and backgrounding immediately stop mic
  window.addEventListener('blur', () => {{ if (isRecording) stopPtt('background'); }});
  document.addEventListener('visibilitychange', () => {{
    if (document.hidden && isRecording) stopPtt('background');
  }});

  // Status and Sentinel refresh
  async function refreshStatus() {{
    if (!token) return;
    const s = await apiCall('/api/ptt/status');
    if (s && s.error && (s.error.includes('UNAUTHENTICATED') || s.error.includes('Invalid, expired') || s.error.includes('FORBIDDEN'))) {{
      cleanupSession('auth_failure', 'Session invalid or expired. Re-authentication required.');
      return;
    }}
    if (s && s.ptt) {{
      if (s.sanctuary && s.sanctuary.is_active) {{
        lockdownBadge.textContent = 'SANCTUARY ACTIVE';
        lockdownBadge.className = 'badge lockdown';
        sanctuaryBtn.textContent = 'DISENGAGE SANCTUARY LOCKDOWN';
        sanctuaryBtn.style.background = '#334155';
      }} else {{
        lockdownBadge.textContent = 'DEFENSE: NOMINAL';
        lockdownBadge.className = 'badge';
        sanctuaryBtn.textContent = 'ACTIVATE SANCTUARY LOCKDOWN';
        sanctuaryBtn.style.background = 'var(--accent-red)';
      }}

      tvBadge.textContent = s.firetv_connected ? 'TV: CONNECTED' : 'TV: DISCONNECTED';
      tvBadge.className = s.firetv_connected ? 'badge online' : 'badge';

      if (s.queue) {{
        queueVal.textContent = `${{s.queue.queued_count}} / ${{s.queue.max_size}}`;
      }}
      if (s.model) {{
        modelVal.textContent = s.model.active_model || 'None (Burst Only)';
      }}
    }}

    // Refresh pending Sentinel cards
    const p = await apiCall('/api/sentinel/pending');
    if (p && p.requests) {{
      pendingCount.textContent = p.requests.length;
      if (p.requests.length === 0) {{
        pendingList.textContent = 'No pending approvals. Sovereign gate is clear.';
      }} else {{
        pendingList.innerHTML = '';
        p.requests.forEach(req => {{
          const div = document.createElement('div');
          div.className = 'sentinel-item';
          div.innerHTML = `
            <div style="display:flex; justify-content:space-between; font-weight:700; margin-bottom:4px;">
              <span>${{req.action_type}}</span>
              <span style="color:var(--accent-amber);">${{req.risk_level || 'HIGH'}}</span>
            </div>
            <div style="font-size:0.8rem; color:#cbd5e1;">Target: ${{req.target}}</div>
            <div style="font-size:0.75rem; color:#94a3b8;">ID: ${{req.id}}</div>
            <div style="font-size:0.75rem; color:var(--accent-red); margin-top:4px;">⚠️ Approval is final and cryptographically logged.</div>
            <div class="btn-row">
              <button class="action-btn btn-approve" onclick="resolveSentinel('${{req.id}}', true)">Approve</button>
              <button class="action-btn btn-deny" onclick="resolveSentinel('${{req.id}}', false)">Deny</button>
            </div>
          `;
          pendingList.appendChild(div);
        }});
      }}
    }}
  }}

  async function resolveSentinel(reqId, approved) {{
    const res = await apiCall('/api/sentinel/resolve', 'POST', {{ request_id: reqId, approved: approved }});
    if (res.status === 'approved' || res.status === 'rejected' || res.status === 'denied') {{
      refreshStatus();
    }} else if (res.error) {{
      showNotice(res.error, 'error');
    }}
  }}

  sanctuaryBtn.addEventListener('click', async () => {{
    const s = await apiCall('/api/ptt/status');
    if (s.sanctuary && s.sanctuary.is_active) {{
      await apiCall('/api/sanctuary/deactivate', 'POST');
    }} else {{
      await apiCall('/api/sanctuary/activate', 'POST', {{ reason: 'Console Emergency Button' }});
    }}
    refreshStatus();
  }});

  checkAuthRequirement();
  setInterval(refreshStatus, 3000);
  refreshStatus();
</script>
</body>
</html>
"""
