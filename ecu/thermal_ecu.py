"""
thermal_ecu.py - Multi-Loop Thermal Management & Cabin HVAC ECU
Coordinates dual coolant loops:
- Loop A (Low Temp): HV Battery pack + Motor Inverter chiller loop
- Loop B (High Temp): ICE Engine radiator & thermostat loop
- Loop C (Refrigerant/Heat Pump): Cabin HVAC climate control
Publishes CAN Frame 0x300.
"""

from core.vehicle_state import VehicleState
from bus.can_bus import global_can_bus

class ThermalManagementECU:
    def __init__(self):
        self.battery_target_temp_c = 25.0 # Ideal Li-ion operating temp: 20-30°C

    def update(self, state: VehicleState, dt: float):
        """Update Thermal & HVAC Subsystems"""
        # 1. Cabin Climate Dynamics
        temp_error = state.cabin_temp_c - state.cabin_target_temp_c
        if abs(temp_error) > 0.5:
            # Compressor / Heat pump power scales with temperature difference
            target_hvac_kw = min(5.5, max(0.4, abs(temp_error) * 0.8 * (state.hvac_fan_speed / 3.0)))
            state.hvac_power_kw = round(target_hvac_kw, 1)

            # Adjust cabin temp toward target
            cooling_direction = -1.0 if temp_error > 0 else 1.0
            state.cabin_temp_c += cooling_direction * (0.05 * (state.hvac_fan_speed / 3.0) * dt)
        else:
            state.hvac_power_kw = 0.5 # Idle maintenance power

        # Ambient leakage to cabin
        leakage = (state.ambient_temp_c - state.cabin_temp_c) * (0.002 * dt)
        state.cabin_temp_c = round(state.cabin_temp_c + leakage, 1)

        # 2. Battery & Inverter Coolant Loop (Loop A)
        # Variable speed electric coolant pump (0 to 25 L/min)
        if state.battery_temp_max_c > 32.0 or state.inverter_temp_c > 50.0:
            target_flow = min(25.0, 10.0 + (state.battery_temp_max_c - 32.0) * 2.0)
        else:
            target_flow = 6.0 # Base circulation
        state.battery_coolant_flow_lpm = round(target_flow, 1)

        # Coolant chiller temperature
        state.battery_coolant_temp_c = round(max(15.0, min(35.0, state.ambient_temp_c - (state.battery_coolant_flow_lpm * 0.4))), 1)

        # 3. Engine Radiator Fan (Loop B)
        if state.engine_coolant_temp_c > 92.0:
            fan_pct = min(100.0, (state.engine_coolant_temp_c - 92.0) * 8.0)
        else:
            fan_pct = 0.0
        state.radiator_fan_pct = round(fan_pct, 0)

        # 4. Publish CAN Frame 0x300
        global_can_bus.publish(
            msg_id=0x300,
            signal_values={
                "battery_coolant_flow_lpm": state.battery_coolant_flow_lpm,
                "battery_coolant_temp": state.battery_coolant_temp_c,
                "engine_radiator_fan_pct": state.radiator_fan_pct,
                "hvac_cabin_temp": state.cabin_temp_c,
                "hvac_target_temp": state.cabin_target_temp_c,
                "hvac_power_kw": state.hvac_power_kw,
                "heat_pump_active": state.ac_compressor_active
            },
            sender_name="THERMAL_ECU"
        )
