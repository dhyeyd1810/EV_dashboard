"""
ice_ecu.py - Internal Combustion Engine (ICE) ECU Simulation
Simulates a 1.5L Turbocharged 4-cylinder engine in a PHEV setup.
Models throttle response, RPM inertia, Brake Specific Fuel Consumption (BSFC),
fuel flow rate, oil pressure, coolant temperature rise, and CAN frame 0x110.
"""

import math
from core.vehicle_state import VehicleState, PowertrainMode
from bus.can_bus import global_can_bus

class InternalCombustionEngineECU:
    def __init__(self):
        self.idle_rpm = 850.0
        self.max_rpm = 6500.0
        self.max_torque_nm = 240.0         # Engine peak torque @ 2000-4500 RPM
        self.max_power_kw = 115.0          # ~156 HP
        self.fuel_energy_density_kwh_per_l = 8.9 # Gasoline energy density

        # Fault flags
        self.fault_misfire = False
        self.fault_coolant_overheat = False
        self.fault_low_oil_pressure = False

    def update(self, state: VehicleState, dt: float, engine_target_power_kw: float):
        """Update Engine ECU state"""
        # Engine is active if HCU requests power or if battery is low and needs charging
        wants_engine_on = engine_target_power_kw > 1.0 or state.powertrain_mode in [
            PowertrainMode.SERIES_HYBRID,
            PowertrainMode.PARALLEL_HYBRID,
            PowertrainMode.ENGINE_DIRECT
        ]

        if not state.ignition_on or state.fuel_level_l <= 0.05:
            wants_engine_on = False

        # State transition: 0=Off, 1=Cranking, 2=Running, 3=Idle
        if not wants_engine_on:
            state.engine_state = 0
            state.engine_rpm = max(0.0, state.engine_rpm - (3000.0 * dt))
            state.engine_torque_nm = 0.0
            state.engine_power_kw = 0.0
            state.instant_fuel_flow_lph = 0.0
        else:
            if state.engine_rpm < self.idle_rpm * 0.8:
                state.engine_state = 1 # Cranking
                state.engine_rpm = min(self.idle_rpm, state.engine_rpm + (2500.0 * dt))
            elif engine_target_power_kw < 3.0 and state.speed_kmh < 1.0:
                state.engine_state = 3 # Eco Idle
                state.engine_rpm = self.idle_rpm + (math.sin(state.odometer_km * 50) * 20.0)
            else:
                state.engine_state = 2 # Running / Under Load

                # Determine target RPM based on power demand (BSFC sweet spot curve for Hybrid)
                # In Series/Parallel hybrid, engine operates around 1800-4200 RPM for maximum thermal efficiency
                power_ratio = min(1.0, max(0.0, engine_target_power_kw / self.max_power_kw))
                target_rpm = self.idle_rpm + (power_ratio ** 0.65) * (self.max_rpm - self.idle_rpm)

                # Smooth RPM ramp (engine inertia)
                rpm_delta = target_rpm - state.engine_rpm
                state.engine_rpm += rpm_delta * min(1.0, 8.0 * dt)

                # Compute torque and power
                rpm_norm = min(1.0, state.engine_rpm / self.max_rpm)
                torque_curve_factor = math.sin(rpm_norm * math.pi) ** 0.4
                torque = min(self.max_torque_nm, (engine_target_power_kw * 9549.0) / max(500.0, state.engine_rpm))
                torque *= torque_curve_factor

                if self.fault_misfire:
                    torque *= 0.65 # 35% power loss from cylinder misfire

                state.engine_torque_nm = round(torque, 1)
                actual_kw = (state.engine_torque_nm * state.engine_rpm) / 9549.0
                state.engine_power_kw = round(actual_kw, 1)

                # 3. Fuel Consumption Model (BSFC ~ 220-300 g/kWh)
                # BSFC g/kWh -> Litres/hr: (Power_kW * BSFC) / (Gasoline_Density_740g_L)
                bsfc_g_kwh = 230.0 + (50.0 * (1.0 - torque_curve_factor))
                fuel_flow_g_per_sec = (state.engine_power_kw * bsfc_g_kwh) / 3600.0
                fuel_flow_lph = (fuel_flow_g_per_sec / 740.0) * 3600.0
                state.instant_fuel_flow_lph = round(fuel_flow_lph, 2)

                # Integrate fuel burn
                fuel_burned_l = (fuel_flow_lph / 3600.0) * dt
                state.fuel_level_l = max(0.0, state.fuel_level_l - fuel_burned_l)
                state.fuel_level_pct = round((state.fuel_level_l / state.fuel_tank_capacity_l) * 100.0, 1)

        # 4. Thermal Dynamics of ICE
        if state.engine_state in [2, 3]:
            # Engine warming up to 90°C
            heat_gen = (state.engine_power_kw * 0.4) * dt
            if self.fault_coolant_overheat:
                heat_gen += 1.5 * dt # Stuck thermostat
            target_coolant = 90.0 if not self.fault_coolant_overheat else 125.0
            state.engine_coolant_temp_c = min(130.0, state.engine_coolant_temp_c + (heat_gen * 0.05))
        else:
            # Engine slowly cooling toward ambient
            cool_rate = (state.engine_coolant_temp_c - state.ambient_temp_c) * (0.01 * dt)
            state.engine_coolant_temp_c = max(state.ambient_temp_c, state.engine_coolant_temp_c - cool_rate)

        state.engine_coolant_temp_c = round(state.engine_coolant_temp_c, 1)

        # Oil pressure simulation (200-550 kPa based on RPM)
        if state.engine_state in [1, 2, 3]:
            base_oil_press = 220.0 + (state.engine_rpm / self.max_rpm) * 300.0
            if self.fault_low_oil_pressure:
                base_oil_press = 65.0 # Warning threshold < 100 kPa
            oil_pressure = base_oil_press
        else:
            oil_pressure = 0.0

        # 5. Broadcast CAN Frame 0x110
        global_can_bus.publish(
            msg_id=0x110,
            signal_values={
                "engine_state": state.engine_state,
                "engine_rpm": round(state.engine_rpm, 0),
                "engine_torque": state.engine_torque_nm,
                "engine_power_kw": state.engine_power_kw,
                "coolant_temp": state.engine_coolant_temp_c,
                "oil_pressure_kpa": round(oil_pressure, 0),
                "fuel_flow_rate_lph": state.instant_fuel_flow_lph,
                "throttle_pos": round(state.accelerator_pedal_pct, 1)
            },
            sender_name="ICE_ECU"
        )
