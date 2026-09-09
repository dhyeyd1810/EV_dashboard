"""
diag_ecu.py - Diagnostic Trouble Code (DTC) & Safety Monitor ECU
Implements OBD-II / UDS (ISO 14229) diagnostic monitors, ASIL safety limits,
watchdog timers, master warning illumination (MIL), and fault injection handling.
Publishes CAN Frame 0x7E0.
"""

from typing import List, Dict, Any, Optional
from core.vehicle_state import VehicleState, DriveMode
from bus.can_bus import global_can_bus

# Standard Automotive Diagnostic Trouble Codes
DTC_CATALOG = {
    "P0A80": {"code": "P0A80", "system": "BMS", "desc": "Replace Hybrid Battery Pack - Cell Degradation", "severity": 3, "fail_safe": "LIMP_MODE"},
    "P0A78": {"code": "P0A78", "system": "INVERTER", "desc": "Drive Motor 'A' Inverter Performance / Overheat", "severity": 2, "fail_safe": "DERATE"},
    "P0A0F": {"code": "P0A0F", "system": "ICE", "desc": "Engine Failed to Start / Fuel Starvation", "severity": 2, "fail_safe": "EV_ONLY"},
    "P0300": {"code": "P0300", "system": "ICE", "desc": "Random/Multiple Cylinder Misfire Detected", "severity": 2, "fail_safe": "DERATE"},
    "P0117": {"code": "P0117", "system": "THERMAL", "desc": "Engine Coolant Temperature Circuit Low / Overheat", "severity": 3, "fail_safe": "FAN_MAX"},
    "C0035": {"code": "C0035", "system": "CHASSIS", "desc": "Left Front Wheel Speed / Low Tire Pressure Critical", "severity": 2, "fail_safe": "WARN"},
    "U0100": {"code": "U0100", "system": "BUS", "desc": "Lost Communication With ECM / Engine Control Module", "severity": 3, "fail_safe": "LIMP_MODE"},
    "B1049": {"code": "B1049", "system": "ADAS", "desc": "Forward Proximity Radar Sensor Obstructed", "severity": 1, "fail_safe": "INFO"}
}

class DiagnosticECU:
    def __init__(self):
        self.active_dtcs: Dict[str, Dict[str, Any]] = {}
        self.cycle_time_ms = 100

    def trigger_fault(self, fault_code: str):
        """Inject or activate a diagnostic fault"""
        if fault_code in DTC_CATALOG:
            self.active_dtcs[fault_code] = DTC_CATALOG[fault_code]

    def clear_fault(self, fault_code: str):
        """Clear a specific fault code"""
        if fault_code in self.active_dtcs:
            del self.active_dtcs[fault_code]

    def clear_all_faults(self):
        """Clear all active diagnostic trouble codes"""
        self.active_dtcs.clear()

    def update(self, state: VehicleState, dt: float):
        """Monitor thresholds and enforce safety mitigations"""
        # Autonomous safety monitor rules (ASIL compliance)
        # 1. Battery Overheat Check
        if state.battery_temp_max_c > 52.0:
            self.trigger_fault("P0A80")
        elif "P0A80" in self.active_dtcs and state.battery_temp_max_c < 45.0:
            pass # Keep latched until explicitly cleared

        # 2. Inverter Overheat Check
        if state.inverter_temp_c > 95.0:
            self.trigger_fault("P0A78")

        # 3. Engine Overheat Check
        if state.engine_coolant_temp_c > 115.0:
            self.trigger_fault("P0117")

        # 4. Critical Low Tire Pressure
        if state.tire_fl_psi < 22.0 or state.tire_fr_psi < 22.0:
            self.trigger_fault("C0035")

        # Compile list of active DTCs
        state.active_dtcs = list(self.active_dtcs.values())

        # Determine highest severity
        severities = [d["severity"] for d in state.active_dtcs] if state.active_dtcs else [0]
        max_sev = max(severities)

        state.master_warning_active = max_sev >= 2
        state.check_engine_mil = any(d["system"] == "ICE" or d["severity"] >= 3 for d in state.active_dtcs)

        # Enforce Limp-Home mode if critical failure
        if max_sev >= 3:
            state.limp_home_active = True
            state.drive_mode = DriveMode.LIMP_HOME
        else:
            state.limp_home_active = False

        # Broadcast CAN Frame 0x7E0
        global_can_bus.publish(
            msg_id=0x7E0,
            signal_values={
                "active_fault_count": len(state.active_dtcs),
                "highest_severity": max_sev,
                "limp_home_mode": state.limp_home_active,
                "mil_indicator": state.check_engine_mil
            },
            sender_name="DIAG_ECU"
        )
