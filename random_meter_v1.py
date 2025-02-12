import asyncio
from mavsdk import System
from mavsdk.offboard import OffboardError, PositionNedYaw
from mavsdk.offboard import PositionGlobalYaw
from mavsdk.telemetry import Heading, Position
import random
import math


def yaw_hesap(dx,dy):
    yaw_radians = math.atan2(dy,dx)
    yaw_degrees = math.degrees(yaw_radians)
    yaw_normalized = (yaw_degrees +360) % 360
    return yaw_normalized


async def baslangıc_konum(drone): # burada başlangıç konumumuzı alıyoruz.
    async for position in drone.telemetry.position():
        ilk_position = position
        print(f"Başlangıç Kuzey :{ilk_position.latitude_deg}, Başlangıç Doğu :{ilk_position.longitude_deg}")
        return ilk_position.latitude_deg, ilk_position.longitude_deg
        break


async def target_location():
    lat = 0
    long = 0
    yaw = 0
    while True:

        latrand = random.uniform(-10,10)
        longrand = random.uniform(-10,10)
        yaw = yaw_hesap(latrand, longrand)
        lat = lat + latrand
        long = long + longrand
        await asyncio.sleep(1)
        yield lat, long, yaw

async def connect_drone():
    drone = System()
    await drone.connect(system_address="udp://:14540")

    async for state in drone.core.connection_state():
        if state.is_connected:
            print("Drone bağlı!")
            break
    return drone

async def takeoff_(drone):
    await drone.action.arm()
    await drone.action.takeoff()
    await asyncio.sleep(1)
    print("Drone arm edildi!")

async def offfboard_gec(drone):
    try:
        await drone.offboard.set_position_ned(PositionNedYaw(0,0,0,0,))
        print("Offboard edildi!")
        await drone.offboard.start()
    except OffboardError as err:
        print(f"Offboard error: {err}")
        return False
    return True

async def hedefucus(drone,lat,long):
    async for lat, long, yaw in target_location():
        print(f"Yeni hedef: kuzey={lat}, doğu={long}, Yükseklik={20} m, Yaw:{yaw}")
        try:
            await drone.offboard.set_position_ned(PositionNedYaw(lat,long,-20,yaw,))
            await asyncio.sleep(1)
        except:
            print(f"Yeni hedef: Error")




async def main():
    drone = await connect_drone()
    lat,long = await baslangıc_konum(drone)
    await takeoff_(drone)
    await asyncio.sleep(5)
    await offfboard_gec(drone)
    while True:
        await hedefucus(drone,lat,long)


asyncio.run(main())


