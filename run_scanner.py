#!/usr/bin/env python

VERA_IP = '172.17.66.15'

import bluetooth
import bluetooth._bluetooth as bluez
import datetime
import logging
import logging.handlers
import sys
import time

import blescan
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

    dev_id = 0
    try:
        sock = bluez.hci_open_dev(dev_id)
    except:
        print "error accessing bluetooth device..."
        sys.exit(1)

    blescan.hci_le_set_scan_parameters(sock)
    blescan.hci_enable_le_scan(sock)

    next_active = 0
    while True:

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
            next_active = time.mktime(datetime.datetime.now().replace(second=0, microsecond=0).timetuple()) + 60
            logger.debug('Done, sleeping until %d' % next_active)

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
