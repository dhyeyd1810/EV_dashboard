"""
bms_ecu.py - Battery Management System (BMS) ECU Simulation
Monitors high-voltage battery pack (18 kWh Lithium-Ion, 96S configuration),
calculates State of Charge (SoC), State of Health (SoH), individual cell voltages,
cell temperature distribution, internal resistance heat dissipation, and publishes CAN frames (0x100).
"""

import math
import random
from typing import Dict, Any, List
from core.vehicle_state import VehicleState
from bus.can_bus import global_can_bus

class BatteryManagementECU:
    def __init__(self):
        self.nominal_capacity_ah = 48.0      # 48 Ah @ ~375V = 18.0 kWh
        self.cell_count = 96                 # 96 cells in series
        self.internal_resistance_pack = 0.08 # Ohms
        self.thermal_mass_j_per_c = 45000.0  # Heat capacity of pack
        self.cycle_time_ms = 50              # Transmit at 20Hz

        # Individual cell voltages simulation
        self.cell_voltages: List[float] = [3.92] * 96

        # Fault override flags
        self.fault_overheat = False
        self.fault_cell_imbalance = False
        self.fault_isolation_loss = False

    def update(self, state: VehicleState, dt: float):
        """Execute BMS algorithm step"""
        # 1. Calculate pack power and current
        # Total power demand = Motor Power (kW) + HVAC Power (kW) + 12V DC/DC Aux (0.4 kW)
        total_hv_power_kw = state.motor_power_kw + state.hvac_power_kw + 0.4

        # Pack voltage based on open-circuit voltage (OCV) and SoC curve
        # Typical Li-ion OCV per cell ranges from 3.2V (0% SoC) to 4.2V (100% SoC)
        soc_norm = state.battery_soc_pct / 100.0
        ocv_cell = 3.20 + (0.90 * soc_norm) + (0.10 * (soc_norm ** 3))
        pack_ocv = ocv_cell * self.cell_count

        # I = P / V (considering I*R drop)
        # Power in Watts: P = V_term * I = (OCV - I*R) * I -> I^2*R - OCV*I + P = 0
        p_watts = total_hv_power_kw * 1000.0

        discriminant = (pack_ocv ** 2) - (4 * self.internal_resistance_pack * p_watts)
        if discriminant >= 0:
            current = (pack_ocv - math.sqrt(discriminant)) / (2 * self.internal_resistance_pack)
        else:
            current = p_watts / pack_ocv

        # Clamp max discharge/charge current
        current = max(-150.0, min(350.0, current))
        terminal_voltage = max(280.0, min(425.0, pack_ocv - (current * self.internal_resistance_pack)))

        state.battery_current_a = round(current, 1)
        state.battery_voltage_v = round(terminal_voltage, 1)

        # 2. Coulomb Counting for State of Charge (SoC)
        # Ampere-hours consumed in dt seconds
        ah_delta = (current * (dt / 3600.0))
        soc_delta_pct = (ah_delta / self.nominal_capacity_ah) * 100.0
        state.battery_soc_pct = max(0.0, min(100.0, state.battery_soc_pct - soc_delta_pct))

        # 3. Simulate 96 individual series cell voltages
        base_cell_v = terminal_voltage / self.cell_count
        for i in range(self.cell_count):
            # Normal slight variance (+/- 0.008V)
            variance = math.sin((i * 0.4) + (state.odometer_km * 0.1)) * 0.006
            if self.fault_cell_imbalance and i == 42:
                # Injected weak/degraded cell
                self.cell_voltages[i] = max(2.5, base_cell_v - 0.45)
            else:
                self.cell_voltages[i] = round(base_cell_v + variance, 3)

        state.cell_voltages = self.cell_voltages

        # 4. Thermal Dynamics of Battery Pack
        # Joule heating: Q_gen = I^2 * R * dt
        joules_gen = (current ** 2) * self.internal_resistance_pack * dt
        delta_t_heat = joules_gen / self.thermal_mass_j_per_c

        # Liquid cooling effect
        coolant_cooling_rate = (state.battery_coolant_flow_lpm / 25.0) * max(0.0, (state.battery_temp_avg_c - state.battery_coolant_temp_c)) * (0.08 * dt)
        ambient_heat_transfer = (state.ambient_temp_c - state.battery_temp_avg_c) * (0.005 * dt)

        if self.fault_overheat:
            delta_t_heat += 0.8 * dt  # Rapid thermal runaway simulation

        new_avg_temp = state.battery_temp_avg_c + delta_t_heat - coolant_cooling_rate + ambient_heat_transfer
        state.battery_temp_avg_c = round(new_avg_temp, 1)
        state.battery_temp_max_c = round(new_avg_temp + 1.8, 1)
        state.battery_temp_min_c = round(new_avg_temp - 1.2, 1)

        # 5. Safety / Isolation Resistance
        if self.fault_isolation_loss:
            state.isolation_resistance_kohm = 85.0 # Degraded below 100kOhm safety threshold
        else:
            state.isolation_resistance_kohm = 3200.0

        # 6. Publish CAN Frame 0x100
        global_can_bus.publish(
            msg_id=0x100,
            signal_values={
                "soc": round(state.battery_soc_pct, 1),
                "soh": round(state.battery_soh_pct, 1),
                "pack_voltage": round(state.battery_voltage_v, 1),
                "pack_current": round(state.battery_current_a, 1),
                "pack_temp_max": round(state.battery_temp_max_c, 1),
                "pack_temp_avg": round(state.battery_temp_avg_c, 1),
                "isolation_resistance": round(state.isolation_resistance_kohm, 0),
                "contactors_closed": state.hv_contactors_closed
            },
            sender_name="BMS_ECU"
        )
