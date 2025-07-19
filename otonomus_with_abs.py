import asyncio
import math
import random

from mavsdk import System
from mavsdk.offboard import OffboardError, PositionNedYaw

# flight_altitude = int(input('FLIGHT ALTITUDE: '))
# data_rate = float(input('DATA RATE: '))
flight_altitude = 20
data_rate = 0.1

# Critical battery level for emergency landing
CRITICAL_BATTERY_PERCENT = 15.0

def calculate_yaw(dx, dy):
    yaw_radians = math.atan2(dy, dx)
    yaw_degrees = math.degrees(yaw_radians)
    yaw_normalized = (yaw_degrees + 360) % 360
    return yaw_normalized


async def get_initial_position(drone):
    async for position in drone.telemetry.position():
        initial_position = position
        print(f'Initial North: {initial_position.latitude_deg}, '
              f'Initial East: {initial_position.longitude_deg}')
        return initial_position.latitude_deg, initial_position.longitude_deg

# Function will be changed to: take_target_location()
# // Function codes will be changed following the dynamic target location data. It'll be taken from the algorithm and the fusion tracking algorithm's target data output.
# // It will be a dynamic function and will be referred in the 77th code line

async def generate_target_location(): 
    lat, long = 0, 0
    while True:
        latrand = random.uniform(-1.5, 1.5)
        longrand = random.uniform(-1.5, 1.5)
        yaw = calculate_yaw(latrand, longrand)
        lat += latrand
        long += longrand
        distance = math.sqrt(math.pow(lat, 2) + math.pow(long, 2))
        await asyncio.sleep(data_rate)
        yield lat, long, yaw, distance


async def connect_drone():
    drone = System()
    await drone.connect(system_address='udp://:14540')

    async for state in drone.core.connection_state():
        if state.is_connected:
            print('Drone connected!')
            break
    return drone


async def takeoff(drone):
    await drone.action.hold()
    await asyncio.sleep(1)
    await drone.action.arm()
    await drone.action.takeoff()
    await asyncio.sleep(1)
    print('Drone armed!')


async def enter_offboard_mode(drone):
    try:
        await drone.offboard.set_position_ned(PositionNedYaw(0, 0, 0, 0))
        print('Offboard mode activated!')
        await drone.offboard.start()
    except OffboardError as err:
        print(f'Offboard error: {err}')
        return False
    return True


async def execute_mission(drone, shared_data):
    async for lat, long, yaw, distance in generate_target_location():
        # Check if mission should terminate due to critical battery
        if shared_data.get('critical_battery', False):
            print('\n🚨 CRITICAL BATTERY - MISSION TERMINATED')
            break
            
        shared_data['mission'] = (
            f'North: {lat:.2f}, East: {long:.2f}, Yaw: {yaw:.2f}, Distance: {distance:.2f}'
        )
        await print_status(shared_data)
        
        try:
            await drone.offboard.set_position_ned(
                PositionNedYaw(lat, long, -flight_altitude, yaw)
            )
            await asyncio.sleep(data_rate)
        except OffboardError as offboard_err:
            print(f'\n❌ Offboard control error: {offboard_err}')
            break
        except Exception as e:
            print(f'\n❌ Mission error: {e}')
            break

# The static 'current' value on line 94 will be replaced with a dynamic variable from telemetry.
async def monitor_battery_status(drone, shared_data):
    battery_capacity_a, battery_capacity_v = 16, 22.2
    battery_energy = battery_capacity_a * battery_capacity_v
    current = 70 / 3600 
    remaining_time = 0

    async for battery in drone.telemetry.battery():
        voltage = battery.voltage_v
        power = voltage * current
        
        if power > 0:
            # Convert power (watts) to energy consumed per second (watt-seconds)
            energy_consumed_per_second = power
            battery_energy -= energy_consumed_per_second
            
            # Prevent negative battery energy
            battery_energy = max(0, battery_energy)
            
            percent = (battery_energy / (battery_capacity_a * battery_capacity_v)) * 100
            
            # Safe division - only calculate remaining time if power > 0
            remaining_time = (battery_energy / power) / 60
        else:
            # Handle case when power is 0 or negative
            percent = 0
            remaining_time = 0
            print('\n⚠️ Warning: Power calculation resulted in 0 or negative value')

        # Check for critical battery level
        if percent <= CRITICAL_BATTERY_PERCENT:
            shared_data['critical_battery'] = True
            print(f'\n🚨 CRITICAL BATTERY: {percent:.1f}% - INITIATING EMERGENCY PROCEDURES')

        shared_data['battery'] = (
            f'Power: {power:.2f}W, Percent: {percent:.2f}%, Remaining: {remaining_time:.1f}min, '
            f'Current: {current:.2f}A, Voltage: {voltage:.2f}V'
        )
        await print_status(shared_data)
        await asyncio.sleep(1)


async def emergency_landing(drone):
    """Perform emergency landing procedure"""
    try:
        print('\n🚨 INITIATING EMERGENCY LANDING')
        await drone.offboard.stop()
        await drone.action.land()
        print('✅ Emergency landing initiated')
    except Exception as e:
        print(f'❌ Emergency landing failed: {e}')


async def print_status(shared_data):
    print(f'\r🔋 BATTERY: {shared_data["battery"]} ]   '
          f'[✈️ MISSION: {shared_data["mission"]} ', end='', flush=True)
    await asyncio.sleep(data_rate)


async def main():
    try:
        drone = await connect_drone()
        await takeoff(drone)
        await asyncio.sleep(1)

        if not await enter_offboard_mode(drone):
            print('Failed to enter Offboard mode! Exiting...')
            return

        shared_data = {'battery': 'N/A', 'mission': 'Starting', 'critical_battery': False}

        mission_task = asyncio.create_task(execute_mission(drone, shared_data))
        battery_task = asyncio.create_task(monitor_battery_status(drone, shared_data))

        # Wait for either task to complete (mission end or critical battery)
        done, pending = await asyncio.wait(
            [mission_task, battery_task], 
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # Cancel remaining tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Perform emergency landing if critical battery
        if shared_data.get('critical_battery', False):
            await emergency_landing(drone)
            
    except KeyboardInterrupt:
        print('\n🛑 Mission interrupted by user')
        await emergency_landing(drone)
    except Exception as e:
        print(f'\n❌ Fatal error: {e}')
        await emergency_landing(drone)


if __name__ == "__main__":
    asyncio.run(main())
