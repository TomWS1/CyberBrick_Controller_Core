from machine import Pin, ADC
import network
import espnow
import asyncio
import time

lv = ADC(Pin(5), atten=ADC.ATTN_11DB) # Range= 289-1233-2705
lh = ADC(Pin(2), atten=ADC.ATTN_11DB) # Range= 832-1728-2512
rv = ADC(Pin(0), atten=ADC.ATTN_11DB) # Range= 2657-1585-448
rh = ADC(Pin(1), atten=ADC.ATTN_11DB) # Range= 2832-1777-624
right_switch = Pin(16, Pin.IN, Pin.PULL_UP)  # Button
yellow_led = Pin(15, Pin.OUT, 1)

def convert_range(v,low,high,range):
    out_v = 0
    # first check if range is reversed (low>high)
    if (low > high):
        inScale = low - high
        out_v = low - v
        out_v = int(out_v * (range / inScale))
    else:
        inScale = high - low
        out_v = v - low
        out_v = int(out_v * (range / inScale))

    return out_v

# Initialize Wi-Fi in station mode
sta = network.WLAN(network.STA_IF)
sta.active(True)
mac = sta.config('mac')
mac_address = ':'.join('%02x' % b for b in mac)
print("MAC address of the transmitter:", mac_address)

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

 
def mac_string_to_bytes(mac_address_str):
    """
    Converts a MAC address string into a bytes set of its hexadecimal octets.

    Args:
        mac_address_str (str): The MAC address string (e.g., "00:11:22:AA:BB:CC").

    Returns:
        bytes: A set of bytes containing the hexadecimal octets as strings (e.g., ('00', '11', '22', 'AA', 'BB', 'CC')).
    """
    # Remove common delimiters (colons or hyphens) and convert to uppercase for consistency
    cleaned_mac = mac_address_str.replace(':', '').replace('-', '').upper()

    # Ensure the cleaned string has the correct length for a MAC address (12 hex digits)
    if len(cleaned_mac) != 12:
        raise ValueError("Invalid MAC address string length.")

    # Split the string into pairs of characters and convert to bytes
    mac_bytes = bytes(int(cleaned_mac[i:i+2],16) for i in range(0, 12, 2))
    return mac_bytes

# Get Receiver's MAC address 
import json as js

filename = 'rx_mac.json'
try:
    with open(filename, 'r') as f:
        file_data = f.read()
        mac_obj = js.loads(file_data)

except OSError as e:
    print('MAC read failed', e)
    raise

mac_str1 = mac_obj.get("mac_address")
receiver_mac = mac_string_to_bytes(mac_str1)

mac_address = ':'.join('%02x' % b for b in receiver_mac)
print("MAC address of the receiver:", mac_address)

# Add peer
try:
    e.add_peer(receiver_mac)
except OSError as err:
    print("Failed to add peer:", err)
    raise

# Async function to send messages
async def send_messages(e, peer):

    led_timer = 0
    mac_addr = ':'.join('%02x' % b for b in peer)
    print("RX PEER:",mac_addr)

    while True:
        #try:

        lvs = convert_range(lv.read(),289,2705,4095)
        lhs = convert_range(lh.read(),832,2512,4095)
        rvs = convert_range(rv.read(),2657,448,4095)
        rhs = convert_range(rh.read(),2832,624,4095)

        message = f"{2047},{lhs},{lvs},{2047},{rhs},{rvs},{right_switch.value()},{0},{0},{0}"
        
        try:
            if not e.send(peer, message, False):
                e.active(False)
                wifi_reset()
                enow_reset()

            if (led_timer % 10 == 0):
              yellow_led.value(yellow_led.value()==0)  # toggle the LED
              
            led_timer += 1

            time.sleep(0.04)
    
        except OSError as err:
            print("Error:", err)
            yellow_led.value(yellow_led.value()==0)  # toggle the LED
            time.sleep(0.5)
            e.active(False)
            wifi_reset()
            enow_reset()

# Main async function
async def main(e, peer):
    await send_messages(e, peer)

# Run the async program
try:
    asyncio.run(main(e, receiver_mac))
except KeyboardInterrupt:
    print("Stopping sender...")
    e.active(False)
    sta.active(False)
    
