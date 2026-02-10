#!/usr/bin/env python3
# battery_test.py - quick INA219 read loop

import time
from battery_ina219 import INA219, voltage_to_percent_liion

def main():
    sensor = INA219(bus_num=1, address=0x43, shunt_ohms=0.1, max_expected_amps=2.0)
    print("INA219 OK at address:", hex(sensor.address))
    try:
        while True:
            d = sensor.read_all()
            pct = voltage_to_percent_liion(d["vload"])
            print(
                f"Vbus={d['vbus']:.3f}V  Vshunt={d['vshunt']*1000:.3f}mV  "
                f"Vload={d['vload']:.3f}V  I={d['current_a']*1000:.1f}mA  "
                f"P={d['power_w']:.3f}W  BAT~{pct}%"
            )
            time.sleep(1)
    finally:
        sensor.close()

if __name__ == "__main__":
    main()
