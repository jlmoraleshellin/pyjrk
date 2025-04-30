from pyjrk import PyJrk
import time

jrk = PyJrk()

serial_nums = jrk.list_connected_device_serial_numbers()
jrk.connect_to_serial_number(serial_nums[0])

# Auto applied
jrk.ram_settings.load_config('config/config.yml')

## RUN for 10 seconds at 2080 mV
jrk.set_target(2080)

for i in range(10):    
    time.sleep(1)

jrk.stop_motor()
