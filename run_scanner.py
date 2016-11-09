#!/usr/bin/env python

SCANNER_NAME = 'Basement'
VERA_IP = '192.168.7.205'

FOUND_HOLD_TIME = 120  # Timeout to go to not found (s)
BEACON_LISTEN_PERIOD = 10  # How often we listen for beacons (s)
BEACON_LISTEN_TIMEOUT = 2  # Timeout on receiving beacon reports (s)
BEACON_LISTEN_QTY = 10 # How many beacon reports per listen
POLLPERIOD_LIVE = 60  # Pollperiod for live bluetooth devices (s)
POLLPERIOD_DEAD = 10  # Pollperiod for dead bluetooth devices (s)
MIN_REPORT_IDLE_TIME = 30  # Min time between Vera updates for each device (s)
VERA_SYNC_PERIOD = 600  # How often we sync device list to Vera (s)
VERA_SYNC_RETRY = 10 # How often we retry sync if it fails or no devices (s)

VERA_MSG_BASE = 'http://%s:3480' % (VERA_IP)
SVC_ID = 'urn:afoyi-com:serviceId:PresenceSensor1'
DEV_TYPE = 'urn:schemas-afoyi-com:device:PresenceSensor:1'

import bluetooth
import datetime
import time
import logging
import logging.handlers
import sys
import math
import struct
import array
import fcntl
import urllib
import urllib2
import json
import bluetooth._bluetooth as bluez
import blescan


def msg_vera(msg):
    """Send a command to Vera.

    Arguments:
    msg --- the partial url of the message starting after <address:port>/

    Returns:
    reply from Vera json formatted if json, otherwise as string
    """
    url = '%s/%s' % (VERA_MSG_BASE, msg)
    for i in range(1,3):
        try:
            conn = urllib2.urlopen(url)
            data = conn.read()
            success = True
        except:
            success = False
        if success:
            conn.close
            break
    if not success:
        logger.debug('Failed to communicate to Vera')
        data = None
    else:
        try:
            data = json.loads(data)
        except:
            pass
    return data


def find_device(id, address, type, device_list):
    """Look for a device in Vera's list matching specified criteria.

    Arguments:
    id --- the Vera deviceid as a string
    address --- the bluetooth address
    type --- the bluetooth type ('ibeacon' or 'bluetooth')
    device_list --- the list of devices from Vera's json reply

    Returns:
    true if found
    """
    match = 0
    for dev in device_list:
        if dev['id'] != id:
            continue
        for state in dev['states']:
            if state['service'] == SVC_ID:
                if state['variable'] == 'Address':
                    if state['value'].upper() == address:
                        match += 1
                    else:
                        break
            if state['service'] == SVC_ID:
                if state['variable'] == 'DeviceType':
                    if state['value'] == type:
                        match += 1
                    else:
                        break
            if match == 2:
                break
        break
    return match == 2


def configure_known_devices(known_beacons, known_phones):
    """Get all Presence Sensors from Vera and put in local structures.

    Arguments:
    known_beacons --- a dictionary of currently known beacons
    known_phones --- a dictionary of currently known phones

    Returns:
    known_beacons, known_phones --- above dicts synced to Vera

    Notes:
    1) If a sensor is deleted from Vera, it will be deleted from the dict
    2) If a sensor was in the dict and still is, it's data is not
       reinitialized
    """
    vera_objects = msg_vera('data_request?id=user_data')
    if vera_objects is None:
        return known_beacons, known_phones
    device_list = filter(lambda item: item['device_type'] == DEV_TYPE,
                         vera_objects['devices'])
    # LUA is loosy goosy with str vs int, so make all id's string
    for device in device_list:
        device['id'] = str(device['id'])
    logger.debug('Checking Vera device list')

    # Check if previously known devices have been removed from Vera
    for address, beacon in known_beacons.items():
        if  not find_device(beacon['id'], address, 'ibeacon', device_list):
            del known_beacons[address]
            logger.debug('Deleting ibeacon %s from device list' % address)
    for address, phone in known_phones.items():
        if  not find_device(phone['id'], address, 'bluetooth', device_list):
            del known_phones[address]
            logger.debug('Deleting bluetooth %s from device list' % address)

    # Add new devices
    for device in device_list:
        address = None
        device_type = None
        for state in device['states']:
            if state['service'] == SVC_ID and state['variable'] == 'Address':
                address = state['value'].upper()
                if device_type is not None:
                    break
                continue
            if (state['service'] == SVC_ID
                    and state['variable'] == 'DeviceType'):
                device_type = state['value']
                if address is not None:
                    break
        if address is None or device_type is None:
            logger.debug('Device id = %s is incomplete. Skipping.'
                         % device['id'])
            continue
        if device_type == 'bluetooth':
            if address in known_phones:
                logger.debug('Bluetooth %s already in device list'
                             % address)
                continue
            known_phones[address] = {
                'id': device['id'],
                'last_state': False,
                'last_seen': 0,
                'next_poll': 0
                }
            logger.debug('Adding %s %s to device list id = %s'
                         % (device_type, address, device['id']))
        elif device_type == 'ibeacon':
            if address in known_beacons:
                logger.debug('iBeacon %s already in device list'
                             % address)
                continue
            known_beacons[address] = {
                'id': device['id'],
                'last_state': False,
                'last_seen': 0,
                'last_report': 0
                }
            logger.debug('Adding %s %s to device list id = %s'
                         % (device_type, address, device['id']))
        else:
            logger.debug('Device id = %s has invalid type (%s). Skipping.'
                         % (address, device['id'], device_type))
    return known_beacons, known_phones


def get_RSSI(addr):
    # Open an hci socket
    hci_sock = bluez.hci_open_dev()
    hci_fd = hci_sock.fileno ()

    # Try to open a connection to remote BT device
    try:
        bt_sock = bluez.SDPSession ()
        bt_sock.connect(addr)
    except:
        bt_sock.close()
        hci_sock.close()
        return None
    # Get handle to ACL connection to remote BT device
    reqstr = struct.pack ("6sB17s", bluez.str2ba (addr),
            bluez.ACL_LINK, "\0" * 17)
    request = array.array ("c", reqstr)
    fcntl.ioctl (hci_fd, bluez.HCIGETCONNINFO, request, 1)
    handle = struct.unpack ("8xH14x", request.tostring ())[0]

    # Get RSSI
    cmd_pkt=struct.pack('H', handle)
    RSSI = bluez.hci_send_req(hci_sock, bluez.OGF_STATUS_PARAM,
                           bluez.OCF_READ_RSSI,
                           bluez.EVT_CMD_COMPLETE, 4, cmd_pkt)
    RSSI = struct.unpack('b', RSSI[3])[0]

    bt_sock.close()
    hci_sock.close()
    return RSSI


def main():
    """Loop forever getting Vera devices, scanning beacons and phones."""
    known_beacons = {}
    known_phones = {}
    next_Vera_sync = time.time()
    next_beacon_scan = time.time()
    while True:

        # Get Vera devices if it is time
        if time.time() >= next_Vera_sync:
            while True:
                known_beacons, known_phones = (
                    configure_known_devices(known_beacons, known_phones))
                if known_beacons or known_phones:
                    break
                logger.debug('No devices to search for, sleeping for %d secs'
                             % VERA_SYNC_RETRY)
                time.sleep(VERA_SYNC_RETRY)
            next_Vera_sync = time.time() + VERA_SYNC_PERIOD

        # Scan for iBeacons if it is time
        if known_beacons and (time.time() >= next_beacon_scan):
            try:
                sock = bluez.hci_open_dev()
                blescan.hci_le_set_scan_parameters(sock)
                blescan.hci_enable_le_scan(sock)
            except:
                logger.debug(
                    "Error accessing bluetooth device for beacon scan")
                return 1
            sock.settimeout(BEACON_LISTEN_TIMEOUT)
            try:
                returnedList = blescan.parse_events(sock, BEACON_LISTEN_QTY)
            except:
                returnedList = []
            sock.close()

            # Check for beacons reporting
            found_beacons = {}
            for advert in returnedList:
                advert = advert.split(',')
                MAC = advert[0].upper()
                UUID = advert[1] + ',' + advert[2] + ',' + advert[3]
                UUID = UUID.upper()
                if MAC in found_beacons or UUID in found_beacons:
                    continue
                if MAC in known_beacons:
                    address = MAC
                elif UUID in known_beacons:
                    address = UUID
                else:
                    continue
                found_beacons[address] = True
                if not known_beacons[address]['last_state']:
                    known_beacons[address]['last_state'] = True
                    logger.debug('iBeacon %s now present' % address)
                if (known_beacons[address]['last_report']
                        + MIN_REPORT_IDLE_TIME) < time.time():
                    value = (SCANNER_NAME + ',' + str(FOUND_HOLD_TIME)
                             + ',' + advert[5])
                    msg_vera('data_request?id=action'
                             + '&DeviceNum=' + known_beacons[address]['id']
                             + '&serviceId=' + SVC_ID
                             + '&action=SetPresent&newPresentValue=' + value)
                    known_beacons[address]['last_report'] = time.time()
                known_beacons[address]['last_seen'] = time.time()
            # Check for beacons that have disappeared
            for address, beacon in known_beacons.items():
                if address in found_beacons:
                    continue
                if (beacon['last_state']
                        and beacon['last_seen'] + FOUND_HOLD_TIME
                        < time.time()):
                    known_beacons[address]['last_state'] = False
                    logger.debug('iBeacon %s is now not present'
                                 % address)
            next_beacon_scan = time.time() + BEACON_LISTEN_PERIOD

        # Scan for phones if it is time
        for address, phone in known_phones.items():
            if phone['next_poll'] > time.time():
                continue
            RSSI = get_RSSI(address)
            found = RSSI != None
            if found:
                if not phone['last_state']:
                    known_phones[address]['last_state'] = True
                    logger.debug('Bluetooth %s now present' % address)
                value = (SCANNER_NAME + ',' + str(FOUND_HOLD_TIME)
                         + ',' + str(RSSI))
                msg_vera('data_request?id=action'
                         + '&DeviceNum=' + known_phones[address]['id']
                         + '&serviceId=' + SVC_ID
                         + '&action=SetPresent&newPresentValue='
                         + value)
                known_phones[address]['last_seen'] = time.time()
                known_phones[address]['next_poll'] = (time.time()
                                                      + POLLPERIOD_LIVE)
            else:
                if (phone['last_state']
                        and phone['last_seen'] + FOUND_HOLD_TIME
                        < time.time()):
                    known_phones[address]['last_state'] = False
                    logger.debug('Bluetooth %s is now not present'
                                 % address)
                known_phones[address]['next_poll'] = (time.time()
                                                      + POLLPERIOD_DEAD)
        # Sleep 'til next event ready
        next_event = next_Vera_sync
        if (next_beacon_scan < next_event) and known_beacons:
            next_event = next_beacon_scan
        for _, phone in known_phones.items():
            if phone['next_poll'] < next_event:
                next_event = phone['next_poll']
        sleep_time = next_event - time.time()
        if sleep_time > 0:
            time.sleep(math.ceil(sleep_time))

# create the logger for this module
logger = logging.getLogger('Bluetooth Scanner')
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.handlers.SysLogHandler(address='/dev/log'))

if __name__ == '__main__':
    ret_val = main()
    sys.exit(ret_val)
