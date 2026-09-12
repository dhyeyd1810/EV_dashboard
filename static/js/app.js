/**
 * app.js - Main Client Controller & Telemetry Dispatcher
 * Clean, emoji-free, accessible presentation for both general drivers and technical reviewers.
 */

document.addEventListener('DOMContentLoaded', () => {
  // 1. Initialize Speedometer Canvas
  const speedo = new CyberSpeedometer('speedo-canvas');

  // 2. Setup 96-Cell BMS Grid
  const cellGridContainer = document.getElementById('cell-grid-96');
  if (cellGridContainer) {
    for (let i = 1; i <= 96; i++) {
      const cellEl = document.createElement('div');
      cellEl.className = 'cell-block';
      cellEl.id = `bms-cell-${i}`;
      cellEl.innerHTML = `
        <span class="cell-num">C${i}</span>
        <span class="cell-v">3.92V</span>
      `;
      cellGridContainer.appendChild(cellEl);
    }
  }

  // 3. Navigation View Switcher Tabs
  const navTabs = document.querySelectorAll('.nav-tab');
  const panels = document.querySelectorAll('.view-panel');

  navTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      navTabs.forEach(t => t.classList.remove('active'));
      panels.forEach(p => p.classList.remove('active'));

      tab.classList.add('active');
      const targetId = `panel-${tab.dataset.tab}`;
      const targetPanel = document.getElementById(targetId);
      if (targetPanel) targetPanel.classList.add('active');
    });
  });

  // 4. Controls & Fault Drawer Toggle & Fullscreen
  const drawer = document.getElementById('controls-drawer');
  const btnToggleControls = document.getElementById('btn-toggle-controls');
  const btnCloseDrawer = document.getElementById('btn-close-drawer');
  const btnFullscreen = document.getElementById('btn-fullscreen');

  btnToggleControls?.addEventListener('click', () => drawer?.classList.toggle('open'));
  btnCloseDrawer?.addEventListener('click', () => drawer?.classList.remove('open'));

  btnFullscreen?.addEventListener('click', () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(err => {
        console.warn('Fullscreen request failed:', err);
      });
      btnFullscreen.textContent = '✕ Exit Fullscreen';
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen();
      }
      btnFullscreen.textContent = '⛶ Fullscreen';
    }
  });

  document.addEventListener('fullscreenchange', () => {
    if (btnFullscreen) {
      btnFullscreen.textContent = document.fullscreenElement ? '✕ Exit Fullscreen' : '⛶ Fullscreen';
    }
  });

  // 5. System Clock Timer
  function updateClock() {
    const now = new Date();
    const clockEl = document.getElementById('system-time');
    if (clockEl) {
      clockEl.textContent = now.toTimeString().split(' ')[0];
    }
  }
  setInterval(updateClock, 1000);
  updateClock();

  // 6. WebSocket Telemetry Pipeline
  let socket = null;
  let isAutoDriving = false;

  function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
      console.log('Connected to Vehicle Telemetry stream.');
      document.querySelector('.status-dot')?.classList.add('active');
    };

    socket.onmessage = (event) => {
      try {
        const payload = jsonParseSafe(event.data);
        if (payload.type === 'telemetry') {
          updateDashboard(payload.data, payload.can_bus);
        }
      } catch (err) {
        console.error('Error processing telemetry frame:', err);
      }
    };

    socket.onclose = () => {
      document.querySelector('.status-dot')?.classList.remove('active');
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

  function jsonParseSafe(str) {
    try { return JSON.parse(str); } catch { return {}; }
  }

  // Modal Elements and State
  let lastReportedDtcCode = null;
  let isModalOpen = false;

  const modalOverlay = document.getElementById('alert-modal-overlay');
  const modalTitle = document.getElementById('modal-error-title');
  const modalDesc = document.getElementById('modal-error-desc');
  const modalSystem = document.getElementById('modal-affected-system');
  const modalDtc = document.getElementById('modal-dtc-code');
  const modalAction = document.getElementById('modal-action-text');
  const btnModalFix = document.getElementById('btn-modal-fix');
  const btnModalClose = document.getElementById('btn-modal-close');
  const btnModalDismiss = document.getElementById('btn-modal-dismiss');

  function showIncidentModal(issue) {
    if (!modalOverlay || isModalOpen) return;
    isModalOpen = true;
    if (modalTitle) modalTitle.textContent = issue.title;
    if (modalDesc) modalDesc.textContent = issue.desc;
    if (modalSystem) modalSystem.textContent = issue.system;
    if (modalDtc) modalDtc.textContent = issue.dtc || 'Diagnostic Alert';
    if (modalAction) modalAction.textContent = issue.action || 'Run Automated Electronic Fix';
    modalOverlay.classList.add('active');
  }

  function hideIncidentModal() {
    if (!modalOverlay) return;
    modalOverlay.classList.remove('active');
    isModalOpen = false;
  }

  btnModalDismiss?.addEventListener('click', hideIncidentModal);
  btnModalClose?.addEventListener('click', hideIncidentModal);

  btnModalFix?.addEventListener('click', () => {
    btnModalFix.textContent = 'Permission Granted! Applying Fix...';
    
    // Trigger reset faults on the backend
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'reset_faults' }));
    }

    // Reset drawer fault buttons
    document.querySelectorAll('.btn-fault').forEach(b => b.classList.remove('active'));

    setTimeout(() => {
      btnModalFix.textContent = 'Fault Cleared & Systems Restored!';
      setTimeout(() => {
        hideIncidentModal();
        btnModalFix.textContent = '✓ Grant Permission & Fix Issue';
        lastReportedDtcCode = null;
      }, 700);
    }, 600);
  });

  function getFriendlyIssueDetails(dtc) {
    const code = dtc.code || '';
    if (code === 'P0A80' || dtc.desc?.includes('Battery') || dtc.desc?.includes('Cell')) {
      return {
        title: 'Battery Temperature / Cell Imbalance Alert',
        desc: 'The high-voltage lithium battery pack reported elevated temperature or abnormal cell variance. System is limiting power to protect battery health.',
        system: 'High-Voltage Battery Management (BMS)',
        dtc: dtc.code || 'P0A80',
        action: 'Activate Coolant Chiller Loop & Rebalance Cell Voltages'
      };
    } else if (code === 'C0035' || dtc.desc?.includes('Tire') || dtc.desc?.includes('Pressure')) {
      return {
        title: 'Tire Pressure Critical Alert',
        desc: 'One of the vehicle tires has dropped below safe driving pressure (< 22 PSI). Immediate tire inflation or repair is recommended.',
        system: 'Tire Pressure Monitoring System (TPMS)',
        dtc: dtc.code || 'C0035',
        action: 'Re-inflate to 35 PSI & Calibrate Pressure Sensor'
      };
    } else if (code === 'P0117' || dtc.desc?.includes('Coolant') || dtc.desc?.includes('Overheat')) {
      return {
        title: 'Engine Coolant Overheating Alert',
        desc: 'Gasoline engine coolant temperature has reached 115°C. The engine is throttled to prevent overheating damage.',
        system: 'Engine Thermal & Radiator Loop',
        dtc: dtc.code || 'P0117',
        action: 'Turn Radiator Fans to 100% & Open Thermostat Valve'
      };
    } else if (code === 'P0A78' || dtc.desc?.includes('Inverter')) {
      return {
        title: 'Electric Inverter Overheat Alert',
        desc: 'The electric motor 3-phase power inverter has exceeded normal thermal limits (> 95°C).',
        system: 'Electric Motor & Inverter Drive',
        dtc: dtc.code || 'P0A78',
        action: 'Derate Motor Torque & Increase Coolant Pump Flow'
      };
    } else if (code === 'P0300' || dtc.desc?.includes('Misfire')) {
      return {
        title: 'Engine Cylinder Misfire Detected',
        desc: 'A misfire was detected in the gasoline engine cylinders, reducing engine power output.',
        system: '1.5L Turbo Gasoline Engine (ICE)',
        dtc: dtc.code || 'P0300',
        action: 'Reset Fuel Injection Mapping & Clear Cylinder Code'
      };
    } else if (code === 'B1049' || dtc.desc?.includes('Radar')) {
      return {
        title: 'Forward Safety Radar Sensor Obstructed',
        desc: 'The forward radar camera is unable to detect vehicles ahead. Automatic collision warning is paused.',
        system: 'Active Driver Assistance (ADAS)',
        dtc: dtc.code || 'B1049',
        action: 'Run Sensor Optical Self-Check & Diagnostic Reset'
      };
    } else {
      return {
        title: dtc.desc || 'Vehicle Warning Detected',
        desc: 'A vehicle diagnostic code was triggered. Automated calibration can restore nominal operating parameters.',
        system: dtc.system || 'Powertrain Computer',
        dtc: dtc.code || 'DTC Alert',
        action: 'Clear Fault Code & Restore Safe Mode'
      };
    }
  }

  // Friendly mode description mappings
  const modeDescriptions = {
    'PURE_EV': 'Pure Electric (0-40 km/h: 100% Battery)',
    'SERIES_HYBRID': 'Series Hybrid (Engine Generating Electricity)',
    'PARALLEL_HYBRID': 'Hybrid Split (40-80 km/h: 50% Motor + 50% Engine)',
    'ENGINE_DIRECT': 'Fuel Direct (>80 km/h: Engine Cruising)',
    'REGEN_BRAKING': 'Regen Braking (Energy Recovery)'
  };

  const driveModeNames = {
    'ECO': 'Eco (Fuel Saver)',
    'COMFORT': 'Comfort',
    'SPORT': 'Sport',
    'EV_HOLD': 'Battery Save',
    'TRACK': 'Performance Track',
    'LIMP_HOME': 'Safe Limp Mode'
  };

  const regenLevelNames = {
    0: 'Off',
    1: 'Low (1)',
    2: 'Medium (2)',
    3: 'One-Pedal (3)'
  };

  // 7. Update Dashboard DOM from Telemetry Snapshot
  function updateDashboard(t, canData) {
    if (!t) return;

    // --- A. Speed & Dynamics ---
    const speedKmh = Math.round(t.speed_kmh || 0);
    if (speedo) speedo.setSpeed(speedKmh);
    setText('disp-speed-kmh', speedKmh);
    setText('disp-odometer', (t.odometer_km || 0).toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 }));
    setText('disp-drive-mode', driveModeNames[t.drive_mode] || t.drive_mode || 'Comfort');
    setText('disp-regen-badge', regenLevelNames[t.regen_setting] || 'Medium (2)');

    // Powertrain description below speedometer
    const ptDesc = modeDescriptions[t.powertrain_mode] || 'Ready to Drive';
    setText('disp-powertrain-desc', speedKmh === 0 && t.gear === 'PARK' ? 'Vehicle Parked & Ready' : ptDesc);
    setText('powertrain-mode-badge', (t.powertrain_mode || 'PURE_EV').replace('_', ' '));
    setText('disp-flow-status', ptDesc);

    // Gear Indicator
    const currentGear = (t.gear || 'P').toLowerCase();
    document.querySelectorAll('.gear-btn').forEach(btn => {
      btn.classList.toggle('active', btn.id === `gear-${currentGear}`);
    });

    // --- B. Energy Reservoirs & Range ---
    const soc = t.battery?.soc_pct || 0;
    setText('disp-soc-pct', `${Math.round(soc)}%`);
    setWidth('bar-battery-soc', `${soc}%`);
    setText('disp-pack-v', (t.battery?.voltage_v || 0).toFixed(1));
    setText('disp-pack-a', (t.battery?.current_a || 0).toFixed(1));
    setText('disp-pack-temp', (t.battery?.temp_avg_c || 0).toFixed(1));

    const fuelPct = t.ice?.fuel_level_pct || 0;
    setText('disp-fuel-pct', `${Math.round(fuelPct)}%`);
    setWidth('bar-fuel-level', `${fuelPct}%`);
    setText('disp-fuel-litres', (t.ice?.fuel_level_l || 0).toFixed(1));
    setText('disp-fuel-flow', (t.ice?.fuel_flow_lph || 0).toFixed(1));
    setText('disp-avg-fuel', (t.ice?.avg_consumption || 0).toFixed(1));

    setText('disp-ev-range', Math.round(t.range?.ev_range_km || 0));
    setText('disp-fuel-range', Math.round(t.range?.fuel_range_km || 0));
    setText('disp-total-range', Math.round(t.range?.total_range_km || 0));

    // --- C. Power Flow Meter ---
    const motorKw = t.motor?.power_kw || 0;
    setText('disp-motor-kw', (motorKw >= 0 ? `+${motorKw.toFixed(1)} kW` : `${motorKw.toFixed(1)} kW`));
    if (motorKw < 0) {
      setWidth('bar-regen-fill', `${Math.min(100, Math.abs(motorKw) / 65 * 100)}%`);
      setWidth('bar-power-fill', '0%');
    } else {
      setWidth('bar-regen-fill', '0%');
      setWidth('bar-power-fill', `${Math.min(100, motorKw / 135 * 100)}%`);
    }

    const iceRpm = Math.round(t.ice?.rpm || 0);
    setText('disp-ice-rpm', `${iceRpm} RPM`);
    setWidth('bar-tacho-rpm', `${Math.min(100, (iceRpm / 6500) * 100)}%`);
    setText('disp-ice-temp', (t.ice?.coolant_temp_c || 0).toFixed(1));

    const iceStateDesc = t.ice?.state === 2 ? 'Running (Providing Power)' : (t.ice?.state === 3 ? 'Idle' : 'Off (Saving Fuel)');
    setText('disp-ice-state-text', iceStateDesc);

    // Power Split Ratio
    const evSplit = Math.round(t.power_split_ratio || 100);
    setWidth('split-ev-bar', `${evSplit}%`);
    setWidth('split-ice-bar', `${100 - evSplit}%`);
    setText('split-ev-bar', `Battery ${evSplit}%`);
    setText('split-ice-bar', `${100 - evSplit}% Fuel`);

    // Car Flow Lines
    const flowEv = document.getElementById('flow-batt-motor');
    const flowIce = document.getElementById('flow-ice-batt');
    if (flowEv) flowEv.classList.toggle('active', Math.abs(motorKw) > 0.5);
    if (flowIce) flowIce.classList.toggle('active', (t.ice?.power_kw || 0) > 1.0);

    // --- D. ADAS & Radar ---
    const radarDist = t.chassis?.radar_dist_m || 999;
    setText('radar-dist-text', `Distance: ${radarDist.toFixed(1)}m`);
    setText('adas-dist', `${radarDist.toFixed(1)} m`);

    const blindL = document.getElementById('radar-blind-l');
    const blindR = document.getElementById('radar-blind-r');
    if (blindL) blindL.classList.toggle('active', !!t.chassis?.blindspot_l);
    if (blindR) blindR.classList.toggle('active', !!t.chassis?.blindspot_r);

    setText('adas-bs-l', t.chassis?.blindspot_l ? 'Vehicle Detected' : 'Clear');
    setText('adas-bs-r', t.chassis?.blindspot_r ? 'Vehicle Detected' : 'Clear');
    setText('adas-ldw', t.chassis?.lane_warning ? 'Drift Warning' : 'In Lane');

    // Pop-up Safety Incident Check
    if (t.diagnostics?.active_dtcs && t.diagnostics.active_dtcs.length > 0) {
      const primaryIssue = t.diagnostics.active_dtcs[0];
      const issueKey = primaryIssue.code || primaryIssue.desc;

      if (issueKey !== lastReportedDtcCode && !isModalOpen) {
        lastReportedDtcCode = issueKey;
        const details = getFriendlyIssueDetails(primaryIssue);
        showIncidentModal(details);
      }
    } else if (lastReportedDtcCode && (!t.diagnostics?.active_dtcs || t.diagnostics.active_dtcs.length === 0)) {
      lastReportedDtcCode = null;
      if (isModalOpen) hideIncidentModal();
    }

    // Cockpit notification banner
    const diagBanner = document.getElementById('cockpit-diag-banner');
    if (diagBanner) {
      if (t.diagnostics?.active_dtcs && t.diagnostics.active_dtcs.length > 0) {
        diagBanner.classList.add('warning-mode');
        diagBanner.innerHTML = `<span class="alert-indicator"></span><span class="alert-text">${t.diagnostics.active_dtcs.length} Issue(s) Detected - Click to Fix</span>`;
        diagBanner.style.cursor = 'pointer';
        diagBanner.onclick = () => {
          if (t.diagnostics.active_dtcs.length > 0) {
            showIncidentModal(getFriendlyIssueDetails(t.diagnostics.active_dtcs[0]));
          }
        };
      } else {
        diagBanner.classList.remove('warning-mode');
        diagBanner.innerHTML = `<span class="alert-indicator"></span><span class="alert-text">All Vehicle Systems Operating Normally</span>`;
        diagBanner.style.cursor = 'default';
        diagBanner.onclick = null;
      }
    }

    // --- E. 96-Cell BMS Grid Update ---
    if (t.battery?.cell_voltages) {
      const baseV = t.battery.voltage_v / 96.0;
      let minV = 5.0, maxV = 0.0;

      for (let i = 1; i <= 96; i++) {
        const cellEl = document.getElementById(`bms-cell-${i}`);
        if (cellEl) {
          const v = (i === 42 && t.diagnostics?.active_dtcs?.some(d => d.code === 'P0A80' || d.desc.includes('Cell'))) 
            ? 3.12 
            : (baseV + Math.sin(i * 0.3) * 0.005);
          
          if (v < minV) minV = v;
          if (v > maxV) maxV = v;

          const vText = cellEl.querySelector('.cell-v');
          if (vText) vText.textContent = `${v.toFixed(2)}V`;

          cellEl.classList.toggle('cell-fault', v < 3.4);
        }
      }

      setText('bms-soc-large', `${soc.toFixed(1)}%`);
      setText('bms-soh-large', `${(t.battery.soh_pct || 98.2).toFixed(1)}%`);
      setText('bms-vi-large', `${t.battery.voltage_v.toFixed(1)}V / ${t.battery.current_a.toFixed(1)}A`);
      setText('bms-iso-large', `${(t.battery.isolation_kohm || 3200).toLocaleString()} kOhm`);
      setText('bms-cell-delta', `${(maxV - minV).toFixed(3)} V`);
    }

    // --- F. Powertrain Tab ---
    setText('pt-motor-rpm', `${Math.round(t.motor?.rpm || 0)} RPM`);
    setText('pt-motor-torque', `${(t.motor?.torque_nm || 0).toFixed(1)} Nm`);
    setText('pt-motor-power', `${(t.motor?.power_kw || 0).toFixed(1)} kW`);
    setText('pt-inverter-eff', `${(t.motor?.efficiency_pct || 95).toFixed(1)}%`);
    setText('pt-motor-temp', `${(t.motor?.motor_temp_c || 38).toFixed(1)} °C`);
    setText('pt-inv-temp', `${(t.motor?.inverter_temp_c || 42).toFixed(1)} °C`);

    setText('pt-ice-state', iceStateDesc);
    setText('pt-ice-rpm', `${Math.round(t.ice?.rpm || 0)} RPM`);
    setText('pt-ice-torque', `${(t.ice?.torque_nm || 0).toFixed(1)} Nm`);
    setText('pt-ice-power', `${(t.ice?.power_kw || 0).toFixed(1)} kW`);
    setText('pt-ice-coolant', `${(t.ice?.coolant_temp_c || 88).toFixed(1)} °C`);
    setText('pt-ice-fuel-rate', `${(t.ice?.fuel_flow_lph || 0).toFixed(2)} L/hour`);

    // HCU Mode Highlight
    const currentMode = t.powertrain_mode || 'PURE_EV';
    document.querySelectorAll('.hcu-mode-box').forEach(b => b.classList.remove('active-mode'));
    if (currentMode === 'PURE_EV') document.getElementById('hcu-box-ev')?.classList.add('active-mode');
    else if (currentMode === 'SERIES_HYBRID') document.getElementById('hcu-box-series')?.classList.add('active-mode');
    else if (currentMode === 'PARALLEL_HYBRID') document.getElementById('hcu-box-parallel')?.classList.add('active-mode');
    else if (currentMode === 'ENGINE_DIRECT') document.getElementById('hcu-box-direct')?.classList.add('active-mode');
    else if (currentMode === 'REGEN_BRAKING') document.getElementById('hcu-box-regen')?.classList.add('active-mode');

    // --- G. Thermal Tab ---
    setText('th-flow-rate', `${(t.thermal?.battery_coolant_flow_lpm || 12).toFixed(1)} L/min`);
    setText('th-coolant-temp', `${(t.thermal?.battery_coolant_temp_c || 25).toFixed(1)} °C`);
    setText('th-batt-temp', `${(t.battery?.temp_avg_c || 28.6).toFixed(1)} °C`);
    setText('th-ice-coolant-2', `${(t.ice?.coolant_temp_c || 88).toFixed(1)} °C`);
    setText('th-fan-pct', `${Math.round(t.thermal?.radiator_fan_pct || 25)} %`);
    setText('th-cabin-temp', `${(t.thermal?.cabin_temp_c || 22.5).toFixed(1)} °C`);
    setText('th-cabin-target', `${(t.thermal?.target_temp_c || 21.0).toFixed(1)} °C`);
    setText('th-hvac-power', `${(t.thermal?.hvac_power_kw || 1.2).toFixed(1)} kW`);
    setText('th-ambient-temp', `${(t.thermal?.ambient_temp_c || 24.0).toFixed(1)} °C`);

    // --- H. TPMS Tab ---
    const tires = t.chassis?.tires || {};
    setText('tpms-fl-psi', `${(tires.fl_psi || 35).toFixed(1)} PSI`);
    setText('tpms-fr-psi', `${(tires.fr_psi || 35).toFixed(1)} PSI`);
    setText('tpms-rl-psi', `${(tires.rl_psi || 35).toFixed(1)} PSI`);
    setText('tpms-rr-psi', `${(tires.rr_psi || 35).toFixed(1)} PSI`);

    setText('tpms-fl-temp', `${(tires.fl_temp || 32).toFixed(1)} °C`);
    setText('tpms-fr-temp', `${(tires.fr_temp || 32).toFixed(1)} °C`);
    setText('tpms-rl-temp', `${(tires.rl_temp || 32).toFixed(1)} °C`);
    setText('tpms-rr-temp', `${(tires.rr_temp || 32).toFixed(1)} °C`);

    const isFlLeak = tires.fl_psi < 24.0;
    document.getElementById('tpms-fl')?.classList.toggle('tpms-alert', isFlLeak);
    document.getElementById('tire-fl-glyph')?.classList.toggle('tire-fault', isFlLeak);

    // --- I. Active DTC list in Drawer ---
    const dtcListContainer = document.getElementById('drawer-dtc-list');
    if (dtcListContainer && t.diagnostics?.active_dtcs) {
      if (t.diagnostics.active_dtcs.length === 0) {
        dtcListContainer.innerHTML = `<div class="no-dtc">All vehicle computers reporting 0 issues.</div>`;
      } else {
        dtcListContainer.innerHTML = t.diagnostics.active_dtcs.map(dtc => `
          <div class="dtc-item">
            <span class="dtc-code">[${dtc.code}]</span>
            <span class="dtc-desc">${dtc.desc}</span>
          </div>
        `).join('');
      }
    }

    // --- J. CAN Bus Table & Metrics ---
    if (canData) {
      setText('can-total-frames', (canData.stats?.total_frames || 0).toLocaleString());
      setText('can-bus-load', `${canData.stats?.bus_load_pct || 18.5}%`);

      const tableBody = document.getElementById('can-frames-table-body');
      if (tableBody && canData.latest_frames) {
        tableBody.innerHTML = Object.values(canData.latest_frames).map(f => `
          <tr>
            <td><strong>${f.id}</strong></td>
            <td>${f.name.replace(/_/g, ' ')}</td>
            <td>${f.sender.replace(/_/g, ' ')}</td>
            <td>20ms</td>
            <td><code>${JSON.stringify(f.data)}</code></td>
          </tr>
        `).join('');
      }
    }
  }

  function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  }

  function setWidth(id, val) {
    const el = document.getElementById(id);
    if (el) el.style.width = val;
  }

  function setTelltale(id, condition, type) {
    const el = document.getElementById(id);
    if (el) {
      el.classList.toggle(`active-${type}`, !!condition);
    }
  }

  // 8. Driver Controls & Sliders
  const sliderAccel = document.getElementById('slider-accel');
  const sliderBrake = document.getElementById('slider-brake');

  sliderAccel?.addEventListener('input', (e) => {
    const val = e.target.value;
    setText('val-accel-slider', `${val}%`);
    sendCommand('control', { accelerator: val });
  });

  sliderBrake?.addEventListener('input', (e) => {
    const val = e.target.value;
    setText('val-brake-slider', `${val}%`);
    sendCommand('control', { brake: val });
  });

  // Gear Buttons
  document.querySelectorAll('.btn-gear').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.btn-gear').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      sendCommand('control', { gear: btn.dataset.gear });
    });
  });

  // Drive Mode Buttons
  document.querySelectorAll('.btn-mode').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.btn-mode').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      sendCommand('control', { drive_mode: btn.dataset.mode });
    });
  });

  // Regen Buttons
  document.querySelectorAll('.btn-regen').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.btn-regen').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      sendCommand('control', { regen_setting: parseInt(btn.dataset.regen) });
    });
  });

  // Auto Drive Cycle Toggle
  const btnAutoDrive = document.getElementById('btn-auto-drive');
  btnAutoDrive?.addEventListener('click', () => {
    isAutoDriving = !isAutoDriving;
    btnAutoDrive.classList.toggle('active', isAutoDriving);
    btnAutoDrive.textContent = isAutoDriving ? 'Stop Automatic Driving' : 'Start Automatic Driving Profile';
    sendCommand('control', { auto_drive: isAutoDriving });
  });

  // Fault Injection Buttons
  const activeFaults = new Set();
  document.querySelectorAll('.btn-fault').forEach(btn => {
    btn.addEventListener('click', () => {
      const faultName = btn.dataset.fault;
      const isCurrentlyActive = activeFaults.has(faultName);

      if (isCurrentlyActive) {
        activeFaults.delete(faultName);
        btn.classList.remove('active');
        if (socket) socket.send(JSON.stringify({ type: 'fault_inject', fault: faultName, enabled: false }));
      } else {
        activeFaults.add(faultName);
        btn.classList.add('active');
        if (socket) socket.send(JSON.stringify({ type: 'fault_inject', fault: faultName, enabled: true }));
      }
    });
  });

  // Reset All Faults Button
  const btnResetFaults = document.getElementById('btn-reset-all-faults');
  btnResetFaults?.addEventListener('click', () => {
    activeFaults.clear();
    document.querySelectorAll('.btn-fault').forEach(b => b.classList.remove('active'));
    if (socket) socket.send(JSON.stringify({ type: 'reset_faults' }));
  });

  // 9. Keyboard Driving Controls (WASD / Arrows)
  let keyAccel = 0;
  let keyBrake = 0;

  window.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT') return;

    if (e.key === 'ArrowUp' || e.key === 'w' || e.key === 'W') {
      keyAccel = Math.min(100, keyAccel + 15);
      keyBrake = 0;
      if (sliderAccel) { sliderAccel.value = keyAccel; setText('val-accel-slider', `${keyAccel}%`); }
      sendCommand('control', { accelerator: keyAccel, brake: 0 });
    } else if (e.key === 'ArrowDown' || e.key === 's' || e.key === 'S') {
      keyBrake = Math.min(100, keyBrake + 25);
      keyAccel = 0;
      if (sliderBrake) { sliderBrake.value = keyBrake; setText('val-brake-slider', `${keyBrake}%`); }
      sendCommand('control', { brake: keyBrake, accelerator: 0 });
    } else if (e.key === ' ' || e.code === 'Space') {
      sendCommand('control', { brake: 100, accelerator: 0 });
    } else if (['p', 'r', 'n', 'd', 'b'].includes(e.key.toLowerCase())) {
      sendCommand('control', { gear: e.key.toUpperCase() });
    }
  });

  window.addEventListener('keyup', (e) => {
    if (e.target.tagName === 'INPUT') return;

    if (e.key === 'ArrowUp' || e.key === 'w' || e.key === 'W') {
      keyAccel = 0;
      if (sliderAccel) { sliderAccel.value = 0; setText('val-accel-slider', '0%'); }
      sendCommand('control', { accelerator: 0 });
    } else if (e.key === 'ArrowDown' || e.key === 's' || e.key === 'S' || e.key === ' ' || e.code === 'Space') {
      keyBrake = 0;
      if (sliderBrake) { sliderBrake.value = 0; setText('val-brake-slider', '0%'); }
      sendCommand('control', { brake: 0 });
    }
  });

  // Start connection
  connectWebSocket();
});
