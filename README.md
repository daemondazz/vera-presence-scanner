# Vera Presence Sensor Bluetooth Scanner

This program is a Python script that will perform both Bluetooth and iBeacon
searches for devices that have been configured using the Presence Sensor
plugin.

## Installation

This module depends on two external libraries, and also has a system startup
file for systemd based systems. The startup script assumes both libraries are
installed under /srv, although they just need to be somewhere in PYTHONPATH:

   $ cd /srv
   $ sudo git clone https://github.com/switchdoclabs/iBeacon-Scanner- ibecaon-scanner
   $ sudo git clone https://github.com/daemondazz/pyvera pyvera
   $ sudo git clone	https://github.com/daemondazz/vera-presence-scanner scanner
   $ sudo cp scanner/bluetooth-scanner.service /etc/systemd/system

If you want the scanner to automatically start at boot time:

   $ sudo systemctl enable bluetooth-scanner.service

## Troubleshooting

PyVera has been written to crash out if it encounters anything that it doesn't
understand. The primary instance of this is having scenes configured on your
Vera that have devices with serviceIDs that it doesn't know about.

There is a tuple in my fork of PyVera at about line 582 that defines the
serviceIDs that we know we can ignore. If you have any devices installed that
need to be added to that, please send me a patch so I can include them.
