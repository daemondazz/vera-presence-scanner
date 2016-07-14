#!/usr/bin/env python

VERA_IP = '172.17.66.15'

import bluetooth
import datetime
import logging
import logging.handlers
import sys
import time

import vera


logger = logging.getLogger('Bluetooth Scanner')
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.handlers.SysLogHandler(address='/dev/log'))

known_beacons = {}
known_phones = {}


if __name__ == '__main__':
    svc_id = 'urn:afoyi-com:serviceId:PresenceSensor1'
    v = vera.VeraLocal(VERA_IP)
    for d in v.get_devices():
        if svc_id in d.services:
            address = d.get_variable(svc_id, 'Address')
            device_type = d.get_variable(svc_id, 'DeviceType')
            logger.debug('Searching for %s %s' % (address, device_type))
            if device_type == 'bluetooth':
                known_phones[address] = {'name': d.name, 'last_seen': None, 'last_state': None, 'vera_device': d}
            elif device_type == 'ibeacon':
                known_beacons[address] = {'name': d.name, 'last_seen': None, 'last_state': None, 'vera_device': d}

    # If we didn't find any devices, let's just sleep a bit and then die
    # This should prevent systemd from freaking out we're respawning too fast
    if not known_phones and not known_beacons:
        logger.debug('No devices to search for, bailing out')
        time.sleep(30)
        sys.exit(1)

    # Only initialise the bluez stack if we're going to be searching for ibeacons
    if known_beacons:
        logger.debug('Initialising bluetooth stack to search for ibeacons')
        import bluetooth._bluetooth as bluez
        import blescan
        dev_id = 0
        try:
            sock = bluez.hci_open_dev(dev_id)
            blescan.hci_le_set_scan_parameters(sock)
            blescan.hci_enable_le_scan(sock)
        except:
            print "error accessing bluetooth device..."
            sys.exit(1)

    # Only initialise our bluetooth search variables if we're searching for
    # bluetooth devices
    if known_phones:
        next_active = 0

    # If we made it this far, then lets keep running forever
    while True:

        # Only do the search for phones if we've been configured to
        if known_phones:
            # We only perform an active check for phones once per minute
            if time.time() >= next_active:
                logger.debug('Searching for known bluetooth devices')
                for phone in known_phones.keys():
                    p = known_phones[phone]
                    found = len(bluetooth.find_service(address=phone)) > 0

                    # If found, update straight away
                    if found:
                        known_phones[phone]['last_seen'] = time.time()
                        if p['last_state'] != found:
                            logger.debug('Found missing bluetooth %s' % phone)
                            known_phones[phone]['last_state'] = found
                            known_phones[phone]['vera_device'].set_present(found)

                    # If not found, don't notify for approx 3 minutes
                    else:
                        if p['last_seen'] is None or p['last_seen'] < time.time() - 165:
                            if p['last_state'] != found:
                                logger.debug('Lost bluetooth %s' % phone)
                                known_phones[phone]['last_state'] = found
                                known_phones[phone]['vera_device'].set_present(found)

                # Calculate time till the start of the next minute
                next_active = time.mktime(datetime.datetime.now().replace(second=0, microsecond=0).timetuple()) + 60
                logger.debug('Done, next poll is %d' % next_active)

        # Only search for ibeacons if we've been configured to
        if known_beacons:

            # But we search for ibeacons as fast as we can
            returnedList = blescan.parse_events(sock, 20)
            found_beacons = {}
            for beacon in returnedList:
                beacon = beacon.split(',')[0]
                if beacon not in known_beacons or beacon in found_beacons:
                    continue
                found_beacons[beacon] = True
                if beacon in known_beacons:
                    if not known_beacons[beacon]['last_state']:
                        logger.debug('Found missing ibeacon %s' % beacon)
                        known_beacons[beacon]['vera_device'].set_present(True)
                    known_beacons[beacon]['last_seen'] = time.time()
                    known_beacons[beacon]['last_state'] = time.time()

            # Lets check for beacons that have disappeared
            for beacon in known_beacons:
                b = known_beacons[beacon]
                if b['last_state'] is None or b['last_state']:
                    if b['last_seen'] is None or b['last_seen'] < time.time() - 180:
                        logger.debug('Lost ibeacon %s' % beacon)
                        known_beacons[beacon]['last_state'] = False
                        known_beacons[beacon]['vera_device'].set_present(False)

        # If we're not searching for beacons, then we must be searching for phones
        # lets sleep until our next search time
        else:
            logger.debug('Sleeping until next poll time')
            time.sleep(next_active - time.time())
