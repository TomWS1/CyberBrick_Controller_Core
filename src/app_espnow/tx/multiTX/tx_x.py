# CyberBrick ESP-NOW transmitter in CyberBrick MicroPython flavor
# To be used on CyberBrick Core, paired with X12 remote control transmitter shield

from machine import Pin, ADC
import network
import espnow
from neopixel import NeoPixel
import time

"""
The outgoing telegram via ESP-NOW is the following:
1) L1, unsigned 12-bit value (3-way switch on Cyberbrick official standard remote) - might be used to select which device to send to
2) L2, unsigned 12-bit value (Left horizontal (LH) stick)
3) L3, unsigned 12-bit value (Left vertical (LV) stick)
4) R1, unsigned 12-bit value (Slider)
5) R2, unsigned 12-bit value (Right horizontal (RH) stick)
6) R3, unsigned 12-bit value (Right vertical (LH) stick)
7) K1, 1-bit value, low-active (Button)
8) K2, 1-bit value, low-active (Not used)
9) K3, 1-bit value, low-active (Not used)
10) K4, 1-bit value, low-active (Not used)
"""

# Comment lists controls as used by the CyberBrick official standard remote
l1 = ADC(Pin(0), atten=ADC.ATTN_11DB) # 3-way-switch
l2 = ADC(Pin(1), atten=ADC.ATTN_11DB) # LH
l3 = ADC(Pin(2), atten=ADC.ATTN_11DB) # LV
r1 = ADC(Pin(3), atten=ADC.ATTN_11DB) # S1
r2 = ADC(Pin(4), atten=ADC.ATTN_11DB) # RH
r3 = ADC(Pin(5), atten=ADC.ATTN_11DB) # RV
k1 = Pin(6, Pin.IN)  # Button
k2 = Pin(7, Pin.IN)  # Not used
k3 = Pin(21, Pin.IN) # Not used
k4 = Pin(20, Pin.IN) # Not used

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
import ujson as js

filename = 'rx_macs.json'
try:
    with open(filename, 'r') as f:
        file_data = f.read()
        macs_obj = js.loads(file_data)

except OSError as e:
    print('MAC read failed', e)
    raise

# macs_obj is a list of devices and mac address strings, iterate through to usable list of devices and mac addresses
all_macs = []
for i, mac_obj in enumerate(macs_obj):
    if len(all_macs) >= 3:
        print("Too Many Receivers!")
        raise

    mac_str1 = mac_obj.get("mac_address")
    receiver_mac = mac_string_to_bytes(mac_str1)
    all_macs.append(receiver_mac)

    mac_address = ':'.join('%02x' % b for b in receiver_mac)
    print("MAC address of the receiver:{} {}", mac_address,i)


# for each device Add peer
for receiver_mac in all_macs:
    try:
        e.add_peer(receiver_mac)
    except OSError as err:
        print("Failed to add peer:", err)
        raise

# Drive NeoPixel on CyberBrick Core
npcore = Pin(8, Pin.OUT)
np = NeoPixel(npcore, 1)
val = 16
while True:
    try:
        message = f"{l1.read()},{l2.read()},{l3.read()},{r1.read()},{r2.read()},{r3.read()},{k1.value()},{k2.value()},{k3.value()},{k4.value()}"
        for receiver_mac in all_macs:

            try:
                e.get_peer(receiver_mac)
            except OSError as err:
                if err.errno == -12393: # ESP_ERR_ESPNOW_NOT_FOUND
                    peer_num, encrypt_num = e.peer_count()
                    if peer_num > 0:
                        peers = e.get_peers()
                        e.del_peer(peers[0][0])
                    try:
                        e.add_peer(receiver_mac)
                    except OSError as err:
                        print("Failed to add peer:", err)

            if not e.send(receiver_mac, message, True):
                val = 16   # not breathing
                e.active(False)
                wifi_reset()
                enow_reset()

        #==========================================
        # "Breathing" LED effect in violet tone
        if (val > 255):
          np[0] = ((int)((511-val)/2), 0, (511-val))
        else:
          np[0] = ((int)(val/2), 0, val)
        np.write()
        val = val + 8 # NeoPixel intensity change step size
        if val > (511-16):
          val = 16


        time.sleep(0.02) # Send every 20 milliseconds / @50 Hz
        
    except OSError as err:
        print("Error:", err)
        time.sleep(0.5)
        e.active(False)
        wifi_reset()
        enow_reset()
        
    except KeyboardInterrupt:
        print("Stopping sender...")
        e.active(False)