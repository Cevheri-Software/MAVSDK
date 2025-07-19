import asyncio
import math
import random
from mavsdk import System
from mavsdk.offboard import OffboardError, PositionNedYaw

flight_altitude = 20
data_rate = 0.5

# Emergency termination flag
mission_active = True

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
    while mission_active:  # Check mission status
        dx = random.uniform(1.5, 2.5)  # İleri hareket
        dy = random.uniform(-1.5, 1.5) # Sağ/sol
        distance = math.sqrt(dx ** 2 + dy ** 2)
        await asyncio.sleep(data_rate)
        yield dx, dy, distance  # Fixed syntax: removed invalid * and extra parameter

async def connect_drone():
    drone = System()
    try:
        await drone.connect(system_address="serial:///dev/ttyUSB0:57600")
        
        # Add timeout for connection
        timeout_counter = 0
        async for state in drone.core.connection_state():
            if state.is_connected:
                print("✅ Drone connected!")
                break
            timeout_counter += 1
            if timeout_counter > 30:  # 30 second timeout
                raise Exception("Connection timeout")
            await asyncio.sleep(1)
        return drone
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        raise

async def takeoff(drone):
    try:
        await drone.action.hold()
        await asyncio.sleep(1)
        await drone.action.arm()
        await drone.action.takeoff()
        await asyncio.sleep(5)
        print("🚀 Drone takeoff completed!")
    except Exception as e:
        print(f"❌ Takeoff failed: {e}")
        raise

async def enter_offboard_mode(drone):
    try:
        await drone.offboard.set_position_ned(PositionNedYaw(0, 0, -flight_altitude, 0))
        await drone.offboard.start()
        print("🟢 Offboard mode activated!")
        return True
    except OffboardError as err:
        print(f"❌ Offboard error: {err}")
        return False
    except Exception as e:
        print(f"❌ Failed to enter offboard mode: {e}")
        return False

async def get_current_attitude(drone, timeout_seconds=5):
    """Get current drone attitude with timeout protection"""
    try:
        # Use asyncio.wait_for to add timeout protection
        async def get_attitude():
            async for attitude in drone.telemetry.attitude_euler():
                return attitude.yaw_deg
        
        current_yaw = await asyncio.wait_for(get_attitude(), timeout=timeout_seconds)
        return current_yaw
    except asyncio.TimeoutError:
        print("⚠️ Warning: Attitude telemetry timeout, using last known yaw")
        return None
    except Exception as e:
        print(f"⚠️ Warning: Attitude telemetry error: {e}")
        return None

async def emergency_landing(drone):
    """Perform emergency landing procedure"""
    global mission_active
    mission_active = False
    try:
        print('\n🚨 INITIATING EMERGENCY LANDING')
        await drone.offboard.stop()
        await drone.action.land()
        print('✅ Emergency landing initiated')
    except Exception as e:
        print(f'❌ Emergency landing failed: {e}')

async def execute_mission(drone):
    global mission_active
    ned_north_total = 0.0
    ned_east_total = 0.0
    last_known_yaw = 0.0  # Fallback yaw value
    
    try:
        async for dx, dy, distance in generate_target_location():
            if not mission_active:
                print("🛑 Mission terminated")
                break
                
            # Get drone's current attitude with timeout protection
            current_yaw = await get_current_attitude(drone)
            if current_yaw is None:
                print(f"⚠️ Using last known yaw: {last_known_yaw:.2f}°")
                current_yaw = last_known_yaw
            else:
                last_known_yaw = current_yaw
            
            # Convert relative movement to NED
            north, east = body_to_ned(dx, dy, current_yaw)
            ned_north_total += north
            ned_east_total += east
            
            # Calculate new target yaw: current yaw + relative yaw from dx, dy
            relative_yaw = calculate_yaw(dx, dy)
            target_yaw = (current_yaw + relative_yaw) % 360
            
            print(f"\n📦 Gelen veri: dx={dx:.2f} m, dy={dy:.2f} m")
            print(f"🧭 Mevcut yaw: {current_yaw:.2f}°, görece hedef yaw: {relative_yaw:.2f}°, toplam yaw: {target_yaw:.2f}°")
            print(f"📍 NED farkı: north={north:.2f}, east={east:.2f}")
            print(f"🎯 Yeni hedef pozisyon: north={ned_north_total:.2f}, east={ned_east_total:.2f}")
            
            try:
                await drone.offboard.set_position_ned(
                    PositionNedYaw(ned_north_total, ned_east_total, -flight_altitude, target_yaw)
                )
                await asyncio.sleep(3.0)
            except OffboardError as offboard_err:
                print(f"\n❌ Offboard control error: {offboard_err}")
                break
            except Exception as pos_err:
                print(f"\n❌ Position command error: {pos_err}")
                break
                
    except Exception as e:
        print(f"\n❌ Mission execution error: {e}")
    finally:
        mission_active = False

async def main():
    global mission_active
    try:
        drone = await connect_drone()
        await takeoff(drone)
        
        if not await enter_offboard_mode(drone):
            print("❌ Programdan çıkılıyor...")
            return
        
        # Execute mission with proper error handling
        await execute_mission(drone)
        
    except KeyboardInterrupt:
        print('\n🛑 Mission interrupted by user')
        await emergency_landing(drone)
    except Exception as e:
        print(f'\n❌ Fatal error: {e}')
        if 'drone' in locals():
            await emergency_landing(drone)
    finally:
        mission_active = False

if __name__ == "__main__":
    asyncio.run(main())
