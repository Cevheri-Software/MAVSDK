import asyncio
import math
import random

from mavsdk import System
from mavsdk.offboard import OffboardError, PositionNedYaw

flight_altitude = 20
data_rate = 0.5


def calculate_yaw(dx, dy):
    yaw_radians = math.atan2(dy, dx)
    yaw_degrees = math.degrees(yaw_radians)
    yaw_normalized = (yaw_degrees + 360) % 360
    return yaw_normalized


def body_to_ned(x_body, y_body, yaw_deg):
    yaw_rad = math.radians(yaw_deg)
    north = x_body * math.cos(yaw_rad) - y_body * math.sin(yaw_rad)
    east = x_body * math.sin(yaw_rad) + y_body * math.cos(yaw_rad)
    return north, east


async def generate_target_location():
    while True:
        dx = random.uniform(1.5, 2.5)  # İleri hareket
        dy = random.uniform(-1.5, 1.5) # Sağ/sol
        distance = math.sqrt(dx ** 2 + dy ** 2)
        await asyncio.sleep(data_rate)
        yield dx, dy, 0, distance


async def connect_drone():
    drone = System()
    await drone.connect(system_address="serial:///dev/ttyUSB0:57600")
    async for state in drone.core.connection_state():
        if state.is_connected:
            print("✅ Drone connected!")
            break
    return drone


async def takeoff(drone):
    await drone.action.hold()
    await asyncio.sleep(1)
    await drone.action.arm()
    await drone.action.takeoff()
    await asyncio.sleep(5)
    print("🚀 Drone takeoff completed!")


async def enter_offboard_mode(drone):
    try:
        await drone.offboard.set_position_ned(PositionNedYaw(0, 0, -flight_altitude, 0))
        await drone.offboard.start()
        print("🟢 Offboard mode activated!")
        return True
    except OffboardError as err:
        print(f"❌ Offboard error: {err}")
        return False


async def execute_mission(drone):
    ned_north_total = 0.0
    ned_east_total = 0.0

    async for dx, dy, _, distance in generate_target_location():
        # Drone'un güncel yönünü al
        async for attitude in drone.telemetry.attitude_euler():
            current_yaw = attitude.yaw_deg
            break

        # Göreli hareketi NED'e çevir
        north, east = body_to_ned(dx, dy, current_yaw)
        ned_north_total += north
        ned_east_total += east

        # Yeni yön açısı: o anki yaw + dx, dy'ye göre yönelme
        relative_yaw = calculate_yaw(dx, dy)
        target_yaw = (current_yaw + relative_yaw) % 360

        print(f"\n📦 Gelen veri: dx={dx:.2f} m, dy={dy:.2f} m")
        print(f"🧭 Mevcut yaw: {current_yaw:.2f}°, görece hedef yaw: {relative_yaw:.2f}°, toplam yaw: {target_yaw:.2f}°")
        print(f"📍 NED farkı: north={north:.2f}, east={east:.2f}")
        print(f"🎯 Yeni hedef pozisyon: north={ned_north_total:.2f}, east={ned_east_total:.2f}")

        await drone.offboard.set_position_ned(
            PositionNedYaw(ned_north_total, ned_east_total, -flight_altitude, target_yaw)
        )
        await asyncio.sleep(3.0)


async def main():
    drone = await connect_drone()
    await takeoff(drone)

    if not await enter_offboard_mode(drone):
        print("Programdan çıkılıyor...")
        return

    await execute_mission(drone)


if __name__ == "__main__":
    asyncio.run(main())
