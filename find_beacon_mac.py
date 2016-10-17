#!/usr/bin/env python

import sys
import bluetooth
import bluetooth._bluetooth as bluez
import blescan


def main():
    try:
        sock = bluez.hci_open_dev()
        blescan.hci_le_set_scan_parameters(sock)
        blescan.hci_enable_le_scan(sock)
    except:
        print("Error accessing bluetooth device for beacon scan")
        return 1
    sock.settimeout(5)
    returnedList = blescan.parse_events(sock, 20)
    sock.close()

    for address in returnedList:
        print(address)

if __name__ == '__main__':
    ret_val = main()
    sys.exit(ret_val)
