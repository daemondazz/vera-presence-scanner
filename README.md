# Vera Presence Sensor Bluetooth Scanner

This program is a Python script that will perform both Bluetooth and iBeacon
searches for devices that have been configured using the Presence Sensor
plugin.

## Installation

Install Jessie on the RPi.  Each RPi on the network must have a unique hostname
so if there is more than one RPi on the network, you must change the defaultset
hostname to something unique.  To do this, use the RPI GUI configuration utility.
Google how to startup with RPi if you are unfamiliar with how to do this.

Next install the bluetooth library from a shell as follows:

    $ sudo apt-get install python-bluez

Now install the scanner s/w and set priviliges and executable statuses:

    $ cd /srv
    $ sudo git clone https://github.com/daemondazz/vera-presence-scanner scanner
    $ cd scanner
    $ sudo chown root:root *
    $ sudo chmod +x *.py

Finally, set it to autostart as a service

    $ sudo cp scanner/bluetooth-scanner.service /etc/systemd/system
    $ sudo systemctl enable bluetooth-scanner

## Upgrading

To upgrade to the lastest version:

    $ cd /srv/scanner
    $ sudo git pull
    $ sudo chown root:root *
    $ sudo chmod +x *.py
    $ sudo cp scanner/bluetooth-scanner.service /etc/systemd/system
    $ sudo systemctl enable bluetooth-scanner

## Configuring Scanner

After installing or upgrading you must configure the scanner.

    $ sudo nano /srv/scanner/run_scanner.py

Now edit the scanner name and the Vera IP address.  In addition you can
edit the timers to optimize the scanning.

When finished, press ^x|y|<Enter> to save your changes then

    $ sudo systemctl restart bluetooth-scanner

## Usage Tips

The scanner gets a list of Presence devices from Vera and updates that list
at a configurable period.  These devices can be beacons or bluetooth devices
(phones, tablets etc.).

Beacon devices transmit continually.  Periodically (configurable period),
the scanner listens for beacon transmissions.  It listens until it gets a maximum
number of reports or until it times out waiting for a report.  All reports
received are each processed as mentioned below.

Bluetooth devices must be polled for a reply.  One device at a time is polled.
This is far less efficient than the Beacon polling and can affect performance
as each device out of range will timeout, slowing down all processing (including
beacon scanning).  Also, the polling of a bluetooth device can cause faster
discharge of the device as it must reply to the poll.  To mitigate this, there
are two pollperiods for bluetooth devices.  Live devices are polled at one rate
(typically slow) and dead ones are polled at another rate (typically faster).
If a reply for a given device is received, it is processed as mentioned below.

When a live device is detected AND it has been at least the minimum report time
since the last report, a report is sent to Vera identifying the scanner's hold
time (time until a present device becomes absent), the scanner name and the RSSI.

## Known Problems and Troubleshooting

The only known problem is that the scanner does not start up reliably on
system reboot.  After a reboot of the RPi, you must type:

    $ sudo systemctl reboot bluetooth-scanner
