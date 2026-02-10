# battery_ina219.py
# Minimal INA219 reader for Pocket-R
#
# Requires: sudo apt install -y python3-smbus i2c-tools
# Enable I2C: raspi-config -> Interface Options -> I2C
#
# Your device address (from: i2cdetect -y 1) is 0x43.

import time

try:
    from smbus import SMBus
except Exception:
    SMBus = None


class INA219:
    # Registers
    REG_CONFIG = 0x00
    REG_SHUNT_VOLT = 0x01
    REG_BUS_VOLT = 0x02
    REG_POWER = 0x03
    REG_CURRENT = 0x04
    REG_CALIB = 0x05

    def __init__(self, bus_num: int = 1, address: int = 0x43,
                 shunt_ohms: float = 0.1, max_expected_amps: float = 2.0):
        """
        shunt_ohms: value of the shunt resistor on your board (common: 0.1 ohm).
        max_expected_amps: expected max current (helps calibration).
        """
        if SMBus is None:
            raise RuntimeError("python3-smbus not installed. Run: sudo apt install -y python3-smbus")

        self.bus_num = bus_num
        self.address = address
        self.shunt_ohms = shunt_ohms
        self.max_expected_amps = max_expected_amps

        self.bus = SMBus(bus_num)

        # Calibration: based on TI INA219 datasheet approach
        # Choose a current LSB such that max_current / 32767
        # Use a slightly larger LSB for headroom.
        self.current_lsb = max_expected_amps / 32767.0
        if self.current_lsb <= 0:
            self.current_lsb = 0.0001

        # Round up to a "nice" value to reduce noise (optional)
        # Keep it simple but avoid extremely tiny values.
        if self.current_lsb < 0.0001:
            self.current_lsb = 0.0001

        # Calibration register:
        # cal = 0.04096 / (current_lsb * shunt_ohms)
        cal = int(0.04096 / (self.current_lsb * self.shunt_ohms))
        if cal <= 0:
            cal = 1
        if cal > 0xFFFF:
            cal = 0xFFFF

        self.calibration_value = cal

        # Power LSB is 20 * current_lsb (per datasheet)
        self.power_lsb = 20.0 * self.current_lsb

        # Configure: 32V range, gain /8 (320mV shunt), 12-bit ADCs, continuous
        # This is a common "safe default".
        config = 0
        config |= 0x2000  # BRNG=1 (32V)
        config |= 0x1800  # PG=3 (Gain /8, +/-320mV)
        config |= 0x0180  # BADC=12-bit (532us)
        config |= 0x0018  # SADC=12-bit (532us)
        config |= 0x0007  # MODE=shunt+bus continuous

        # Write calibration then config
        self._write_u16(self.REG_CALIB, self.calibration_value)
        self._write_u16(self.REG_CONFIG, config)

    def close(self):
        try:
            self.bus.close()
        except Exception:
            pass

    def _write_u16(self, reg, value):
        # INA219 expects big-endian register values
        hi = (value >> 8) & 0xFF
        lo = value & 0xFF
        self.bus.write_i2c_block_data(self.address, reg, [hi, lo])

    def _read_u16(self, reg):
        data = self.bus.read_i2c_block_data(self.address, reg, 2)
        return (data[0] << 8) | data[1]

    @staticmethod
    def _to_signed_16(v):
        if v & 0x8000:
            return -((~v & 0xFFFF) + 1)
        return v

    def read_bus_voltage_v(self) -> float:
        raw = self._read_u16(self.REG_BUS_VOLT)
        # Bus voltage register: bits [15:3] are voltage, LSB = 4mV
        raw >>= 3
        return raw * 0.004

    def read_shunt_voltage_v(self) -> float:
        raw = self._read_u16(self.REG_SHUNT_VOLT)
        signed = self._to_signed_16(raw)
        # Shunt voltage LSB = 10uV
        return signed * 0.00001

    def read_current_a(self) -> float:
        # Must have calibration register set
        self._write_u16(self.REG_CALIB, self.calibration_value)
        raw = self._read_u16(self.REG_CURRENT)
        signed = self._to_signed_16(raw)
        return signed * self.current_lsb

    def read_power_w(self) -> float:
        self._write_u16(self.REG_CALIB, self.calibration_value)
        raw = self._read_u16(self.REG_POWER)
        return raw * self.power_lsb

    def read_all(self):
        vbus = self.read_bus_voltage_v()
        vshunt = self.read_shunt_voltage_v()
        current_a = self.read_current_a()
        power_w = self.read_power_w()
        # "Load voltage" estimate (bus + shunt drop)
        vload = vbus + vshunt
        return {
            "vbus": vbus,
            "vshunt": vshunt,
            "vload": vload,
            "current_a": current_a,
            "power_w": power_w,
            "address": self.address,
        }


def voltage_to_percent_liion(v: float) -> int:
    """
    Rough Li-ion 1-cell voltage -> percent mapping.
    If your HAT measures 5V rail instead of the cell, this will be meaningless.
    """
    # Clamp typical single-cell Li-ion range
    if v <= 3.20:
        return 0
    if v >= 4.20:
        return 100

    # Simple piecewise approximation
    # 3.20-3.50: 0-10
    # 3.50-3.70: 10-40
    # 3.70-3.90: 40-75
    # 3.90-4.10: 75-95
    # 4.10-4.20: 95-100
    if v < 3.50:
        p = (v - 3.20) / (3.50 - 3.20) * 10
    elif v < 3.70:
        p = 10 + (v - 3.50) / (3.70 - 3.50) * 30
    elif v < 3.90:
        p = 40 + (v - 3.70) / (3.90 - 3.70) * 35
    elif v < 4.10:
        p = 75 + (v - 3.90) / (4.10 - 3.90) * 20
    else:
        p = 95 + (v - 4.10) / (4.20 - 4.10) * 5

    pi = int(round(p))
    if pi < 0:
        pi = 0
    if pi > 100:
        pi = 100
    return pi
