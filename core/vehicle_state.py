"""
vehicle_state.py - Unified Vehicle Telemetry & State Model
Represents the complete dynamic physical and electronic state of the PHEV.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any
from enum import IntEnum

class PowertrainMode(IntEnum):
    PURE_EV = 0          # Electric motor only (battery traction)
    SERIES_HYBRID = 1    # ICE runs generator to charge battery; motor drives wheels
    PARALLEL_HYBRID = 2  # Both ICE & Electric Motor drive wheels simultaneously
    ENGINE_DIRECT = 3    # ICE directly drives wheels (high-speed cruising)
    REGEN_BRAKING = 4    # Motor recovers kinetic energy to battery

class DriveMode(IntEnum):
    ECO = 0
    COMFORT = 1
    SPORT = 2
    EV_HOLD = 3
    TRACK = 4
    LIMP_HOME = 5

class Gear(IntEnum):
    PARK = 0
    REVERSE = 1
    NEUTRAL = 2
    DRIVE = 3
    BRAKE_REGEN = 4

@dataclass
class VehicleState:
    # 1. Driver Controls / Intended Inputs
    accelerator_pedal_pct: float = 0.0     # 0 to 100%
    brake_pedal_pct: float = 0.0           # 0 to 100%
    steering_angle_deg: float = 0.0        # -45 to +45 deg
    drive_mode: DriveMode = DriveMode.COMFORT
    gear: Gear = Gear.PARK
    regen_setting: int = 2                 # 0=Off, 1=Low, 2=Medium, 3=One-Pedal
    ignition_on: bool = True

    # 2. Longitudinal Vehicle Dynamics
    speed_kmh: float = 0.0
    speed_mps: float = 0.0
    acceleration_mps2: float = 0.0
    odometer_km: float = 12450.0
    trip_distance_km: float = 18.4
    road_grade_pct: float = 0.0            # Slope % (e.g. uphill/downhill)

    # 3. Hybrid Powertrain Supervisory State
    powertrain_mode: PowertrainMode = PowertrainMode.PURE_EV
    target_torque_nm: float = 0.0
    actual_wheel_torque_nm: float = 0.0
    power_split_ratio_pct: float = 100.0   # 100% = Pure EV, 0% = Pure ICE

    # 4. Electric Traction Motor & Inverter
    motor_rpm: float = 0.0
    motor_torque_nm: float = 0.0
    motor_power_kw: float = 0.0           # Positive = Motoring, Negative = Regen
    motor_temp_c: float = 38.0
    inverter_temp_c: float = 42.0
    inverter_efficiency_pct: float = 94.5

    # 5. Internal Combustion Engine (ICE) & Fuel System
    engine_state: int = 0                  # 0=Off, 1=Cranking, 2=Running, 3=Idle
    engine_rpm: float = 0.0
    engine_torque_nm: float = 0.0
    engine_power_kw: float = 0.0
    engine_coolant_temp_c: float = 88.0
    engine_oil_temp_c: float = 92.0
    fuel_tank_capacity_l: float = 45.0
    fuel_level_l: float = 34.2
    fuel_level_pct: float = 76.0
    instant_fuel_flow_lph: float = 0.0
    avg_fuel_consumption_l_100km: float = 3.8

    # 6. High-Voltage Battery Management System (BMS)
    battery_capacity_kwh: float = 18.0     # 18 kWh PHEV Battery
    battery_soc_pct: float = 82.5          # State of Charge %
    battery_soh_pct: float = 98.2          # State of Health %
    battery_voltage_v: float = 388.0       # Nominal ~350-420V
    battery_current_a: float = 0.0         # Positive = Discharge, Negative = Charge
    battery_temp_max_c: float = 29.5
    battery_temp_min_c: float = 27.8
    battery_temp_avg_c: float = 28.6
    cell_voltages: List[float] = field(default_factory=lambda: [3.92] * 96) # 96S Li-ion pack
    hv_contactors_closed: bool = True
    isolation_resistance_kohm: float = 3200.0

    # 7. Range & Energy Calculations
    est_ev_range_km: float = 68.0
    est_fuel_range_km: float = 620.0
    est_total_range_km: float = 688.0
    avg_electric_consumption_wh_km: float = 145.0

    # 8. Thermal & Climate Control
    cabin_temp_c: float = 22.5
    cabin_target_temp_c: float = 21.0
    ambient_temp_c: float = 24.0
    hvac_power_kw: float = 1.2
    hvac_fan_speed: int = 3
    ac_compressor_active: bool = True
    battery_coolant_temp_c: float = 25.0
    battery_coolant_flow_lpm: float = 12.0
    radiator_fan_pct: float = 25.0

    # 9. Chassis, Tires & ADAS
    tire_fl_psi: float = 35.2
    tire_fr_psi: float = 35.1
    tire_rl_psi: float = 34.9
    tire_rr_psi: float = 35.0
    tire_fl_temp_c: float = 32.0
    tire_fr_temp_c: float = 32.5
    tire_rl_temp_c: float = 31.8
    tire_rr_temp_c: float = 31.9

    radar_front_distance_m: float = 45.0
    radar_target_detected: bool = True
    radar_target_rel_speed_kmh: float = -2.0
    blind_spot_left_alert: bool = False
    blind_spot_right_alert: bool = False
    lane_departure_alert: bool = False
    abs_active: bool = False
    traction_control_active: bool = False

    # 10. Active Diagnostic Trouble Codes (DTCs) & Faults
    active_dtcs: List[Dict[str, Any]] = field(default_factory=list)
    master_warning_active: bool = False
    check_engine_mil: bool = False
    limp_home_active: bool = False
