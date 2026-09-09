"""
hybrid_controller.py - Hybrid Supervisory Control Unit (HCU)
The master powertrain controller. Arbitrates torque requests, executes
energy management strategies (Pure EV vs. Series vs. Parallel vs. Engine-Direct),
manages regenerative braking, and computes dynamic EV & Fuel range.
Publishes CAN frame 0x200.
"""

import math
from core.vehicle_state import VehicleState, PowertrainMode, DriveMode, Gear
from bus.can_bus import global_can_bus

class HybridControlUnitECU:
    def __init__(self):
        self.max_total_torque_nm = 500.0  # Combined powertrain output
        self.ev_speed_threshold_kmh = 110.0 # Above 110 km/h, ICE assists for aerodynamic cruising

    def arbitrate(self, state: VehicleState, dt: float) -> tuple[float, float]:
        """
        Main HCU Energy Management Strategy (EMS).
        Returns: (motor_target_torque_nm, engine_target_power_kw)
        """
        accel = state.accelerator_pedal_pct / 100.0
        brake = state.brake_pedal_pct / 100.0

        # 1. Drive Mode Torque Shaping
        mode_gain = 1.0
        if state.drive_mode == DriveMode.ECO:
            mode_gain = 0.75
        elif state.drive_mode == DriveMode.SPORT:
            mode_gain = 1.25
        elif state.drive_mode == DriveMode.TRACK:
            mode_gain = 1.40
        elif state.drive_mode == DriveMode.LIMP_HOME:
            mode_gain = 0.30

        # Total driver requested torque
        requested_torque = (accel ** 1.3) * self.max_total_torque_nm * mode_gain
        state.target_torque_nm = round(requested_torque, 1)

        motor_torque = 0.0
        engine_power_kw = 0.0

        # 2. Braking & Regenerative Deceleration
        if brake > 0.01:
            # Brake pedal pressed: Blended braking (Regen + Friction)
            regen_demand = min(1.0, brake * 1.5)
            regen_torque = -180.0 * regen_demand
            motor_torque = regen_torque
            state.powertrain_mode = PowertrainMode.REGEN_BRAKING
            state.actual_wheel_torque_nm = motor_torque
            state.power_split_ratio_pct = 100.0

        elif accel <= 0.01 and state.speed_kmh > 1.0:
            # One-pedal / Lift-off Regenerative braking based on regen setting
            regen_map = {0: 0.0, 1: -40.0, 2: -90.0, 3: -160.0}
            motor_torque = regen_map.get(state.regen_setting, -80.0)
            state.powertrain_mode = PowertrainMode.REGEN_BRAKING
            state.actual_wheel_torque_nm = motor_torque
            state.power_split_ratio_pct = 100.0

        elif requested_torque > 0.0:
            # 3. Acceleration / Cruising Power Split Strategy
            soc = state.battery_soc_pct
            speed = state.speed_kmh
            fuel_ok = state.fuel_level_l > 0.5

            # Strategy Selection
            if state.drive_mode == DriveMode.EV_HOLD and fuel_ok:
                # Driver explicitly requested to preserve EV battery for later
                state.powertrain_mode = PowertrainMode.SERIES_HYBRID
                motor_torque = requested_torque * 0.8
                engine_power_kw = min(80.0, requested_torque * 0.25 + 15.0) # Engine charges battery while driving
                state.power_split_ratio_pct = 40.0

            elif soc > 18.0 and (speed < self.ev_speed_threshold_kmh or not fuel_ok) and requested_torque < 280.0:
                # PURE EV MODE: Sufficient battery, low to moderate torque demand
                state.powertrain_mode = PowertrainMode.PURE_EV
                motor_torque = requested_torque
                engine_power_kw = 0.0
                state.power_split_ratio_pct = 100.0

            elif soc <= 18.0 and fuel_ok:
                # LOW BATTERY: SERIES HYBRID / SUSTAINING MODE
                state.powertrain_mode = PowertrainMode.SERIES_HYBRID
                motor_torque = requested_torque * 0.7
                # Engine generates electricity to sustain battery & assist propulsion
                engine_power_kw = max(12.0, min(90.0, (requested_torque * 0.2) + (20.0 - soc) * 2.5))
                state.power_split_ratio_pct = 30.0

            elif requested_torque >= 280.0 and fuel_ok:
                # HIGH ACCELERATION / BOOST: PARALLEL HYBRID (Engine + Motor Combined)
                state.powertrain_mode = PowertrainMode.PARALLEL_HYBRID
                motor_torque = min(280.0, requested_torque * 0.65)
                engine_power_kw = min(110.0, requested_torque * 0.22)
                state.power_split_ratio_pct = 60.0

            elif speed >= self.ev_speed_threshold_kmh and fuel_ok:
                # HIGHWAY CRUISE: ENGINE DIRECT
                state.powertrain_mode = PowertrainMode.ENGINE_DIRECT
                motor_torque = requested_torque * 0.2
                engine_power_kw = min(75.0, (requested_torque * 0.25) + 10.0)
                state.power_split_ratio_pct = 20.0

            else:
                # Fallback to Motor
                state.powertrain_mode = PowertrainMode.PURE_EV
                motor_torque = requested_torque
                engine_power_kw = 0.0
                state.power_split_ratio_pct = 100.0

            state.actual_wheel_torque_nm = motor_torque + (engine_power_kw * 1.5 if state.powertrain_mode == PowertrainMode.PARALLEL_HYBRID else 0.0)

        else:
            state.actual_wheel_torque_nm = 0.0

        # 4. Range Estimation Algorithms
        self._calculate_range_estimates(state)

        # 5. Broadcast CAN Frame 0x200
        global_can_bus.publish(
            msg_id=0x200,
            signal_values={
                "powertrain_mode": int(state.powertrain_mode),
                "drive_mode": int(state.drive_mode),
                "vehicle_speed": state.speed_kmh,
                "gear_selection": int(state.gear),
                "accelerator_pedal": round(state.accelerator_pedal_pct, 1),
                "brake_pedal": round(state.brake_pedal_pct, 1),
                "power_split_ratio": round(state.power_split_ratio_pct, 0),
                "est_ev_range_km": state.est_ev_range_km,
                "est_fuel_range_km": state.est_fuel_range_km,
                "fuel_level_litres": round(state.fuel_level_l, 1),
                "fuel_level_pct": round(state.fuel_level_pct, 1)
            },
            sender_name="HCU_ECU"
        )

        return motor_torque, engine_power_kw

    def _calculate_range_estimates(self, state: VehicleState):
        """Dynamic estimation factoring HVAC, battery SoC, and fuel level"""
        # EV Range: usable kWh / (Wh/km / 1000)
        usable_kwh = (state.battery_capacity_kwh * (state.battery_soc_pct / 100.0)) * 0.95
        # HVAC & ambient temp penalty
        temp_penalty = 1.0 + (abs(state.ambient_temp_c - 21.0) * 0.012)
        effective_wh_km = state.avg_electric_consumption_wh_km * temp_penalty
        ev_range = (usable_kwh * 1000.0) / max(80.0, effective_wh_km)
        state.est_ev_range_km = round(max(0.0, ev_range), 1)

        # Fuel Range: Litres / (L/100km / 100)
        fuel_range = (state.fuel_level_l / max(2.5, state.avg_fuel_consumption_l_100km)) * 100.0
        state.est_fuel_range_km = round(max(0.0, fuel_range), 1)

        state.est_total_range_km = round(state.est_ev_range_km + state.est_fuel_range_km, 1)
