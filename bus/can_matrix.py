"""
can_matrix.py - Simulated CAN-FD Message & Signal Matrix (DBC Specification)
Defines standard arbitration IDs, payload layouts, signal bit-lengths, scales, and offsets
for the Hybrid Electric Vehicle (PHEV) powertrain.
"""

from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class CANSignal:
    name: str
    unit: str
    min_val: float
    max_val: float
    scale: float = 1.0
    offset: float = 0.0

@dataclass
class CANMessageDef:
    msg_id: int
    name: str
    sender_ecu: str
    cycle_time_ms: int  # ECU transmission period
    signals: Dict[str, CANSignal]

# Standardized Automotive CAN Arbitration Matrix
CAN_MATRIX: Dict[int, CANMessageDef] = {
    # 0x100: Battery Management System (BMS) Status
    0x100: CANMessageDef(
        msg_id=0x100,
        name="BMS_Pack_Status",
        sender_ecu="BMS_ECU",
        cycle_time_ms=50,
        signals={
            "soc": CANSignal("State of Charge", "%", 0.0, 100.0, 0.1),
            "soh": CANSignal("State of Health", "%", 0.0, 100.0, 0.1),
            "pack_voltage": CANSignal("Pack Voltage", "V", 0.0, 500.0, 0.1),
            "pack_current": CANSignal("Pack Current", "A", -400.0, 400.0, 0.1),
            "pack_temp_max": CANSignal("Max Cell Temp", "°C", -40.0, 120.0, 0.5),
            "pack_temp_avg": CANSignal("Avg Cell Temp", "°C", -40.0, 120.0, 0.5),
            "isolation_resistance": CANSignal("Isolation Res", "kOhm", 0, 10000, 1.0),
            "contactors_closed": CANSignal("HV Contactors", "bool", 0, 1, 1.0),
        }
    ),

    # 0x110: Internal Combustion Engine (ICE) ECU
    0x110: CANMessageDef(
        msg_id=0x110,
        name="ICE_Engine_Status",
        sender_ecu="ICE_ECU",
        cycle_time_ms=20,
        signals={
            "engine_state": CANSignal("State (0=Off,1=Cranking,2=Running,3=EcoIdle)", "", 0, 3, 1.0),
            "engine_rpm": CANSignal("Engine RPM", "RPM", 0, 7500, 1.0),
            "engine_torque": CANSignal("Engine Torque", "Nm", 0, 450, 0.5),
            "engine_power_kw": CANSignal("Engine Output Power", "kW", 0, 250, 0.1),
            "coolant_temp": CANSignal("Engine Coolant Temp", "°C", -40, 150, 0.5),
            "oil_pressure_kpa": CANSignal("Oil Pressure", "kPa", 0, 700, 1.0),
            "fuel_flow_rate_lph": CANSignal("Instant Fuel Flow", "L/h", 0.0, 60.0, 0.05),
            "throttle_pos": CANSignal("Throttle Position", "%", 0.0, 100.0, 0.5),
        }
    ),

    # 0x120: Electric Traction Motor & Inverter
    0x120: CANMessageDef(
        msg_id=0x120,
        name="EMotor_Inverter_Status",
        sender_ecu="MOTOR_ECU",
        cycle_time_ms=20,
        signals={
            "motor_rpm": CANSignal("Motor RPM", "RPM", -15000, 15000, 1.0),
            "motor_torque": CANSignal("Motor Torque", "Nm", -400, 400, 0.5),
            "motor_power_kw": CANSignal("Motor Power (Pos=Draw, Neg=Regen)", "kW", -150, 200, 0.1),
            "inverter_temp": CANSignal("Inverter Temp", "°C", -40, 150, 0.5),
            "motor_temp": CANSignal("Stator Winding Temp", "°C", -40, 180, 0.5),
            "regen_level": CANSignal("Regen Braking Level (0-3)", "", 0, 3, 1.0),
            "inverter_efficiency": CANSignal("Inverter Efficiency", "%", 0.0, 100.0, 0.1),
        }
    ),

    # 0x200: Hybrid Supervisory Control Unit (HCU)
    0x200: CANMessageDef(
        msg_id=0x200,
        name="HCU_PowerSplit_Status",
        sender_ecu="HCU_ECU",
        cycle_time_ms=20,
        signals={
            "powertrain_mode": CANSignal("Mode (0=EV, 1=Series, 2=Parallel, 3=EngineDirect, 4=Regen)", "", 0, 4, 1.0),
            "drive_mode": CANSignal("Drive Mode (0=Eco, 1=Normal, 2=Sport, 3=EV_Hold, 4=Track)", "", 0, 4, 1.0),
            "vehicle_speed": CANSignal("Vehicle Speed", "km/h", 0.0, 260.0, 0.1),
            "gear_selection": CANSignal("Gear (P, R, N, D, B)", "", 0, 4, 1.0),
            "accelerator_pedal": CANSignal("Accelerator Pedal", "%", 0.0, 100.0, 0.5),
            "brake_pedal": CANSignal("Brake Pedal", "%", 0.0, 100.0, 0.5),
            "power_split_ratio": CANSignal("Electric vs Fuel Power Split", "%", 0.0, 100.0, 1.0),
            "est_ev_range_km": CANSignal("Estimated EV Range", "km", 0.0, 120.0, 0.1),
            "est_fuel_range_km": CANSignal("Estimated Fuel Range", "km", 0.0, 900.0, 0.1),
            "fuel_level_litres": CANSignal("Fuel Tank Level", "L", 0.0, 60.0, 0.1),
            "fuel_level_pct": CANSignal("Fuel Tank Level", "%", 0.0, 100.0, 0.1),
        }
    ),

    # 0x210: Chassis, TPMS & ADAS Sensor ECU
    0x210: CANMessageDef(
        msg_id=0x210,
        name="Chassis_ADAS_Status",
        sender_ecu="CHASSIS_ECU",
        cycle_time_ms=100,
        signals={
            "tire_fl_psi": CANSignal("Front Left Pressure", "psi", 0, 60, 0.1),
            "tire_fr_psi": CANSignal("Front Right Pressure", "psi", 0, 60, 0.1),
            "tire_rl_psi": CANSignal("Rear Left Pressure", "psi", 0, 60, 0.1),
            "tire_rr_psi": CANSignal("Rear Right Pressure", "psi", 0, 60, 0.1),
            "tire_fl_temp": CANSignal("Front Left Temp", "°C", -30, 100, 0.5),
            "tire_fr_temp": CANSignal("Front Right Temp", "°C", -30, 100, 0.5),
            "tire_rl_temp": CANSignal("Rear Left Temp", "°C", -30, 100, 0.5),
            "tire_rr_temp": CANSignal("Rear Right Temp", "°C", -30, 100, 0.5),
            "radar_front_dist_m": CANSignal("Forward Proximity Radar", "m", 0.0, 200.0, 0.1),
            "radar_blindspot_l": CANSignal("Left Blind Spot Target", "bool", 0, 1, 1.0),
            "radar_blindspot_r": CANSignal("Right Blind Spot Target", "bool", 0, 1, 1.0),
            "lane_departure_warning": CANSignal("Lane Departure Active", "bool", 0, 1, 1.0),
            "abs_active": CANSignal("ABS Engaged", "bool", 0, 1, 1.0),
            "traction_control_active": CANSignal("Traction Control Engaged", "bool", 0, 1, 1.0),
        }
    ),

    # 0x300: Thermal Management & Cabin HVAC ECU
    0x300: CANMessageDef(
        msg_id=0x300,
        name="Thermal_HVAC_Status",
        sender_ecu="THERMAL_ECU",
        cycle_time_ms=250,
        signals={
            "battery_coolant_flow_lpm": CANSignal("Battery Coolant Flow", "L/min", 0.0, 25.0, 0.1),
            "battery_coolant_temp": CANSignal("Battery Coolant In Temp", "°C", -20, 80, 0.5),
            "engine_radiator_fan_pct": CANSignal("Radiator Fan Speed", "%", 0, 100, 1.0),
            "hvac_cabin_temp": CANSignal("Cabin Temp", "°C", -20, 50, 0.5),
            "hvac_target_temp": CANSignal("Target Temp", "°C", 16, 30, 0.5),
            "hvac_power_kw": CANSignal("HVAC Compressor Power", "kW", 0.0, 8.0, 0.1),
            "heat_pump_active": CANSignal("Heat Pump Active", "bool", 0, 1, 1.0),
        }
    ),

    # 0x7E0: Unified Diagnostic Services (UDS) / DTC Fault Frame
    0x7E0: CANMessageDef(
        msg_id=0x7E0,
        name="UDS_Diagnostics_DTC",
        sender_ecu="DIAG_ECU",
        cycle_time_ms=100,
        signals={
            "active_fault_count": CANSignal("Active DTC Count", "count", 0, 20, 1.0),
            "highest_severity": CANSignal("Severity (0=None, 1=Info, 2=Warn, 3=Critical)", "", 0, 3, 1.0),
            "limp_home_mode": CANSignal("Limp Home Active", "bool", 0, 1, 1.0),
            "mil_indicator": CANSignal("Check Engine / Master Warning MIL", "bool", 0, 1, 1.0),
        }
    )
}

if __name__ == "__main__":
    print("=" * 80)
    print("   AURA-PHEV CAN-FD MESSAGE & SIGNAL DEFINITION MATRIX (DBC SPEC)")
    print("=" * 80)
    for msg_id, msg in CAN_MATRIX.items():
        print(f"\n[CAN ID: 0x{msg_id:03X}] {msg.name} (Sender: {msg.sender_ecu}, Rate: {msg.cycle_time_ms}ms)")
        print("-" * 80)
        for sig_key, sig in msg.signals.items():
            unit_str = f"[{sig.unit}]" if sig.unit else ""
            print(f"  - {sig_key:<26} : {sig.name} {unit_str:<8} (Range: {sig.min_val} to {sig.max_val})")
    print("\n" + "=" * 80)
    print("Total CAN Messages Defined:", len(CAN_MATRIX))
    print("To launch the live dashboard & simulation server, run: python main.py")
    print("=" * 80)


