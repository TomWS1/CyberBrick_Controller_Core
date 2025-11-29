# CyberBrick ESP-NOW receiver in CyberBrick MicroPython flavor
# To be copied to CyberBrick Core, paired with X11 remote control receiver shield
# Control for the CyberBrick Soccerbot
# https://makerworld.com/en/models/1395987-cyberbrick-official-soccerbot?from=search#profileId-1446987
#
# The outputs of X11 shield are driven from following inputs:
# * Servo1: fork for lifting and tossing (Slider Control R1, ch 3)
# * Servo2: not used
# * Servo3: not used
# * Servo4: not used
# * Motor1: channel 2 (Left tread) 
# * Motor2: channel 5 (Right tread)
# * NeoPixel Builtin: left on at dim green
# * NeoPixel_Channel1: not driven by this code
# * NeoPixel_Channel2: Headlights and 'show off'

# In this device, only 2 NeoPixels are connected to channel2, 1 - Left Headlight, 2 - Right Headlight

"""
The incoming telegram via ESP-NOW is expected in the following order:
 1)  ch0 L1, unsigned 12-bit value   (3-way switch on Cyberbrick official standard remote)
 2)  ch1 L2, unsigned 12-bit value   (Left horizontal (LH) stick)
 3)  ch2 L3, unsigned 12-bit value   (Left vertical (LV) stick - used for speed control)
 4)  ch3 R1, unsigned 12-bit value   (Slider - used for picking up and 'tossing' the soccerball)
 5)  ch4 R2, unsigned 12-bit value   (Right horizontal (RH) stick - used for steering)
 6)  ch5 R3, unsigned 12-bit value   (Right vertical (LH) stick)
 7)  ch6 K1, 1-bit value, low-active (Button) - Used to Null Joysticks, sequence lights
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

RIGHT_STICK = 4    # Right Horizontal Stick, used for Steering
LEFT_STICK = 2    # Left Vertical Stick, used for speed (FWD & BKWD)
SLIDER = 3
BUTTON = 6
MAX_STEERING = 1800 # limit range of steering control due to inaccuracy of joysticks (can't travel all the way between +/- 2047)

# Initialize motors output to idle (a brushed motor is controlled via 2 pins on HTD8811)
M1A = PWM(Pin(4), freq=100, duty_u16=0)
M1B = PWM(Pin(5), freq=100, duty_u16=0)
M2A = PWM(Pin(6), freq=100, duty_u16=0)
M2B = PWM(Pin(7), freq=100, duty_u16=0)

S1 = PWM(Pin(3), freq=50, duty_u16=4915) # servo center 1.5ms equals to 65535/20 * 1.5 = 4915

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

# use a table to control color

color_scheme = [
  (0, 0, 0),         # initially LEDs are off (RGB=0,0,0)
  (0, 0, 127),       # then half blue
  (0, 0, 255),        # full blue
  (0, 127, 0),        # half green
  (0, 255, 0),        # full green
  (127, 0, 0),        # half red
  (255, 0, 0)         # full red
]

LED_OFF = 0
LED_BLUE = 2
LED_GREEN = 4
LED_RED = 6

color_index = -1      # start color index at invalid value so first press nulls the joystick

LEDstring2pin = Pin(20, Pin.OUT)           # define the pin used for the LED2 string
LEDstring2 = NeoPixel(LEDstring2pin, 2)    # tell the Neopixel driver that there are TWO LEDs in the string.

def setLedColor(idx):
  global LEDstring2

  for i in range(2):
    LEDstring2[i] = color_scheme[idx] # set them all to same color
  LEDstring2.write()

setLedColor(LED_OFF)

button = 0                                 # variable to accept the latest button state
last_button = 1                            # and a history of the last state to differentiate it
blinkertime_ms  = 750  # 1.5 Hz

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
midpoint_left = 2047
midpoint_right = 2047
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
      color_index = -1
      if ((utime.ticks_ms() % blinkertime_ms) > (blinkertime_ms / 2)):
        setLedColor(LED_OFF)
      else:
        setLedColor(LED_RED) # All red
      
      e.active(False)
      wifi_reset()
      enow_reset()
    
    else:  # got a good message, split it into individual data fields and process it
      rxch = msg.decode().split(",")
      if len(rxch) == 10:
        
        left_stick = int(rxch[LEFT_STICK])  
        right_stick = int(rxch[RIGHT_STICK])  
        tosser = int(rxch[SLIDER])

        button = int(rxch[BUTTON])   # the single pushbutton on the standard remote

        # midpoint calibrate
        if (button_falling(button)): # is button pressed? 
          if (color_index < 0):      # first time, set the midpoint to null the joystick
            midpoint_left = left_stick   # set new midpoints
            midpoint_right = right_stick
            color_index = 0
          else:
            rgb = color_scheme[color_index]    # subsequent pushes change the LED color
            color_index = ((color_index+1) % len(color_scheme))
            setLedColor(color_index)

        # set speeds based on above/equal/below midpoints
        speed = 0
        steering = 0
        turnMult = 1.0  # no difference in tread speeds

        if ((left_stick < (midpoint_left+deadzoneplusminus)) and (left_stick > (midpoint_left - deadzoneplusminus))):
          # motion stopped
          speed = 0
        else:
          if (left_stick > midpoint_left):
            speed = min(32*(left_stick - midpoint_left), 65535)
          else:
            speed = min(32*(midpoint_left - left_stick), 65535)

        if ((right_stick < (midpoint_right+deadzoneplusminus)) and (right_stick > (midpoint_right - deadzoneplusminus))):
          # steering centered
          steering = 0
        else:
          steering = right_stick - midpoint_right

        if (speed == 0):
          stop_motors()

        else:
          left_speed = speed
          right_speed = speed
          # For steering control, the steering controls the proportion of right/left speed on the two treads
          # steering = 0, speed is equal on both treads
          # steering > midpoint then the left speed is 100% while the right is reduced from 100% to 0% depending on amount of steering
          # Note: Steering value range is limited to 1800 due to inaccurracy of controls
          if (steering > 0):   # Right Turn (Right Tread reduced speed)
            steering = min(steering, MAX_STEERING)
            turnMult = (MAX_STEERING - steering)/MAX_STEERING
            right_speed = int(speed * turnMult)

          if (steering < 0):
            steering = min(steering, -MAX_STEERING)
            turnMult = (MAX_STEERING + steering)/MAX_STEERING
            left_speed = int(speed * turnMult)

          if (left_speed > 0):
              M1B.duty_u16(0)
              M1A.duty_u16(left_speed)
          else:
              M1A.duty_u16(0)
              M1B.duty_u16(left_speed)

          if (right_speed > 0):
              M2B.duty_u16(0)
              M2A.duty_u16(right_speed)
          else:
              M2A.duty_u16(0)
              M2B.duty_u16(right_speed)

        # Ok, is the tosser to be activated???
        # 1 to 2ms range for 0 to 4095 input value
        S1.duty_u16(int(((float(tosser)*6554)/4095 + 1638)))


        if ((printloopctr%20) == 0):
          print("left:{}; right:{}; tosser:{}; b:{};".format(speed, steering, tosser, button))

        printloopctr += 1

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
