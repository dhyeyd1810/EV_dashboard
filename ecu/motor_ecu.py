"""
motor_ecu.py - Electric Traction Motor & Inverter ECU Simulation
Simulates Permanent Magnet Synchronous Motor (PMSM) and 3-Phase IGBT Inverter.
Handles field-oriented torque delivery, regenerative deceleration braking,
inverter efficiency losses, stator winding temperatures, and CAN frame 0x120.
"""

import math
from core.vehicle_state import VehicleState, DriveMode, Gear
from bus.can_bus import global_can_bus

class TractionMotorECU:
    def __init__(self):
        self.max_motor_torque_nm = 330.0    # 330 Nm instant torque
        self.max_motor_power_kw = 135.0     # 135 kW (~184 HP) electric motor
        self.max_regen_power_kw = 65.0      # Max regenerative braking capture
        self.base_efficiency = 95.0

        # Fault flags
        self.fault_inverter_overheat = False
        self.fault_resolver_signal_loss = False
        self.fault_derating = False

    def update(self, state: VehicleState, dt: float, motor_target_torque_nm: float):
        """Update Motor/Inverter ECU"""
        if not state.ignition_on or state.gear in [Gear.PARK, Gear.NEUTRAL]:
            state.motor_torque_nm = 0.0
            state.motor_power_kw = 0.0
            self._update_temperatures(state, dt)
            self._publish_can(state)
            return

        # Torque derating under fault or low SoC
        max_available_torque = self.max_motor_torque_nm
        if state.battery_soc_pct < 10.0:
            max_available_torque *= (state.battery_soc_pct / 10.0) # Derate as battery empties

        if self.fault_derating or state.drive_mode == DriveMode.LIMP_HOME:
            max_available_torque *= 0.35 # Safe limp torque

        if self.fault_resolver_signal_loss:
            max_available_torque = 0.0 # Safety shutoff

        # Clamp requested torque
        applied_torque = max(-self.max_motor_torque_nm, min(max_available_torque, motor_target_torque_nm))
        state.motor_torque_nm = round(applied_torque, 1)

        # Electrical power calculation: P = (Torque * RPM) / 9549
        rad_per_sec = (state.motor_rpm * 2 * math.pi) / 60.0
        mech_power_kw = (applied_torque * rad_per_sec) / 1000.0

        # Inverter & Motor Efficiency Model (90% to 96.5% depending on operating point)
        torque_ratio = abs(applied_torque) / self.max_motor_torque_nm
        efficiency = self.base_efficiency - (3.5 * ((1.0 - torque_ratio) ** 2))
        state.inverter_efficiency_pct = round(max(85.0, min(97.0, efficiency)), 1)

        if applied_torque >= 0:
            # Motoring mode (drawing power from battery)
            elec_power_kw = mech_power_kw / (efficiency / 100.0)
        else:
            # Regenerative braking mode (pushing power back to battery)
            # Cannot regen if battery is 100% full
            if state.battery_soc_pct >= 99.0:
                elec_power_kw = 0.0
            else:
                elec_power_kw = mech_power_kw * (efficiency / 100.0)
                elec_power_kw = max(-self.max_regen_power_kw, elec_power_kw)

        state.motor_power_kw = round(elec_power_kw, 1)

        self._update_temperatures(state, dt)
        self._publish_can(state)

    def _update_temperatures(self, state: VehicleState, dt: float):
        # Heat generation in stator & IGBTs
        current_factor = (abs(state.motor_power_kw) / self.max_motor_power_kw) ** 1.8
        motor_heat_gen = current_factor * 1.5 * dt
        inv_heat_gen = current_factor * 1.8 * dt

        if self.fault_inverter_overheat:
            inv_heat_gen += 2.5 * dt

        # Cooling from coolant loop
        coolant_factor = (state.battery_coolant_flow_lpm / 25.0) * (0.04 * dt)

        state.motor_temp_c = max(state.ambient_temp_c, min(160.0, state.motor_temp_c + motor_heat_gen - ((state.motor_temp_c - 30.0) * coolant_factor)))
        state.inverter_temp_c = max(state.ambient_temp_c, min(140.0, state.inverter_temp_c + inv_heat_gen - ((state.inverter_temp_c - 30.0) * coolant_factor)))

        state.motor_temp_c = round(state.motor_temp_c, 1)
        state.inverter_temp_c = round(state.inverter_temp_c, 1)

    def _publish_can(self, state: VehicleState):
        global_can_bus.publish(
            msg_id=0x120,
            signal_values={
                "motor_rpm": round(state.motor_rpm, 0),
                "motor_torque": state.motor_torque_nm,
                "motor_power_kw": state.motor_power_kw,
                "inverter_temp": state.inverter_temp_c,
                "motor_temp": state.motor_temp_c,
                "regen_level": state.regen_setting,
                "inverter_efficiency": state.inverter_efficiency_pct
            },
            sender_name="MOTOR_ECU"
        )
