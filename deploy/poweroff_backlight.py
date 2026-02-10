#!/usr/bin/env python3
"""
Pocket-R shutdown hook:
Turn off the LCD backlight at the very end of shutdown/reboot/halt,
so the user has a reliable "SAFE TO FLIP SWITCH" indicator.
"""
import time

try:
    import RPi.GPIO as GPIO
except Exception:
    GPIO = None

BACKLIGHT_PIN = 24  # BCM pin for Waveshare 1.3" LCD HAT backlight

def main():
    # Tiny delay to run late-ish in shutdown ordering
    time.sleep(0.2)

    if GPIO is None:
        return

    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(BACKLIGHT_PIN, GPIO.OUT)

    # Backlight OFF
    GPIO.output(BACKLIGHT_PIN, GPIO.LOW)
    GPIO.cleanup(BACKLIGHT_PIN)

if __name__ == "__main__":
    main()
