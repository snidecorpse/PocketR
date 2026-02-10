# -*- coding: utf-8 -*-
"""
Waveshare 1.3inch LCD HAT (ST7789, 240x240) - Raspberry Pi helper.

This is a small, self-contained version of the Waveshare demo "config.py".
It uses BCM pin numbering and hardware SPI (SPI0 CE0).

Pin map (BCM) from Waveshare product page / wiki:
- KEY1 21, KEY2 20, KEY3 16
- Joystick: UP 6, DOWN 19, LEFT 5, RIGHT 26, PRESS 13
- LCD: DC 25, RST 27, BL 24, SPI0 CE0/MOSI/SCLK (BCM 8/10/11)

If your demo already works, this file should work as-is.
If your buttons read inverted, change the PUD setting below or the "ACTIVE_HIGH"
toggle in app.py.
"""
import time

import spidev

try:
    import RPi.GPIO as GPIO
except Exception as e:
    # On some newer Raspberry Pi OS releases you may need a compatibility layer.
    # Try installing: sudo apt install python3-rpi.gpio  OR  python3-rpi-lgpio
    raise

import numpy as np


class RaspberryPi:
    # LCD pins
    GPIO_RST_PIN = 27
    GPIO_DC_PIN = 25
    GPIO_BL_PIN = 24

    # Buttons/joystick pins
    GPIO_KEY_UP_PIN = 6
    GPIO_KEY_DOWN_PIN = 19
    GPIO_KEY_LEFT_PIN = 5
    GPIO_KEY_RIGHT_PIN = 26
    GPIO_KEY_PRESS_PIN = 13

    GPIO_KEY1_PIN = 21
    GPIO_KEY2_PIN = 20
    GPIO_KEY3_PIN = 16

    def __init__(self):
        self.np = np
        self._spi = None
        self._pwm = None

    def digital_write(self, pin: int, value: bool):
        GPIO.output(pin, GPIO.HIGH if value else GPIO.LOW)

    def digital_read(self, pin: int) -> int:
        return GPIO.input(pin)

    def delay_ms(self, delaytime):
        time.sleep(delaytime / 1000.0)

    def spi_writebyte(self, data):
        # data: list[int]
        self._spi.writebytes(data)

    def bl_DutyCycle(self, duty: int):
        duty = max(0, min(100, int(duty)))
        if self._pwm is not None:
            self._pwm.ChangeDutyCycle(duty)

    def module_init(self, spi_speed_hz: int = 40_000_000):
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        # Outputs
        GPIO.setup(self.GPIO_RST_PIN, GPIO.OUT)
        GPIO.setup(self.GPIO_DC_PIN, GPIO.OUT)
        GPIO.setup(self.GPIO_BL_PIN, GPIO.OUT)

        # Inputs (pull-ups). If your keys are reversed, try GPIO.PUD_DOWN instead.
        for pin in [
            self.GPIO_KEY_UP_PIN, self.GPIO_KEY_DOWN_PIN, self.GPIO_KEY_LEFT_PIN,
            self.GPIO_KEY_RIGHT_PIN, self.GPIO_KEY_PRESS_PIN,
            self.GPIO_KEY1_PIN, self.GPIO_KEY2_PIN, self.GPIO_KEY3_PIN
        ]:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # Backlight PWM
        self._pwm = GPIO.PWM(self.GPIO_BL_PIN, 1000)
        self._pwm.start(100)

        # SPI (SPI0 CE0)
        self._spi = spidev.SpiDev(0, 0)
        self._spi.max_speed_hz = int(spi_speed_hz)
        self._spi.mode = 0

        return 0

    def module_exit(self):
        try:
            if self._pwm is not None:
                self._pwm.stop()
        except Exception:
            pass
        try:
            if self._spi is not None:
                self._spi.close()
        except Exception:
            pass
        try:
            GPIO.cleanup()
        except Exception:
            pass
