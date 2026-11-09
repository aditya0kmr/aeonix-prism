"""
ÆONIX PRISM // Sovereign POCO Operator Console Mobile UI
Standalone, zero-external-CDN HTML/CSS/JS interface for POCO Core Mind.
Provides:
1. Physical local review deck for Sentinel pending requests (R1-R4).
2. Action Digest cryptographic confirmation.
3. Passphrase verification challenge before consequential resolution.
4. Emergency Sanctuary / Killswitch toggle.
5. System telemetry & RAM guard live status.
"""

OPERATOR_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>ÆONIX PRISM // Operator Console</title>
  <style>
    :root {
      --bg: #0B1018;
      --surface: #151E2C;
      --surface-light: #1C2739;
      --border: #223147;
      --text: #F3F6FC;
      --text-muted: #8E9BAE;
      --accent: #72A0C1;
      --accent-glow: rgba(114, 160, 193, 0.2);
      --danger: #E05D52;
      --success: #4BB543;
      --warning: #F0A352;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      padding: 16px;
      font-size: 14px;
      line-height: 1.5;
    }
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--border);
      margin-bottom: 16px;
    }
    .brand {
      font-weight: 700;
      letter-spacing: 1px;
      font-size: 15px;
      color: var(--accent);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .badge {
      font-size: 10px;
      padding: 2px 6px;
      border-radius: 4px;
      background: var(--surface-light);
      border: 1px solid var(--border);
      color: var(--text-muted);
      text-transform: uppercase;
      font-weight: 600;
    }
    .badge-live {
      background: rgba(75, 181, 67, 0.15);
      border-color: var(--success);
      color: var(--success);
    }
    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px;
      margin-bottom: 14px;
    }
    .card-title {
      font-size: 12px;
      text-transform: uppercase;
      color: var(--text-muted);
      letter-spacing: 0.5px;
      margin-bottom: 8px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 8px 14px;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      border: 1px solid transparent;
      transition: all 0.15s ease;
      user-select: none;
    }
    .btn-primary { background: var(--accent); color: var(--bg); }
    .btn-danger { background: rgba(224, 93, 82, 0.15); border-color: var(--danger); color: var(--danger); }
    .btn-danger:active { background: var(--danger); color: #fff; }
    .btn-success { background: rgba(75, 181, 67, 0.15); border-color: var(--success); color: var(--success); }
    .btn-success:active { background: var(--success); color: #fff; }
    .btn-sm { padding: 4px 10px; font-size: 12px; }
    .btn-block { width: 100%; }
    .pending-item {
      background: var(--surface-light);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 12px;
      margin-bottom: 10px;
    }
    .item-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 6px;
    }
    .item-id { font-family: monospace; font-size: 11px; color: var(--text-muted); }
    .item-action { font-weight: 600; font-size: 13px; color: var(--text); }
    .item-digest {
      font-family: monospace;
      font-size: 10px;
      color: var(--accent);
      background: var(--bg);
      padding: 4px 6px;
      border-radius: 4px;
      margin: 6px 0;
      word-break: break-all;
    }
    .item-params {
      font-family: monospace;
      font-size: 11px;
      background: var(--bg);
      padding: 6px 8px;
      border-radius: 4px;
      color: var(--text-muted);
      overflow-x: auto;
      max-height: 80px;
      white-space: pre-wrap;
      margin-bottom: 10px;
    }
    .item-actions {
      display: flex;
      gap: 8px;
    }
    .status-row {
      display: flex;
      justify-content: space-between;
      padding: 6px 0;
      border-bottom: 1px solid rgba(255,255,255,0.05);
      font-size: 13px;
    }
    .status-row:last-child { border-bottom: none; }
    .modal-overlay {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,0.75);
      backdrop-filter: blur(2px);
      justify-content: center;
      align-items: center;
      padding: 16px;
      z-index: 100;
    }
    .modal {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
      width: 100%;
      max-width: 360px;
    }
    .input-field {
      width: 100%;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 10px;
      color: var(--text);
      font-size: 14px;
      margin: 10px 0 14px 0;
      outline: none;
    }
    .input-field:focus { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-glow); }
    .empty-state {
      text-align: center;
      padding: 24px 12px;
      color: var(--text-muted);
      font-size: 13px;
    }
  </style>
</head>
<body>

  <header>
    <div class="brand">
      <span>ÆONIX PRISM</span>
      <span class="badge">POCO CORE</span>
    </div>
    <span class="badge badge-live" id="sys-status-badge">ONLINE</span>
  </header>

  <!-- Sentinel Pending Action Approvals -->
  <div class="card">
    <div class="card-title">
      <span>Pending Consequential Actions (Sentinel)</span>
      <button class="btn btn-sm btn-primary" onclick="loadPending()">Refresh</button>
    </div>
    <div id="pending-list">
      <div class="empty-state">Loading pending actions...</div>
    </div>
  </div>

  <!-- System Telemetry & RAM Guard -->
  <div class="card">
    <div class="card-title">Controller Telemetry & Trust</div>
    <div class="status-row">
      <span style="color: var(--text-muted);">RAM Guard Budget</span>
      <span id="ram-budget">Checking...</span>
    </div>
    <div class="status-row">
      <span style="color: var(--text-muted);">Current Memory PSS</span>
      <span id="ram-pss">Checking...</span>
    </div>
    <div class="status-row">
      <span style="color: var(--text-muted);">Sanctuary Mode</span>
      <span id="sanctuary-status">Inactive</span>
    </div>
    <div style="margin-top: 12px; display: flex; gap: 8px;">
      <button class="btn btn-danger btn-sm btn-block" onclick="triggerSanctuary()">Emergency Stop</button>
    </div>
  </div>

  <!-- Modal for Passphrase Challenge -->
  <div class="modal-overlay" id="approval-modal">
    <div class="modal">
      <h3 style="margin-bottom: 8px; font-size: 15px;">Authorize Consequential Action</h3>
      <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 8px;" id="modal-desc"></p>
      <div class="item-digest" id="modal-digest"></div>
      <input type="password" id="modal-passphrase" class="input-field" placeholder="Enter Operator Passphrase" autocomplete="off" />
      <div style="display: flex; gap: 8px;">
        <button class="btn btn-primary btn-block" onclick="submitDecision(true)">Confirm Approval</button>
        <button class="btn btn-sm btn-block" style="background: var(--surface-light); color: var(--text);" onclick="closeModal()">Cancel</button>
      </div>
    </div>
  </div>

  <script>
    let activeRequestId = null;
    let activeDigest = null;

    async function loadPending() {
      try {
        const res = await fetch('/api/sentinel/pending');
        const data = await res.json();
        const list = document.getElementById('pending-list');
        
        if (!data.pending || data.pending.length === 0) {
          list.innerHTML = '<div class="empty-state">✓ No pending actions requiring operator authorization.</div>';
          return;
        }

        list.innerHTML = data.pending.map(item => {
          const reqId = item.id || item.request_id;
          const reqAction = item.action_type || item.action || 'Unknown';
          const reqDigest = item.action_digest || 'None';
          const reqParams = item.scope_json || item.params || '{}';
          const reqActor = item.agent || item.actor || 'unknown';
          return `
          <div class="pending-item">
            <div class="item-header">
              <span class="item-action">${escapeHtml(reqAction)}</span>
              <span class="badge" style="color: var(--warning); border-color: var(--warning);">${escapeHtml(item.risk_level || 'R3')}</span>
            </div>
            <div class="item-id">ID: ${escapeHtml(reqId)} • Actor: ${escapeHtml(reqActor)}</div>
            <div class="item-digest">Digest: ${escapeHtml(reqDigest)}</div>
            <div class="item-params">${escapeHtml(reqParams)}</div>
            <div class="item-actions">
              <button class="btn btn-success btn-sm btn-block" onclick="openApprovalModal('${reqId}', '${reqDigest}', '${escapeHtml(reqAction)}')">Authorize</button>
              <button class="btn btn-danger btn-sm btn-block" onclick="rejectAction('${reqId}')">Reject</button>
            </div>
          </div>
        `;}).join('');
      } catch (err) {
        document.getElementById('pending-list').innerHTML = `<div class="empty-state" style="color: var(--danger);">Error loading actions: ${err.message}</div>`;
      }
    }

    async function loadTelemetry() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        if (data.ram_guard) {
          document.getElementById('ram-budget').innerText = data.ram_guard.status || 'OK';
          document.getElementById('ram-pss').innerText = `${Math.round(data.ram_guard.current_pss_mb || 0)} MB / ${data.ram_guard.budget_mb || 1024} MB`;
        }
      } catch (e) {}
    }

    function openApprovalModal(reqId, digest, action) {
      activeRequestId = reqId;
      activeDigest = digest;
      document.getElementById('modal-desc').innerText = `Action: ${action}`;
      document.getElementById('modal-digest').innerText = digest || 'NO_DIGEST';
      document.getElementById('modal-passphrase').value = '';
      document.getElementById('approval-modal').style.display = 'flex';
      document.getElementById('modal-passphrase').focus();
    }

    function closeModal() {
      document.getElementById('approval-modal').style.display = 'none';
      activeRequestId = null;
      activeDigest = null;
    }

    async function submitDecision(approved) {
      const pass = document.getElementById('modal-passphrase').value;
      if (!pass) {
        alert('Passphrase is required to approve consequential actions.');
        return;
      }
      try {
        const res = await fetch('/api/sentinel/resolve', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer POCO_CORE_DEV_TOKEN_AETHERION'
          },
          body: JSON.stringify({
            request_id: activeRequestId,
            approved: true,
            action_digest: activeDigest,
            operator_passphrase: pass
          })
        });
        const result = await res.json();
        if (res.ok) {
          closeModal();
          loadPending();
        } else {
          alert(`Authorization Denied: ${result.error || 'Unknown error'}`);
        }
      } catch (e) {
        alert(`Error submitting decision: ${e.message}`);
      }
    }

    async function rejectAction(reqId) {
      if (!confirm(`Reject action ${reqId}?`)) return;
      try {
        const res = await fetch('/api/sentinel/resolve', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer POCO_CORE_DEV_TOKEN_AETHERION'
          },
          body: JSON.stringify({
            request_id: reqId,
            approved: false
          })
        });
        loadPending();
      } catch (e) {
        alert(e.message);
      }
    }

    async function triggerSanctuary() {
      if (!confirm('ENGAGE SANCTUARY / EMERGENCY STOP?\\nThis will revoke all active approvals and disconnect living surface links.')) return;
      try {
        await fetch('/api/sanctuary/activate', { method: 'POST' });
        alert('Sanctuary engaged.');
        loadPending();
      } catch (e) {
        alert(e.message);
      }
    }

    function escapeHtml(str) {
      if (!str) return '';
      return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    loadPending();
    loadTelemetry();
    setInterval(loadPending, 5000);
  </script>
</body>
</html>
"""
