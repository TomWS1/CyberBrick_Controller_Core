# CyberBrick ESP-NOW receiver in CyberBrick MicroPython flavor
# To be copied to CyberBrick Core, paired with X11 remote control receiver shield
# Control for the CyberBrick official truck
# https://makerworld.com/de/models/1396031-cyberbrick-official-truck
#
# The outputs of X11 shield are driven from following inputs:
# * Motors 1 & 2: controlled by Channels 1 & 2 where:
#     Throttle: ch2 L3, Left vertical stick 
#     Steering: ch1 L2, Left horizontal stick proportionally differing speed to each motor
#     On/Off: ch6 K1, 1-bit value, low-active ON (Button)


"""
The incoming telegram via ESP-NOW is expected in the following order:
 1)  ch0 L1, unsigned 12-bit value   (3-way switch on Cyberbrick official standard remote)
 2)  ch1 L2, unsigned 12-bit value   (Left horizontal (LH) stick)
 3)  ch2 L3, unsigned 12-bit value   (Left vertical (LV) stick)
 4)  ch3 R1, unsigned 12-bit value   (Slider)
 5)  ch4 R2, unsigned 12-bit value   (Right horizontal (RH) stick)
 6)  ch5 R3, unsigned 12-bit value   (Right vertical (LH) stick)
 7)  ch6 K1, 1-bit value, low-active (Button)
 8)  ch7 K2, 1-bit value, low-active (Not used)
 9)  ch9 K3, 1-bit value, low-active (Not used)
10) ch10 K4, 1-bit value, low-active (Not used)
"""

from machine import Pin, PWM
import network
import espnow
import asyncio
from neopixel import NeoPixel
import utime

DEAD_BAND   = 200
MAX_POT_VAL = 2048-DEAD_BAND

# Initialize all servo outputs with 1.5ms pulse length in 20ms period
#S1 = PWM(Pin(3), freq=50, duty_u16=4915) # servo center 1.5ms equals to 65535/20 * 1.5 = 4915
#S2 = PWM(Pin(2), freq=50, duty_u16=4915)
#S3 = PWM(Pin(1), freq=50, duty_u16=4915)
#S4 = PWM(Pin(0), freq=50, duty_u16=4915)

# Initialize motor 1 output to idle (a brushed motor is controlled via 2 pins on HTD8811)
M1A = PWM(Pin(4), freq=100, duty_u16=0)
M1B = PWM(Pin(5), freq=100, duty_u16=0)
M2A = PWM(Pin(7), freq=100, duty_u16=0)
M2B = PWM(Pin(6), freq=100, duty_u16=0)

def u16_limit(val):
  return (max(0,min(val,65535)))

def stop_motors():
  # Turn off both motor outputs
  M1A.duty_u16(0)
  M1B.duty_u16(0)
  M2A.duty_u16(0)
  M2B.duty_u16(0)

def run_motors_forwards(speed,steering):
  # speed of each motor depends on steering
  # steering = 0 then both motors run at same speed
  # steering > 0 then left motor runs faster than right motor
  # steering < 0 then right motor runs faster than left 
  M1B.duty_u16(0)
  M2B.duty_u16(0)
  modSpeed = 0
  steer = 0

  if steering == 0:
    M1A.duty_u16(speed)
    M2A.duty_u16(speed)
    modSpeed = speed

  elif steering > 0:
    steer = MAX_POT_VAL-steering
    modSpeed = int(speed*(steer/MAX_POT_VAL))
    M1A.duty_u16(speed)
    M2A.duty_u16(u16_limit(modSpeed))

  else:
    steer = MAX_POT_VAL+steering
    modSpeed = int(speed*(steer/MAX_POT_VAL))
    M2A.duty_u16(speed)
    M1A.duty_u16(u16_limit(modSpeed))
  
  parms = f"{speed},{steering},{steer},{modSpeed}"
  print(parms)

def run_motors_backwards(speed,steering):
  # speed of each motor depends on steering
  # steering = 0 then both motors run at same speed
  # steering > 0 then left motor runs faster than right motor
  # steering < 0 then right motor runs faster than left 
  M1A.duty_u16(0)
  M2A.duty_u16(0)
  modSpeed = 0
  steer = 0

  if steering == 0:
    M1B.duty_u16(speed)
    M2B.duty_u16(speed)
    modSpeed = speed

  elif steering > 0:
    steer = MAX_POT_VAL-steering
    modSpeed = int(speed*(steer/MAX_POT_VAL))
    M1B.duty_u16(speed)
    M2B.duty_u16(u16_limit(modSpeed))

  else:
    steer = MAX_POT_VAL+steering
    modSpeed = int(speed*(steer/MAX_POT_VAL))
    M2B.duty_u16(speed)
    M1B.duty_u16(u16_limit(modSpeed))

  parms = f"{speed},{steering},{steer},{modSpeed}"
  print(parms)


# Initialize Wi-Fi in station mode
sta = network.WLAN(network.STA_IF)
sta.active(True)
mac = sta.config('mac')
mac_address = ':'.join('%02x' % b for b in mac)
print("MAC address of the receiver:", mac_address)

mac_obj = {
  "device_name": "rx_duck", 
  "mac_address": mac_address
}

# Save Receiver's MAC address 
import ujson as js

filename = 'rx_mac.json'
try:
    with open(filename, 'w') as f:
        file_data = js.dumps(mac_obj)
        f.write(file_data)

except OSError as e:
    print('MAC write failed', e)
    raise


def wifi_reset():
  # Reset Wi-Fi to AP_IF off, STA_IF on and disconnected
  sta = network.WLAN(network.WLAN.IF_STA); sta.active(False)
  ap = network.WLAN(network.WLAN.IF_AP); ap.active(False)
  sta.active(True)
  while not sta.active():
      time.sleep(0.1)
  while sta.isconnected():
      time.sleep(0.1)
  sta = network.WLAN(network.STA_IF)
  sta.active(True)
  sta.config(channel=1,pm=sta.PM_NONE,reconnects=0)
  sta.disconnect()

wifi_reset()

# Initialize ESP-NOW
e = espnow.ESPNow()

def enow_reset():
  try:
      e.active(True)
  except OSError as err:
      print("Failed to initialize ESP-NOW:", err)
      raise

enow_reset()

# Drive NeoPixel on CyberBrick Core
npcore = Pin(8, Pin.OUT)
np = NeoPixel(npcore, 1)
np[0] = (0, 10, 0) # dim green
np.write()

prev_button       = 1
midpoint_th       = 2047
midpoint_st       = 2047
deadzoneplusminus = DEAD_BAND

while True:
  try:
    # Receive message (host MAC, message, 500ms failsafe timeout)
    host, msg = e.recv(500)
    if msg == None:
      # Failsafe
      # Motor off, no change to steering
      print("Failsafe!")
      stop_motors()

      e.active(False)
      wifi_reset()
      enow_reset()
    
    else:
      rxch = msg.decode().split(",")
      #print(rxch)

      if len(rxch) == 10:
        # assuming that we received valid message
        steering = int(rxch[1])
        throttle = int(rxch[2])
        speed = 0

        button = int(rxch[6])
        #deadzone update
        if (button == 0 and button != prev_button): # is button pressed? first trigger, normalize joystick
          midpoint_th = int(throttle)   # set new midpoint
          midpoint_st = int(steering)   # set new midpoint
          
        prev_button = button

        # ADD SHUTOFF IF NO BUTTON!!!

        #deadzone check
        if ((steering < (midpoint_st+deadzoneplusminus)) and (steering > (midpoint_st-deadzoneplusminus))):
          #deadzone - no steering
          steering = 0

        elif steering < (midpoint_st-deadzoneplusminus):
          steering -= (midpoint_st-deadzoneplusminus)

        else:
          steering -= (midpoint_st+deadzoneplusminus)

        if ((throttle < (midpoint_th+deadzoneplusminus)) and (throttle > (midpoint_th-deadzoneplusminus))):
          #deadzone - no forward/backward movement
          stop_motors()
          speed = 0
            
        else:
          if throttle > midpoint_th:
            # forwards
            speed = u16_limit((32*(throttle-midpoint_th)))
            run_motors_forwards(speed,steering)
  
          else:
            # backwards
            speed = u16_limit((32*(midpoint_th-throttle)))
            run_motors_backwards(speed,steering)


  except OSError as err:
    print("Error:", err)
    stop_motors()
    time.sleep(0.5)
    e.active(False)
    wifi_reset()
    enow_reset()

  except KeyboardInterrupt:
    print("Stopping receiver...")
    stop_motors()
    e.active(False)
    sta.active(False)
    break
