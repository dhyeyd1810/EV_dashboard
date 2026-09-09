"""
can_bus.py - Virtual CAN Bus Broker & Frame Serializer
Simulates a broadcast CAN-FD physical layer with arbitration IDs, priority,
cyclic frame scheduling, latency, and hardware abstraction.
"""

import time
import json
import struct
from typing import Dict, Any, Callable, List, Optional
from bus.can_matrix import CAN_MATRIX, CANMessageDef

class CANFrame:
    __slots__ = ('msg_id', 'name', 'sender', 'timestamp_ms', 'data', 'dlc', 'crc')

    def __init__(self, msg_id: int, name: str, sender: str, data: Dict[str, Any], timestamp_ms: float = 0.0):
        self.msg_id = msg_id
        self.name = name
        self.sender = sender
        self.timestamp_ms = timestamp_ms or (time.time() * 1000.0)
        self.data = data
        self.dlc = len(data)
        self.crc = self._compute_crc(msg_id, data)

    def _compute_crc(self, msg_id: int, data: Dict[str, Any]) -> int:
        """Simulate an 8-bit checksum for CAN frame integrity verification"""
        val = msg_id & 0xFF
        for k, v in data.items():
            if isinstance(v, (int, float)):
                val = (val + int(abs(v) * 10)) & 0xFF
            elif isinstance(v, bool):
                val = (val + (1 if v else 0)) & 0xFF
        return val

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": f"0x{self.msg_id:03X}",
            "raw_id": self.msg_id,
            "name": self.name,
            "sender": self.sender,
            "ts": round(self.timestamp_ms, 1),
            "data": self.data,
            "crc": self.crc
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class VirtualCANBus:
    """
    Simulated Automotive CAN Bus Router.
    Allows ECUs to publish frames by Arbitration ID and listeners to subscribe.
    """
    def __init__(self):
        self._subscribers: List[Callable[[CANFrame], None]] = []
        self._message_buffer: Dict[int, CANFrame] = {}
        self._bus_load_pct: float = 18.5
        self._frame_count: int = 0
        self._error_frame_count: int = 0
        self._last_stats_time = time.time()
        self._frames_in_window = 0

    def subscribe(self, callback: Callable[[CANFrame], None]):
        """Register a callback (e.g. Dashboard WebSocket broadcaster or ECU node)"""
        self._subscribers.append(callback)

    def publish(self, msg_id: int, signal_values: Dict[str, Any], sender_name: str = "ECU") -> CANFrame:
        """Transmit a CAN frame onto the virtual bus"""
        def_spec: Optional[CANMessageDef] = CAN_MATRIX.get(msg_id)
        msg_name = def_spec.name if def_spec else f"MSG_0x{msg_id:03X}"
        sender = def_spec.sender_ecu if def_spec else sender_name

        frame = CANFrame(
            msg_id=msg_id,
            name=msg_name,
            sender=sender,
            data=signal_values,
            timestamp_ms=time.time() * 1000.0
        )

        # Store in latest state buffer
        self._message_buffer[msg_id] = frame
        self._frame_count += 1
        self._frames_in_window += 1

        # Broadcast to all connected nodes
        for sub in self._subscribers:
            try:
                sub(frame)
            except Exception as e:
                # Node error does not crash bus
                pass

        return frame

    def get_latest_frame(self, msg_id: int) -> Optional[CANFrame]:
        return self._message_buffer.get(msg_id)

    def get_all_latest(self) -> Dict[int, Dict[str, Any]]:
        return {msg_id: frame.to_dict() for msg_id, frame in self._message_buffer.items()}

    def update_bus_stats(self) -> Dict[str, Any]:
        """Compute virtual bus metrics (Frames/sec, load %)"""
        now = time.time()
        dt = now - self._last_stats_time
        if dt >= 1.0:
            fps = self._frames_in_window / dt
            self._bus_load_pct = min(95.0, max(5.0, (fps / 250.0) * 100.0))
            self._frames_in_window = 0
            self._last_stats_time = now

        return {
            "total_frames": self._frame_count,
            "error_frames": self._error_frame_count,
            "bus_load_pct": round(self._bus_load_pct, 1),
            "baudrate_kbps": 500
        }


# Global Virtual Bus Instance
global_can_bus = VirtualCANBus()
