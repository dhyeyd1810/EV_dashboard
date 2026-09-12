"""
server.py - High-Performance Async Telemetry & CAN Bus Server
Serves the digital dashboard, broadcasts real-time CAN bus frames over WebSockets at 20-50Hz,
and exposes RESTful APIs for driver inputs, drive cycles, and fault injection.
"""

import os
import sys
import json
import asyncio
import logging
import threading
import webbrowser
from aiohttp import web

from core.vehicle_sim import global_simulator
from bus.can_bus import global_can_bus

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("EV_SERVER")

# Set of active WebSocket connections
connected_websockets = set()

async def websocket_handler(request):
    """Handles real-time bi-directional telemetry and command stream"""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    connected_websockets.add(ws)
    logger.info(f"Dashboard client connected. Active clients: {len(connected_websockets)}")

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    payload = json.loads(msg.data)
                    msg_type = payload.get("type", "")

                    if msg_type == "control":
                        ctrl_data = payload.get("data")
                        if not isinstance(ctrl_data, dict):
                            ctrl_data = {k: v for k, v in payload.items() if k != "type"}
                        global_simulator.apply_driver_control(ctrl_data)
                    elif msg_type == "fault_inject":
                        fault_name = payload.get("fault", "")
                        enabled = payload.get("enabled", True)
                        global_simulator.inject_fault(fault_name, enabled)
                    elif msg_type == "reset_faults":
                        global_simulator.reset_all_faults()
                    elif msg_type == "ping":
                        await ws.send_json({"type": "pong"})
                except Exception as e:
                    logger.error(f"Error handling WS message: {e}")
            elif msg.type == web.WSMsgType.ERROR:
                logger.error(f"WebSocket closed with exception: {ws.exception()}")
    finally:
        connected_websockets.discard(ws)
        logger.info(f"Dashboard client disconnected. Active clients: {len(connected_websockets)}")

    return ws

async def api_get_telemetry(request):
    """REST endpoint returning complete instantaneous vehicle state"""
    return web.json_response(global_simulator.get_full_telemetry_snapshot())

async def api_get_can_frames(request):
    """REST endpoint returning latest CAN frame buffer and bus statistics"""
    bus_stats = global_can_bus.update_bus_stats()
    return web.json_response({
        "stats": bus_stats,
        "frames": global_can_bus.get_all_latest()
    })

async def api_post_control(request):
    """REST endpoint for driver controls (pedals, gear, mode)"""
    try:
        data = await request.json()
        global_simulator.apply_driver_control(data)
        return web.json_response({"status": "ok", "applied": data})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=400)

async def api_post_fault(request):
    """REST endpoint for fault injection"""
    try:
        data = await request.json()
        fault = data.get("fault")
        enabled = data.get("enabled", True)
        if fault == "reset":
            global_simulator.reset_all_faults()
        else:
            global_simulator.inject_fault(fault, enabled)
        return web.json_response({"status": "ok", "fault": fault, "enabled": enabled})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=400)

async def simulation_loop_task():
    """High-frequency 50Hz (20ms) real-time simulation background task"""
    logger.info("Starting real-time vehicle simulation loop at 50Hz...")
    dt = 0.02 # 20ms physics step
    broadcast_counter = 0

    while True:
        try:
            start_t = asyncio.get_event_loop().time()

            # Step physical model and all ECUs
            global_simulator.step(dt)

            # Broadcast to UI clients at ~25Hz (every 2 physics ticks)
            broadcast_counter += 1
            if broadcast_counter % 2 == 0 and connected_websockets:
                snapshot = global_simulator.get_full_telemetry_snapshot()
                bus_stats = global_can_bus.update_bus_stats()
                can_buffer = global_can_bus.get_all_latest()

                msg_payload = {
                    "type": "telemetry",
                    "data": snapshot,
                    "can_bus": {
                        "stats": bus_stats,
                        "latest_frames": can_buffer
                    }
                }
                msg_str = json.dumps(msg_payload)

                # Broadcast concurrently
                tasks = [ws.send_str(msg_str) for ws in list(connected_websockets) if not ws.closed]
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

            elapsed = asyncio.get_event_loop().time() - start_t
            sleep_time = max(0.001, dt - elapsed)
            await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in simulation loop: {e}", exc_info=True)
            await asyncio.sleep(0.05)

async def start_background_tasks(app):
    app['sim_task'] = asyncio.create_task(simulation_loop_task())

async def cleanup_background_tasks(app):
    if 'sim_task' in app:
        app['sim_task'].cancel()
        try:
            await app['sim_task']
        except asyncio.CancelledError:
            pass

import socket

def get_local_ip():
    """Detect the local machine LAN IP address for cross-device tablet pairing"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

async def api_get_host_info(request):
    """REST endpoint returning server host LAN IP and pairing URLs"""
    ip = get_local_ip()
    host_header = request.headers.get("Host", "")
    port = host_header.split(":")[-1] if ":" in host_header else "8080"
    return web.json_response({
        "local_ip": ip,
        "port": port,
        "dashboard_url": f"http://{ip}:{port}/",
        "simulation_url": f"http://localhost:{port}/simulation"
    })

def create_app():
    app = web.Application()

    # REST APIs
    app.router.add_get('/api/host-info', api_get_host_info)
    app.router.add_get('/api/telemetry', api_get_telemetry)
    app.router.add_get('/api/can', api_get_can_frames)
    app.router.add_post('/api/control', api_post_control)
    app.router.add_post('/api/fault', api_post_fault)

    # WebSocket Stream
    app.router.add_get('/ws', websocket_handler)

    # Static Assets & Pages
    static_dir = os.path.join(os.path.dirname(__file__), 'static')
    if not os.path.exists(static_dir):
        os.makedirs(static_dir, exist_ok=True)

    app.router.add_static('/static/', path=static_dir, name='static')

    async def dashboard_page(request):
        return web.FileResponse(os.path.join(static_dir, 'index.html'))

    async def simulation_page(request):
        return web.FileResponse(os.path.join(static_dir, 'simulation.html'))

    app.router.add_get('/', dashboard_page)
    app.router.add_get('/dashboard', dashboard_page)
    app.router.add_get('/tablet', dashboard_page)
    app.router.add_get('/cluster', dashboard_page)
    app.router.add_get('/simulation', simulation_page)
    app.router.add_get('/sim', simulation_page)
    app.router.add_get('/control', simulation_page)

    app.on_startup.append(start_background_tasks)
    app.on_cleanup.append(cleanup_background_tasks)

    return app

def open_browsers(port: int):
    """Automatically launch both the Cockpit Dashboard and PC Simulation tabs"""
    import time
    time.sleep(0.8)
    cockpit_url = f"http://localhost:{port}/"
    sim_url = f"http://localhost:{port}/simulation"
    try:
        # Open Cockpit tab (to drag to Legion Tab)
        webbrowser.open(cockpit_url)
        time.sleep(0.4)
        # Open Simulation Lab tab (to keep on PC)
        webbrowser.open(sim_url)
    except Exception as e:
        logger.warning(f"Could not automatically open browsers: {e}")

def run_server():
    """Runs server with automatic port fallback if port is in use"""
    base_port = int(os.environ.get("PORT", 8080))
    local_ip = get_local_ip()

    for port in range(base_port, base_port + 10):
        url_local = f"http://localhost:{port}"
        url_sim = f"http://localhost:{port}/simulation"
        url_cockpit = f"http://localhost:{port}/"
        try:
            logger.info("=" * 65)
            logger.info("  AURA HYBRID EV TELEMETRY & CONTROL SERVER")
            logger.info(f"  > Tab 1 (Cockpit Dashboard):    {url_cockpit}")
            logger.info(f"  > Tab 2 (PC Simulation Lab):    {url_sim}")
            logger.info("=" * 65)
            threading.Thread(target=open_browsers, args=(port,), daemon=True).start()
            # Pass fresh app factory or instance to avoid loop re-initialization error
            app = create_app()
            web.run_app(app, host='0.0.0.0', port=port, print=None)
            break
        except OSError as e:
            if getattr(e, 'errno', None) in (10048, 98): # Port in use
                logger.warning(f"Port {port} in use, trying port {port + 1}...")
                continue
            raise

if __name__ == '__main__':
    run_server()


