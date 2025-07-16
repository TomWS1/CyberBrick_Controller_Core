# CyberBrick ESP-NOW receiver in CyberBrick MicroPython flavor
# To be copied to CyberBrick Core, paired with X11 remote control receiver shield
# Control for the CyberBrick RC Crab
# https://makerworld.com/en/models/1415889-rc-crab-cyberbrick?from=search#profileId-1470427
#
# The outputs of X11 shield are driven from following inputs:
# * Servo1: not used
# * Servo2: not used
# * Servo3: not used
# * Servo4: not used
# * Motor1: channel 1 (Left horizontal (LH) stick) Both Motors are used, Walking is left stick, turning is right stick
# * Motor2: channel 4 (Right horizontal (RH) stick)
# * NeoPixel_Channel1: not driven by this code
# * NeoPixel_Channel2: Not used at moment, will be used for 'Eyes'

# In CyberBrick RC Crab, only 2 NeoPixels are connected to channel2, 1 - Left Eye, 2 - Right Eye

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

TURNING_STICK = 4    # Right Horizontal Stick, used for Turning Direction
WALKING_STICK = 1    # Left Horizontal Stick, used for walking speed

# Initialize motors output to idle (a brushed motor is controlled via 2 pins on HTD8811)
M1A = PWM(Pin(4), freq=100, duty_u16=0)
M1B = PWM(Pin(5), freq=100, duty_u16=0)
M2A = PWM(Pin(6), freq=100, duty_u16=0)
M2B = PWM(Pin(7), freq=100, duty_u16=0)

def stop_motors():
  # Turn off both motor outputs
  M1A.duty_u16(0)
  M1B.duty_u16(0)
  M2A.duty_u16(0)
  M2B.duty_u16(0)


# Initialize Wi-Fi in station mode
sta = network.WLAN(network.STA_IF)
sta.active(True)

mac = sta.config('mac')
mac_address = ':'.join('%02x' % b for b in mac)
print("MAC address of the receiver:", mac_address)

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

printloopctr = 0

    
# Drive NeoPixel on CyberBrick Core
npcore = Pin(8, Pin.OUT)
np = NeoPixel(npcore, 1)
np[0] = (0, 10, 0) # dim green
np.write()

# use a table to control eye color
color_scheme = [
  (0, 0, 0),         # initially eyes are off (RGB=0,0,0)
  (0, 0, 127),       # then half blue
  (0, 0, 255),        # full blue
  (0, 127, 0),        # half green
  (0, 255, 0),        # full green
  (127, 0, 0),        # half red
  (255, 0, 0)         # full red
]

color_index = -1      # start color index at invalid value so first press nulls the joystick

LEDstring2pin = Pin(20, Pin.OUT)           # define the pin used for the LED2 string
LEDstring2 = NeoPixel(LEDstring2pin, 2)    # tell the Neopixel driver that there are TWO LEDs in the string.
for i in range(2):
  LEDstring2[i] = (0, 0, 0) # default all off
LEDstring2.write()

button = 0                                 # variable to accept the latest button state
last_button = 1                            # and a history of the last state to differentiate it
blinkertime_ms    = 750  # 1.5 Hz

#  function to differentiate the button, signal when it 'falls', ie, pushed.
def button_falling(button):
  global last_button
  if (button == 0 and button != last_button):  # pushed but previously not?
    last_button = button
    return True 

  else:
    last_button = button   # not falling so simply record the latest state.
    return False


# for deadzone check
midpoint = 2047
deadzoneplusminus = 200

# main control loop
while True:
  try:
    # Receive message (host MAC, message, 500ms failsafe timeout)
    host, msg = e.recv(500)
    if msg == None:
      # Failsafe
      # Motor off, no change to steering
      stop_motors()
      # blinking red LEDs
      color_index = 0
      if ((utime.ticks_ms() % blinkertime_ms) > (blinkertime_ms / 2)):
        for i in range(2):
          LEDstring2[i] = (0, 0, 0) # All dark
      else:
        for i in range(2):
          LEDstring2[i] = (255, 0, 0) # All red
      LEDstring2.write()

      e.active(False)
      wifi_reset()
      enow_reset()
    
    else:  # got a good message, split it into individual data fields and process it
      rxch = msg.decode().split(",")
      if len(rxch) == 10:
        
        walking = int(rxch[WALKING_STICK])  # speed is controlled by walking control
        turning = int(rxch[TURNING_STICK])  # direction is controlled by turning control
        beingTurned = 0
        direction = 0           # direction = 0, right turn, = 1, left turn (I think...)
        speed = 0
        button = int(rxch[6])   # the single pushbutton on the standard remote

        #deadzone update
        if (button_falling(button)): # is button pressed? 
          if (color_index < 0):      # first time set the midpoint to null the joystick
            midpoint = int(rxch[WALKING_STICK])   # set new midpoint
            color_index = 0
          else:
            rgb = color_scheme[color_index]    # subsequent pushes change the eye color
            color_index = ((color_index+1) % len(color_scheme))
            for i in range(2):
              LEDstring2[i] = rgb
            LEDstring2.write()

        # first see if we're turning
        if ((turning < (midpoint+deadzoneplusminus)) and (turning > (midpoint-deadzoneplusminus))):
          # no, motion is just walking
          beingTurned = 0
        else:
          beingTurned = 1  # the motion is turning, direction is controlled by turning control
          if (turning < midpoint):
            direction = 1
          else:
            direction = 0

        if ((walking < (midpoint+deadzoneplusminus)) and (walking > (midpoint-deadzoneplusminus))):
          # motion stopped
          speed = 0
        else:
          if (walking > midpoint):
            speed = min(32*(walking-midpoint), 65535)
          else:
            speed = min(32*(midpoint-walking), 65535)

        if (speed == 0):
          M1A.duty_u16(0)
          M1B.duty_u16(0)
          M2A.duty_u16(0)
          M2B.duty_u16(0)

        else:
          if (beingTurned == 0):
            if (walking > midpoint):
              M1B.duty_u16(0)
              M1A.duty_u16(speed)
              M2A.duty_u16(0)
              M2B.duty_u16(speed)
            else:
              M1A.duty_u16(0)
              M1B.duty_u16(speed)
              M2B.duty_u16(0)
              M2A.duty_u16(speed)

          else:
            if (direction == 0):
              if (walking > midpoint):
                M1B.duty_u16(0)
                M1A.duty_u16(speed)
                M2B.duty_u16(0)
                M2A.duty_u16(speed)
              else:
                M1A.duty_u16(0)
                M1B.duty_u16(speed)
                M2A.duty_u16(0)
                M2B.duty_u16(speed)

            else:
              if (walking > midpoint):
                M1A.duty_u16(0)
                M1B.duty_u16(speed)
                M2A.duty_u16(0)
                M2B.duty_u16(speed)
              else:
                M1B.duty_u16(0)
                M1A.duty_u16(speed)
                M2B.duty_u16(0)
                M2A.duty_u16(speed)

        #if ((printloopctr%20) == 0):
          #print("speed:{}; bt:{}; dir:{}; w:{}; t:{}; b:{};".format(speed, beingTurned, direction, walking, turning, button))

        #printloopctr += 1

  except OSError as err:
    print("Error:", err)
    time.sleep(0.5)
    e.active(False)
    wifi_reset()
    enow_reset()

  except KeyboardInterrupt:
    print("Stopping receiver...")
    e.active(False)
    sta.active(False)
    break
