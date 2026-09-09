"""
physics.py - Vehicle Dynamics & Kinematics Engine
Calculates aerodynamic drag, rolling resistance, inertial forces,
and wheel power requirements based on vehicle parameters.
"""

import math
from core.vehicle_state import VehicleState, Gear, DriveMode

class VehiclePhysicsEngine:
    """
    Longitudinal vehicle dynamics physics model for PHEV sedan.
    """
    def __init__(self):
        # Physical constants & Vehicle specs
        self.mass_kg = 1750.0            # Curb mass + payload
        self.gravity = 9.81              # m/s^2
        self.air_density = 1.225         # kg/m^3 at sea level
        self.frontal_area_m2 = 2.25      # Frontal cross-section area
        self.drag_coefficient_cd = 0.26  # Aerodynamic drag coeff
        self.rolling_res_coeff = 0.012   # Tire rolling resistance
        self.wheel_radius_m = 0.33       # Tire radius (18" wheels)
        self.final_drive_ratio = 8.5     # Gearbox reduction ratio
        self.generator_efficiency = 0.92

    def compute_motion_step(self, state: VehicleState, dt: float):
        """
        Execute one physics integration step (dt in seconds).
        Updates state.speed_kmh, acceleration, forces, odometer.
        """
        if not state.ignition_on or state.gear == Gear.PARK:
            state.speed_kmh = max(0.0, state.speed_kmh - (20.0 * dt))
            state.speed_mps = state.speed_kmh / 3.6
            state.acceleration_mps2 = 0.0
            return

        v = state.speed_mps

        # 1. Aerodynamic Drag Force: F_drag = 0.5 * rho * Cd * A * v^2
        f_drag = 0.5 * self.air_density * self.drag_coefficient_cd * self.frontal_area_m2 * (v ** 2)

        # 2. Rolling Resistance Force: F_roll = C_rr * m * g * cos(theta)
        slope_rad = math.atan(state.road_grade_pct / 100.0)
        f_roll = self.rolling_res_coeff * self.mass_kg * self.gravity * math.cos(slope_rad) if v > 0.05 else 0.0

        # 3. Grade / Slope Gravity Force: F_grade = m * g * sin(theta)
        f_grade = self.mass_kg * self.gravity * math.sin(slope_rad)

        total_resistive_force = f_drag + f_roll + f_grade

        # 4. Tractive / Braking Force at Wheels
        wheel_tractive_force = 0.0

        if state.gear == Gear.DRIVE:
            # Positive torque from powertrain
            wheel_torque = state.actual_wheel_torque_nm
            wheel_tractive_force = wheel_torque / self.wheel_radius_m

            # Friction braking
            friction_brake_force = (state.brake_pedal_pct / 100.0) * (self.mass_kg * 8.5) # up to ~0.85g deceleration
            wheel_tractive_force -= friction_brake_force

        elif state.gear == Gear.REVERSE:
            wheel_torque = -state.actual_wheel_torque_nm * 0.4
            wheel_tractive_force = wheel_torque / self.wheel_radius_m
            friction_brake_force = (state.brake_pedal_pct / 100.0) * (self.mass_kg * 8.5)
            wheel_tractive_force += friction_brake_force

        elif state.gear == Gear.NEUTRAL:
            wheel_tractive_force = 0.0
            friction_brake_force = (state.brake_pedal_pct / 100.0) * (self.mass_kg * 8.5)
            if v > 0:
                wheel_tractive_force -= friction_brake_force

        # 5. Net Force and Acceleration: F_net = m * a
        f_net = wheel_tractive_force - (total_resistive_force if v >= 0 else -total_resistive_force)
        acceleration = f_net / self.mass_kg

        # Clamp max physical acceleration/deceleration
        acceleration = max(-10.0, min(6.5, acceleration))

        # Integrate velocity
        new_v = v + acceleration * dt
        if new_v < 0 and state.gear == Gear.DRIVE:
            new_v = 0.0
            acceleration = 0.0
        elif new_v > 0 and state.gear == Gear.REVERSE:
            new_v = 0.0
            acceleration = 0.0

        # Top speed limiter (210 km/h)
        max_speed_mps = 210.0 / 3.6
        if state.drive_mode == DriveMode.LIMP_HOME:
            max_speed_mps = 50.0 / 3.6

        new_v = min(max_speed_mps, max(-30.0 / 3.6, new_v))

        # Update state
        state.speed_mps = new_v
        state.speed_kmh = round(abs(new_v) * 3.6, 1)
        state.acceleration_mps2 = round(acceleration, 2)

        # Distance accumulation
        distance_km = (abs(new_v) * dt) / 1000.0
        state.odometer_km = round(state.odometer_km + distance_km, 3)
        state.trip_distance_km = round(state.trip_distance_km + distance_km, 3)

        # Motor RPM matches wheel speed * final drive ratio
        wheel_rpm = (abs(new_v) / (2.0 * math.pi * self.wheel_radius_m)) * 60.0
        state.motor_rpm = round(wheel_rpm * self.final_drive_ratio, 0)
