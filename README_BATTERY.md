Pocket-R Battery Patch (INA219)

Files included:
- app.py (adds battery HUD + polling)
- battery_ina219.py (INA219 I2C reader)
- battery_test.py (prints readings once/sec)
- install.sh (adds i2c-tools + python3-smbus)

How to apply:
1) Copy these files into your existing Pocket-R project folder, overwriting app.py and install.sh.
2) Enable I2C: sudo raspi-config -> Interface Options -> I2C -> Enable -> reboot
3) Verify INA219: sudo i2cdetect -y 1  (should show address 40)
4) Optional test: ./battery_test.py

If the voltage you see is ~5.0V all the time, your INA219 may be monitoring the 5V rail, not the raw cell.
In that case we can still display voltage/current, but % won't reflect true battery unless the HAT exposes battery voltage directly.
