# PHEV // Next-Gen Hybrid Embedded Digital Cluster & Simulation Architecture

A high-fidelity software simulation and digital cockpit dashboard built for an **Embedded Systems Architecture** course. It models a modern **Plug-in Hybrid Electric Vehicle (PHEV)** with dual electric & internal combustion powertrains, realistic Electronic Control Units (ECUs), a virtual CAN-FD message bus with DBC specifications, thermal management loops, 96-cell BMS monitoring, and an interactive fault injection testing suite.

---

##  System Architecture & ECU Partitioning

The architecture follows automotive industry standards (AUTOSAR / ISO 26262 ASIL) where independent ECU nodes communicate cyclically over a broadcast CAN bus:

```
                                +-------------------------------+
                                |  VIRTUAL CAN-FD BUS (500kbps) |
                                +---------------+---------------+
                                                |
        +-----------------------+---------------+-----------------------+
        |                       |               |                       |
+-------v-------+       +-------v-------+   +---v-----------+   +-------v-------+
|    BMS ECU    |       |    ICE ECU    |   |   MOTOR ECU   |   |    HCU ECU    |
| (CAN ID 0x100)|       | (CAN ID 0x110)|   | (CAN ID 0x120)|   | (CAN ID 0x200)|
+---------------+       +---------------+   +---------------+   +---------------+
        |                       |               |                       |
+-------v-------+       +-------v-------+   +---v-----------+           |
|  CHASSIS ECU  |       |  THERMAL ECU  |   |   DIAG ECU    |           |
| (CAN ID 0x210)|       | (CAN ID 0x300)|   | (CAN ID 0x7E0)|           |
+---------------+       +---------------+   +---------------+           |
                                                |                       |
                                                +-----------+-----------+
                                                            | (WebSocket / UART)
                                                +-----------v-----------+
                                                | DIGITAL COCKPIT CLUSTER|
                                                | (HTML5 / Canvas / JS) |
                                                +-----------------------+
```

---

##  CAN-FD Message & DBC Specification Matrix

| CAN ID | Message Name | Transmitter ECU | Cycle (ms) | Key Signals & Units |
|---|---|---|---|---|
| **`0x100`** | `BMS_Pack_Status` | `BMS_ECU` | 50ms | SoC (%), SoH (%), Pack Voltage (V), Current (A), Max Cell Temp (°C), Isolation ($k\Omega$) |
| **`0x110`** | `ICE_Engine_Status` | `ICE_ECU` | 20ms | Engine State (0-3), RPM, Torque (Nm), Output Power (kW), Coolant Temp (°C), Fuel Flow (L/h) |
| **`0x120`** | `EMotor_Inverter_Status` | `MOTOR_ECU` | 20ms | Motor RPM, Torque (Nm), Power (kW), Inverter Temp (°C), Stator Temp (°C), Efficiency (%) |
| **`0x200`** | `HCU_PowerSplit_Status` | `HCU_ECU` | 20ms | Powertrain Mode (EV/Series/Parallel/Direct/Regen), Drive Mode, Speed (km/h), EV & Gas Range (km) |
| **`0x210`** | `Chassis_ADAS_Status` | `CHASSIS_ECU` | 100ms | 4x TPMS Pressure (psi) & Temp (°C), Radar Distance (m), Blind Spot L/R, ABS/TCS flags |
| **`0x300`** | `Thermal_HVAC_Status` | `THERMAL_ECU` | 250ms | Battery Coolant Flow (L/min), Radiator Fan Speed (%), Cabin Temp (°C), HVAC Power (kW) |
| **`0x7E0`** | `UDS_Diagnostics_DTC` | `DIAG_ECU` | 100ms | Active DTC Count, Highest Severity, Limp-Home Mode active, MIL Check Engine flag |

---

##  Mathematical & Physics Models

### 1. Vehicle Longitudinal Dynamics
$$F_{net} = F_{wheel} - (F_{drag} + F_{roll} + F_{grade})$$
- **Aerodynamic Drag**: $F_{drag} = \frac{1}{2} \rho C_d A v^2$ (with $\rho = 1.225\text{ kg/m}^3, C_d = 0.26, A = 2.25\text{ m}^2$)
- **Rolling Resistance**: $F_{roll} = C_{rr} m g \cos(\theta)$
- **Longitudinal Acceleration**: $a = \frac{F_{net}}{m}$

### 2. High-Voltage Battery Management (BMS)
- **Open Circuit Voltage (OCV)**: Modeled using non-linear Li-ion polynomial:
  $$V_{cell\_ocv} = 3.20 + 0.90 \cdot \text{SoC} + 0.10 \cdot \text{SoC}^3$$
- **Terminal Voltage**: $V_{term} = V_{ocv} - I R_{int}$
- **Coulomb Counting**: $\Delta \text{SoC} = \frac{\int I \, dt}{Q_{nominal}} \times 100\%$
- **Joule Heating**: $Q_{heat} = I^2 R_{int} \Delta t$

### 3. Internal Combustion Engine & Fuel Efficiency
- **Power Output**: $P_{ICE} = \frac{\tau \cdot \text{RPM}}{9549}$ (kW)
- **Brake Specific Fuel Consumption (BSFC)**: Interpolated BSFC sweet-spot ($230\text{ g/kWh}$) mapped to instantaneous fuel flow:
  $$\text{Fuel Flow (L/h)} = \frac{P_{ICE} \cdot \text{BSFC}}{740 \times 3600} \times 3600$$

---

## 🛠️ How to Run

1. **Start the Python Telemetry & Virtual CAN Server**:
   ```bash
   python server.py
   ```
2. **Open the Digital Cockpit in your Browser**:
   ```
   http://localhost:8080
   ```

###  Interactive Controls & Keyboard Shortcuts
- **W / ArrowUp**: Accelerate (increases throttle %)
- **S / ArrowDown**: Brake (applies regenerative & friction braking)
- **Space**: Emergency Full Stop
- **P / R / N / D / B**: Select Transmission Gear
- **Click 'CONTROLS & FAULTS'**: Open the live control drawer to toggle drive modes, slider inputs, and inject hardware faults.

---

##  Future Hardware Integration (Microcontroller Ready)

The code utilizes a clean **Hardware Abstraction Layer (HAL)**:
- To bridge to physical hardware (e.g. **ESP32**, **STM32**, or **Raspberry Pi** with an **MCP2515 CAN transceiver**), implement a serial reader in `bus/hal_bridge.py` that listens on a USB COM port and feeds CAN frames directly into `global_can_bus.publish()`.
- The dashboard UI and simulation logic will consume physical sensor frames with zero modifications.
