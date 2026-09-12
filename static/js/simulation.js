/**
 * simulation.js - PC Mission Control & CAN Test Bench Controller
 * High-performance WebSocket synchronization with vehicle physics engine
 */

document.addEventListener('DOMContentLoaded', () => {
  let socket = null;
  let currentTelemetry = null;
  let activeFaults = new Set();
  let isAutoDriving = false;
  let autoDriveInterval = null;

  // ==================== 1. CLOCK TIMER ====================
  function updateClock() {
    const now = new Date();
    const clockEl = document.getElementById('sim-clock');
    if (clockEl) {
      clockEl.textContent = now.toTimeString().split(' ')[0];
    }
  }
  setInterval(updateClock, 1000);
  updateClock();

  // ==================== 2. WEBSOCKET PIPELINE ====================
  function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
      console.log('Connected to Vehicle Physics WebSocket Stream.');
      document.querySelector('#sim-ws-status .status-dot')?.classList.add('active');
      const statusText = document.querySelector('#sim-ws-status .status-text');
      if (statusText) statusText.textContent = 'Sim Engine Live (50 Hz)';
    };

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.type === 'telemetry') {
          currentTelemetry = payload.data;
          updateMissionControlHUD(payload.data, payload.can_bus);
        }
      } catch (err) {
        console.error('Error parsing WS frame:', err);
      }
    };

    socket.onclose = () => {
      document.querySelector('#sim-ws-status .status-dot')?.classList.remove('active');
      const statusText = document.querySelector('#sim-ws-status .status-text');
      if (statusText) statusText.textContent = 'Disconnected • Reconnecting...';
      setTimeout(connectWebSocket, 1500);
    };

    socket.onerror = (err) => {
      console.error('WebSocket Error:', err);
    };
  }

  function sendCommand(type, data) {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type, data }));
    }
  }

  connectWebSocket();

  // ==================== 3. TELEMETRY HUD & CAN SNIFFER UPDATES ====================
  function updateMissionControlHUD(t, can) {
    if (!t) return;

    // HUD metrics
    const speed = Math.round(t.speed_kmh || 0);
    setElText('hud-speed', speed);
    
    const soc = t.battery?.soc_pct !== undefined ? t.battery.soc_pct : 82.0;
    const volt = t.battery?.voltage_v !== undefined ? t.battery.voltage_v : 388.0;
    setElText('hud-soc', `${soc.toFixed(1)}%`);
    setElText('hud-pack-v', `${volt.toFixed(1)}V`);
    
    const powerKw = t.motor?.power_kw !== undefined ? t.motor.power_kw : 0.0;
    setElText('hud-power', powerKw.toFixed(1));
    
    const rpm = t.ice?.rpm !== undefined ? Math.round(t.ice.rpm) : 0;
    setElText('hud-rpm', rpm);
    
    const gear = t.gear || 'P';
    setElText('hud-gear', gear);
    
    const mode = t.drive_mode || 'COMFORT';
    setElText('hud-mode', mode);

    // Active faults count
    const dtcList = t.diagnostics?.active_dtcs || [];
    const countEl = document.getElementById('hud-fault-count');
    if (countEl) {
      countEl.textContent = `${dtcList.length} Active`;
      countEl.className = dtcList.length > 0 ? 'hud-val color-red' : 'hud-val color-green';
    }

    // DTC Console
    updateDtcConsole(dtcList);

    // CAN Bus Sniffer Table
    if (can) {
      updateCanSniffer(can);
    }
  }

  function setElText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  // ==================== 4. DTC CONSOLE ====================
  function updateDtcConsole(dtcList) {
    const container = document.getElementById('sim-dtc-container');
    const badgeCount = document.getElementById('dtc-badge-count');
    if (!container || !badgeCount) return;

    badgeCount.textContent = `${dtcList.length} CODES`;

    if (dtcList.length === 0) {
      container.innerHTML = '<div class="dtc-empty-message">✓ All vehicle ECUs reporting 0 fault codes. System nominal.</div>';
      return;
    }

    let html = '';
    dtcList.forEach(item => {
      html += `
        <div class="dtc-item-row">
          <span class="dtc-code-badge">${item.code || 'DTC'}</span>
          <span class="dtc-desc-text"><strong>${item.system || 'ECU'}:</strong> ${item.desc || 'Abnormal condition'}</span>
          <button class="btn-mitigate-dtc" onclick="window.mitigateFault('${item.code}')">Recalibrate & Fix</button>
        </div>
      `;
    });
    container.innerHTML = html;
  }

  window.mitigateFault = function(code) {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'reset_faults' }));
    }
    activeFaults.clear();
    document.querySelectorAll('.fault-button').forEach(btn => {
      btn.classList.remove('active');
      const pill = btn.querySelector('.fault-pill');
      if (pill) pill.textContent = 'NORMAL';
    });
    showToast(`Executed automated electronic calibration for ${code}. Fault cleared.`);
  };

  // ==================== 5. CAN BUS SNIFFER ====================
  function updateCanSniffer(can) {
    const stats = can.stats || {};
    const frames = can.latest_frames || {};

    setElText('sniff-bus-load', `${(stats.bus_load_pct || 18.5).toFixed(1)}%`);
    setElText('sniff-total-frames', (stats.total_frames_sent || 0).toLocaleString());

    const tbody = document.getElementById('sim-can-table-body');
    if (!tbody) return;

    let rowsHtml = '';
    for (const [idStr, frame] of Object.entries(frames)) {
      const signalsSummary = formatSignals(frame.signals || {});
      rowsHtml += `
        <tr>
          <td><span class="can-id-badge">${idStr}</span></td>
          <td><strong>${frame.name || 'UNKNOWN'}</strong></td>
          <td>${frame.ecu || 'ECU'}</td>
          <td>${frame.rate_hz || 50} Hz</td>
          <td class="can-signals-cell">${signalsSummary}</td>
        </tr>
      `;
    }
    tbody.innerHTML = rowsHtml;
  }

  function formatSignals(signals) {
    const items = [];
    for (const [k, v] of Object.entries(signals)) {
      const val = typeof v === 'number' ? (Number.isInteger(v) ? v : v.toFixed(2)) : v;
      items.push(`<span>${k}=<strong>${val}</strong></span>`);
    }
    return items.join(', ');
  }

  // ==================== 6. DRIVER CONTROLS & PEDALS ====================
  const sliderAccel = document.getElementById('sim-slider-accel');
  const sliderBrake = document.getElementById('sim-slider-brake');
  const readoutAccel = document.getElementById('readout-accel');
  const readoutBrake = document.getElementById('readout-brake');

  function applyDriverControls() {
    const accel = parseFloat(sliderAccel?.value || 0);
    const brake = parseFloat(sliderBrake?.value || 0);

    if (readoutAccel) readoutAccel.textContent = `${Math.round(accel)}%`;
    if (readoutBrake) readoutBrake.textContent = `${Math.round(brake)}%`;

    sendCommand('control', {
      accelerator: accel,
      brake: brake
    });
  }

  sliderAccel?.addEventListener('input', applyDriverControls);
  sliderBrake?.addEventListener('input', applyDriverControls);

  // Quick pedal buttons
  document.getElementById('btn-accel-zero')?.addEventListener('click', () => {
    if (sliderAccel) { sliderAccel.value = 0; applyDriverControls(); }
  });
  document.getElementById('btn-accel-50')?.addEventListener('click', () => {
    if (sliderAccel) { sliderAccel.value = 50; applyDriverControls(); }
  });
  document.getElementById('btn-accel-100')?.addEventListener('click', () => {
    if (sliderAccel) { sliderAccel.value = 100; applyDriverControls(); }
  });

  document.getElementById('btn-brake-zero')?.addEventListener('click', () => {
    if (sliderBrake) { sliderBrake.value = 0; applyDriverControls(); }
  });
  document.getElementById('btn-brake-50')?.addEventListener('click', () => {
    if (sliderBrake) { sliderBrake.value = 50; applyDriverControls(); }
  });
  document.getElementById('btn-brake-100')?.addEventListener('click', () => {
    if (sliderBrake) { sliderBrake.value = 100; applyDriverControls(); }
    if (sliderAccel) { sliderAccel.value = 0; applyDriverControls(); }
    showToast('Emergency Stop Activated!');
  });

  // Gear Shift buttons
  const gearBtns = document.querySelectorAll('.btn-sim-gear');
  gearBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      gearBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const gear = btn.dataset.gear;
      sendCommand('control', { gear: gear });
      showToast(`Shifted Transmission to ${gear}`);
    });
  });

  // Mode buttons
  const modeBtns = document.querySelectorAll('.btn-sim-mode');
  modeBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      modeBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const mode = btn.dataset.mode;
      sendCommand('control', { drive_mode: mode });
      showToast(`Drive Mode changed to ${mode}`);
    });
  });

  // Regen buttons
  const regenBtns = document.querySelectorAll('.btn-sim-regen');
  regenBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      regenBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const regen = parseInt(btn.dataset.regen, 10);
      sendCommand('control', { regen_setting: regen });
      showToast(`Regen level set to ${regen}`);
    });
  });

  // Keyboard driving controls
  document.addEventListener('keydown', (e) => {
    if (['input', 'textarea'].includes(document.activeElement?.tagName.toLowerCase())) return;

    if (e.key === 'w' || e.key === 'ArrowUp') {
      if (sliderAccel) {
        sliderAccel.value = Math.min(100, parseInt(sliderAccel.value, 10) + 10);
        applyDriverControls();
      }
    } else if (e.key === 's' || e.key === 'ArrowDown') {
      if (sliderBrake) {
        sliderBrake.value = Math.min(100, parseInt(sliderBrake.value, 10) + 15);
        applyDriverControls();
      }
    } else if (e.code === 'Space') {
      e.preventDefault();
      if (sliderBrake) {
        sliderBrake.value = 100;
        if (sliderAccel) sliderAccel.value = 0;
        applyDriverControls();
        showToast('Emergency Stop (Spacebar)');
      }
    } else if (['p', 'r', 'n', 'd', 'b'].includes(e.key.toLowerCase())) {
      const g = e.key.toUpperCase();
      const targetBtn = document.querySelector(`.btn-sim-gear[data-gear="${g}"]`);
      targetBtn?.click();
    }
  });

  // Auto-Drive Cycle
  const btnAutoDrive = document.getElementById('btn-sim-auto-drive');
  btnAutoDrive?.addEventListener('click', () => {
    isAutoDriving = !isAutoDriving;
    if (isAutoDriving) {
      btnAutoDrive.classList.add('active');
      btnAutoDrive.textContent = '⏹ Stop Auto-Drive Cycle';
      showToast('Starting automated WLTP highway/city profile...');

      // Ensure gear is Drive
      const driveGearBtn = document.querySelector('.btn-sim-gear[data-gear="D"]');
      driveGearBtn?.click();

      let simStep = 0;
      autoDriveInterval = setInterval(() => {
        simStep++;
        const speed = currentTelemetry?.speed_kmh || 0;
        let targetThrottle = 0;
        let targetBrake = 0;

        const cyclePhase = Math.floor((simStep % 300) / 50);
        if (cyclePhase === 0) { // Accelerate to 40 km/h (City)
          targetThrottle = speed < 40 ? 45 : 10;
        } else if (cyclePhase === 1) { // Cruise 40-50 km/h
          targetThrottle = speed < 48 ? 20 : 5;
        } else if (cyclePhase === 2) { // Highway blast to 90 km/h
          targetThrottle = speed < 90 ? 75 : 25;
        } else if (cyclePhase === 3) { // High speed cruise
          targetThrottle = speed < 95 ? 30 : 10;
        } else if (cyclePhase === 4) { // Slow down at light
          targetThrottle = 0;
          targetBrake = speed > 5 ? 35 : 5;
        } else { // Idle at red light
          targetThrottle = 0;
          targetBrake = 20;
        }

        if (sliderAccel) sliderAccel.value = targetThrottle;
        if (sliderBrake) sliderBrake.value = targetBrake;
        applyDriverControls();
      }, 200);

    } else {
      btnAutoDrive.classList.remove('active');
      btnAutoDrive.textContent = '▶ Start Auto-Drive Cycle';
      clearInterval(autoDriveInterval);
      if (sliderAccel) sliderAccel.value = 0;
      if (sliderBrake) sliderBrake.value = 0;
      applyDriverControls();
      showToast('Auto-Drive cycle stopped.');
    }
  });

  // ==================== 7. FAULT INJECTION SWITCHBOARD ====================
  const faultButtons = document.querySelectorAll('.fault-button');
  faultButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const fault = btn.dataset.fault;
      const isCurrentlyActive = activeFaults.has(fault);
      const newEnabled = !isCurrentlyActive;

      if (newEnabled) {
        activeFaults.add(fault);
        btn.classList.add('active');
        const pill = btn.querySelector('.fault-pill');
        if (pill) pill.textContent = 'FAULT ACTIVE';
      } else {
        activeFaults.delete(fault);
        btn.classList.remove('active');
        const pill = btn.querySelector('.fault-pill');
        if (pill) pill.textContent = 'NORMAL';
      }

      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({
          type: 'fault_inject',
          fault: fault,
          enabled: newEnabled
        }));
      }

      showToast(`${fault.toUpperCase()}: ${newEnabled ? 'Injected ⚠️' : 'Cleared ✓'}`);
    });
  });

  // Master Reset All Faults
  const btnResetFaults = document.getElementById('btn-reset-all-faults');
  btnResetFaults?.addEventListener('click', () => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'reset_faults' }));
    }
    activeFaults.clear();
    faultButtons.forEach(btn => {
      btn.classList.remove('active');
      const pill = btn.querySelector('.fault-pill');
      if (pill) pill.textContent = 'NORMAL';
    });
    showToast('All safety faults reset. Vehicle ECUs restored to nominal.');
  });

  // ==================== 8. TOAST NOTIFICATIONS ====================
  function showToast(msg) {
    const toast = document.getElementById('sim-toast');
    if (!toast) return;
    toast.textContent = msg;
    toast.classList.add('show');
    setTimeout(() => {
      toast.classList.remove('show');
    }, 2800);
  }

});
