# CyberBrick ESP-NOW receiver in CyberBrick MicroPython flavor
# Generic code to read this device's MAC and output it to a file
# 'rx_mac.json'



import network
import espnow
import asyncio

# Initialize Wi-Fi in station mode
sta = network.WLAN(network.STA_IF)
sta.active(True)
mac = sta.config('mac')
mac_address = ':'.join('%02x' % b for b in mac)
print("MAC address of the receiver:", mac_address)

mac_obj = {
  "device_name": "rx_generic", 
  "mac_address": mac_address
}

# Save Receiver's MAC address 
import ujson as js

filename = 'rx_mac.json'
try:
    with open(filename, 'w') as f:
        file_data = js.dumps(mac_obj)
        f.write(file_data)
        print("MAC saved in file:", filename)

except OSError as e:
    print('MAC write failed', e)
    raise

