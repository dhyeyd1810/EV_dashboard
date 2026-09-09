"""
vehicle_sim.py - Master Hybrid Vehicle Simulation Coordinator
Coordinates the real-time simulation loop, scheduling ECU ticks at realistic rates,
integrating physical equations of motion, and handling external driver/telemetry commands.
"""

import time
import asyncio
from typing import Dict, Any, Optional

from core.vehicle_state import VehicleState, DriveMode, Gear, PowertrainMode
from core.physics import VehiclePhysicsEngine
from ecu.bms_ecu import BatteryManagementECU
from ecu.ice_ecu import InternalCombustionEngineECU
from ecu.motor_ecu import TractionMotorECU
from ecu.hybrid_controller import HybridControlUnitECU
from ecu.thermal_ecu import ThermalManagementECU
from ecu.chassis_ecu import ChassisAndAdasECU
from ecu.diag_ecu import DiagnosticECU
from bus.can_bus import global_can_bus

class HybridVehicleSimulator:
    def __init__(self):
        self.state = VehicleState()
        self.physics = VehiclePhysicsEngine()

        # Instantiate all ECUs
        self.bms_ecu = BatteryManagementECU()
        self.ice_ecu = InternalCombustionEngineECU()
        self.motor_ecu = TractionMotorECU()
        self.hcu_ecu = HybridControlUnitECU()
        self.thermal_ecu = ThermalManagementECU()
        self.chassis_ecu = ChassisAndAdasECU()
        self.diag_ecu = DiagnosticECU()

        # Timing tracking
        self.last_step_time = time.time()
        self.is_running = False
        self._sim_task: Optional[asyncio.Task] = None

        # Autopilot / Automated Drive Cycle profile flag
        self.auto_drive_cycle = False
        self.auto_drive_time = 0.0

    def step(self, dt: float):
        """Execute one simulation cycle (dt in seconds)"""
        # 1. Autonomous Drive Cycle Profile (WLTP-like cycle generator if enabled)
        if self.auto_drive_cycle:
            self._execute_drive_cycle_step(dt)

        # 2. Hybrid Supervisory Control Unit arbitrates torque & power
        motor_torque_req, engine_power_req = self.hcu_ecu.arbitrate(self.state, dt)

        # 3. Traction Motor & ICE Execute power deliveries
        self.motor_ecu.update(self.state, dt, motor_torque_req)
        self.ice_ecu.update(self.state, dt, engine_power_req)

        # 4. Longitudinal Physics integrates forces into vehicle speed
        self.physics.compute_motion_step(self.state, dt)

        # 5. BMS computes battery load, cell balance, and thermal generation
        self.bms_ecu.update(self.state, dt)

        # 6. Thermal management regulates coolant loops & cabin HVAC
        self.thermal_ecu.update(self.state, dt)

        # 7. Chassis & ADAS monitors TPMS, wheel speeds, radar
        self.chassis_ecu.update(self.state, dt)

        # 8. Diagnostics monitors limits, ASIL triggers, and DTC codes
        self.diag_ecu.update(self.state, dt)

    def _execute_drive_cycle_step(self, dt: float):
        """Simulates an active dynamic drive cycle profile (urban + highway + braking)"""
        self.auto_drive_time += dt
        cycle_phase = (self.auto_drive_time % 60.0)

        self.state.gear = Gear.DRIVE
        if cycle_phase < 15.0:
            # Acceleration phase (Urban cruising)
            self.state.accelerator_pedal_pct = min(45.0, cycle_phase * 3.5)
            self.state.brake_pedal_pct = 0.0
        elif cycle_phase < 28.0:
            # Steady speed cruising
            self.state.accelerator_pedal_pct = 22.0
            self.state.brake_pedal_pct = 0.0
        elif cycle_phase < 36.0:
            # Highway power acceleration
            self.state.accelerator_pedal_pct = 65.0
            self.state.brake_pedal_pct = 0.0
        elif cycle_phase < 46.0:
            # Coasting / mild regenerative deceleration
            self.state.accelerator_pedal_pct = 0.0
            self.state.brake_pedal_pct = 10.0
        else:
            # Braking to stop
            self.state.accelerator_pedal_pct = 0.0
            self.state.brake_pedal_pct = 40.0

    def apply_driver_control(self, command: Dict[str, Any]):
        """Handle incoming driver/dashboard control actions"""
        if "accelerator" in command:
            self.state.accelerator_pedal_pct = max(0.0, min(100.0, float(command["accelerator"])))
        if "brake" in command:
            self.state.brake_pedal_pct = max(0.0, min(100.0, float(command["brake"])))
        if "gear" in command:
            gear_map = {"P": Gear.PARK, "R": Gear.REVERSE, "N": Gear.NEUTRAL, "D": Gear.DRIVE, "B": Gear.BRAKE_REGEN}
            g = command["gear"]
            if isinstance(g, str) and g in gear_map:
                self.state.gear = gear_map[g]
            elif isinstance(g, int) and 0 <= g <= 4:
                self.state.gear = Gear(g)
        if "drive_mode" in command:
            dm_map = {"ECO": DriveMode.ECO, "COMFORT": DriveMode.COMFORT, "SPORT": DriveMode.SPORT, "EV_HOLD": DriveMode.EV_HOLD, "TRACK": DriveMode.TRACK}
            dm = command["drive_mode"]
            if isinstance(dm, str) and dm in dm_map:
                self.state.drive_mode = dm_map[dm]
            elif isinstance(dm, int) and 0 <= dm <= 5:
                self.state.drive_mode = DriveMode(dm)
        if "regen_setting" in command:
            self.state.regen_setting = max(0, min(3, int(command["regen_setting"])))
        if "ignition" in command:
            self.state.ignition_on = bool(command["ignition"])
        if "cabin_target_temp" in command:
            self.state.cabin_target_temp_c = float(command["cabin_target_temp"])
        if "auto_drive" in command:
            self.auto_drive_cycle = bool(command["auto_drive"])

    def inject_fault(self, fault_type: str, enabled: bool = True):
        """Simulate embedded hardware/component fault injection"""
        if fault_type == "bms_overheat":
            self.bms_ecu.fault_overheat = enabled
        elif fault_type == "cell_imbalance":
            self.bms_ecu.fault_cell_imbalance = enabled
        elif fault_type == "isolation_loss":
            self.bms_ecu.fault_isolation_loss = enabled
        elif fault_type == "engine_misfire":
            self.ice_ecu.fault_misfire = enabled
        elif fault_type == "engine_overheat":
            self.ice_ecu.fault_coolant_overheat = enabled
        elif fault_type == "low_oil_press":
            self.ice_ecu.fault_low_oil_pressure = enabled
        elif fault_type == "inverter_overheat":
            self.motor_ecu.fault_inverter_overheat = enabled
        elif fault_type == "tire_leak":
            self.chassis_ecu.fault_tire_leak_fl = enabled
        elif fault_type == "radar_blind":
            self.chassis_ecu.fault_radar_sensor_blind = enabled

    def reset_all_faults(self):
        self.bms_ecu.fault_overheat = False
        self.bms_ecu.fault_cell_imbalance = False
        self.bms_ecu.fault_isolation_loss = False
        self.ice_ecu.fault_misfire = False
        self.ice_ecu.fault_coolant_overheat = False
        self.ice_ecu.fault_low_oil_pressure = False
        self.motor_ecu.fault_inverter_overheat = False
        self.chassis_ecu.fault_tire_leak_fl = False
        self.chassis_ecu.fault_radar_sensor_blind = False
        self.diag_ecu.clear_all_faults()

        self.state.tire_fl_psi = 35.2
        self.state.battery_temp_max_c = 29.5
        self.state.battery_temp_avg_c = 28.0
        self.state.engine_coolant_temp_c = 88.0
        self.state.inverter_temp_c = 42.0
        self.state.drive_mode = DriveMode.COMFORT
        self.state.limp_home_active = False


    def get_full_telemetry_snapshot(self) -> Dict[str, Any]:
        """Returns JSON-serializable snapshot of complete vehicle telemetry"""
        s = self.state
        return {
            "timestamp_ms": round(time.time() * 1000, 1),
            "speed_kmh": s.speed_kmh,
            "acceleration_mps2": s.acceleration_mps2,
            "odometer_km": s.odometer_km,
            "trip_distance_km": s.trip_distance_km,
            "gear": s.gear.name,
            "drive_mode": s.drive_mode.name,
            "powertrain_mode": s.powertrain_mode.name,
            "power_split_ratio": s.power_split_ratio_pct,
            "target_torque_nm": s.target_torque_nm,
            "actual_wheel_torque_nm": s.actual_wheel_torque_nm,

            # Controls
            "accelerator_pct": s.accelerator_pedal_pct,
            "brake_pct": s.brake_pedal_pct,
            "regen_setting": s.regen_setting,
            "auto_drive": self.auto_drive_cycle,

            # Battery (BMS)
            "battery": {
                "soc_pct": s.battery_soc_pct,
                "soh_pct": s.battery_soh_pct,
                "voltage_v": s.battery_voltage_v,
                "current_a": s.battery_current_a,
                "temp_max_c": s.battery_temp_max_c,
                "temp_avg_c": s.battery_temp_avg_c,
                "cell_voltages": s.cell_voltages[:16], # first 16 cells for UI summary
                "isolation_kohm": s.isolation_resistance_kohm,
                "contactors": s.hv_contactors_closed
            },

            # Motor & Inverter
            "motor": {
                "rpm": s.motor_rpm,
                "torque_nm": s.motor_torque_nm,
                "power_kw": s.motor_power_kw,
                "inverter_temp_c": s.inverter_temp_c,
                "motor_temp_c": s.motor_temp_c,
                "efficiency_pct": s.inverter_efficiency_pct
            },

            # Engine & Fuel (ICE)
            "ice": {
                "state": s.engine_state,
                "rpm": s.engine_rpm,
                "torque_nm": s.engine_torque_nm,
                "power_kw": s.engine_power_kw,
                "coolant_temp_c": s.engine_coolant_temp_c,
                "fuel_level_l": s.fuel_level_l,
                "fuel_level_pct": s.fuel_level_pct,
                "fuel_flow_lph": s.instant_fuel_flow_lph,
                "avg_consumption": s.avg_fuel_consumption_l_100km
            },

            # Range
            "range": {
                "ev_range_km": s.est_ev_range_km,
                "fuel_range_km": s.est_fuel_range_km,
                "total_range_km": s.est_total_range_km
            },

            # Thermal & Climate
            "thermal": {
                "cabin_temp_c": s.cabin_temp_c,
                "target_temp_c": s.cabin_target_temp_c,
                "ambient_temp_c": s.ambient_temp_c,
                "hvac_power_kw": s.hvac_power_kw,
                "battery_coolant_flow_lpm": s.battery_coolant_flow_lpm,
                "battery_coolant_temp_c": s.battery_coolant_temp_c,
                "radiator_fan_pct": s.radiator_fan_pct
            },

            # Chassis & ADAS
            "chassis": {
                "tires": {
                    "fl_psi": s.tire_fl_psi, "fr_psi": s.tire_fr_psi,
                    "rl_psi": s.tire_rl_psi, "rr_psi": s.tire_rr_psi,
                    "fl_temp": s.tire_fl_temp_c, "fr_temp": s.tire_fr_temp_c,
                    "rl_temp": s.tire_rl_temp_c, "rr_temp": s.tire_rr_temp_c
                },
                "radar_dist_m": s.radar_front_distance_m,
                "blindspot_l": s.blind_spot_left_alert,
                "blindspot_r": s.blind_spot_right_alert,
                "lane_warning": s.lane_departure_alert,
                "abs_active": s.abs_active,
                "traction_active": s.traction_control_active
            },

            # Diagnostics
            "diagnostics": {
                "active_dtcs": s.active_dtcs,
                "master_warning": s.master_warning_active,
                "check_engine": s.check_engine_mil,
                "limp_mode": s.limp_home_active
            }
        }

# Global Simulator Instance
global_simulator = HybridVehicleSimulator()
