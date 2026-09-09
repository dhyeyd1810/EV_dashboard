"""
chassis_ecu.py - Chassis, TPMS & ADAS Sensor ECU Simulation
Monitors individual tire pressures & temperatures (TPMS),
Wheel speeds, ABS & Electronic Stability Control (ESC) intervention,
and Forward/Blind-spot ADAS Proximity Radar.
Publishes CAN Frame 0x210.
"""

import math
import random
from core.vehicle_state import VehicleState
from bus.can_bus import global_can_bus

class ChassisAndAdasECU:
    def __init__(self):
        # Fault injection flags
        self.fault_tire_leak_fl = False
        self.fault_radar_sensor_blind = False

        # Internal target radar simulation
        self.sim_obstacle_dist = 65.0
        self.sim_blindspot_l = False
        self.sim_blindspot_r = False

    def update(self, state: VehicleState, dt: float):
        """Update Chassis & ADAS Subsystems"""
        # 1. TPMS Pressure & Temperature Simulation
        # Pressure increases slightly as tires warm up from driving
        speed_factor = (state.speed_kmh / 120.0) * 1.5
        state.tire_fl_temp_c = round(30.0 + speed_factor * 8.0, 1)
        state.tire_fr_temp_c = round(30.0 + speed_factor * 8.0, 1)
        state.tire_rl_temp_c = round(29.5 + speed_factor * 7.5, 1)
        state.tire_rr_temp_c = round(29.5 + speed_factor * 7.5, 1)

        if self.fault_tire_leak_fl:
            state.tire_fl_psi = max(12.0, state.tire_fl_psi - (2.5 * dt)) # Rapid deflation
        else:
            state.tire_fl_psi = round(35.0 + (speed_factor * 0.8), 1)

        state.tire_fr_psi = round(35.0 + (speed_factor * 0.8), 1)
        state.tire_rl_psi = round(34.8 + (speed_factor * 0.8), 1)
        state.tire_rr_psi = round(34.9 + (speed_factor * 0.8), 1)

        # 2. ADAS Proximity Radar Simulation
        if self.fault_radar_sensor_blind:
            state.radar_target_detected = False
            state.radar_front_distance_m = 999.0
        else:
            # Simulate approaching leading vehicles on the road
            if state.speed_kmh > 10.0:
                self.sim_obstacle_dist -= (state.speed_kmh * 0.05 * dt)
                if self.sim_obstacle_dist < 8.0:
                    self.sim_obstacle_dist = 95.0 # Reset to next car ahead
            else:
                self.sim_obstacle_dist = 35.0

            state.radar_front_distance_m = round(self.sim_obstacle_dist, 1)
            state.radar_target_detected = self.sim_obstacle_dist < 80.0

        # Blind spot detection triggers periodically based on speed
        if state.speed_kmh > 30.0:
            cycle = math.sin(state.odometer_km * 3.0)
            state.blind_spot_left_alert = cycle > 0.85
            state.blind_spot_right_alert = cycle < -0.85
        else:
            state.blind_spot_left_alert = False
            state.blind_spot_right_alert = False

        # Lane departure warning if steering angle high at speed
        state.lane_departure_alert = state.speed_kmh > 50.0 and abs(state.steering_angle_deg) > 22.0

        # ABS / Traction Control Intervention
        state.abs_active = state.brake_pedal_pct > 80.0 and state.speed_kmh > 15.0
        state.traction_control_active = state.accelerator_pedal_pct > 85.0 and state.speed_kmh < 40.0

        # 3. Publish CAN Frame 0x210
        global_can_bus.publish(
            msg_id=0x210,
            signal_values={
                "tire_fl_psi": round(state.tire_fl_psi, 1),
                "tire_fr_psi": round(state.tire_fr_psi, 1),
                "tire_rl_psi": round(state.tire_rl_psi, 1),
                "tire_rr_psi": round(state.tire_rr_psi, 1),
                "tire_fl_temp": state.tire_fl_temp_c,
                "tire_fr_temp": state.tire_fr_temp_c,
                "tire_rl_temp": state.tire_rl_temp_c,
                "tire_rr_temp": state.tire_rr_temp_c,
                "radar_front_dist_m": state.radar_front_distance_m,
                "radar_blindspot_l": state.blind_spot_left_alert,
                "radar_blindspot_r": state.blind_spot_right_alert,
                "lane_departure_warning": state.lane_departure_alert,
                "abs_active": state.abs_active,
                "traction_control_active": state.traction_control_active
            },
            sender_name="CHASSIS_ECU"
        )
