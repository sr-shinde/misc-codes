#!/usr/bin/env python2
from __future__ import print_function
import csv
import msgpack
import os
import re
import sys
import socket
import subprocess
import copy

EVENT_VERSION = 1
EVENT_TYPE_CELL = 1
regex = ('[a-zA-Z]$')
alpha_band=""

# get the socket file
socket_addr = os.environ['PUSH_ADDR']
if socket_addr == '':
    print("Missing env variable PUSH_ADDR")
    exit(-1)

# Compatible with eventp version v0
cell_info_dict = {
    "MCC":0,
    "MNC":0,
    "LAC":0,
    "CID":0,
    "Sig_Str":0,
    "Band":"GSM",
    "GPRS":False
}

PLMNs = None

if os.path.exists('/tmp/COPN'):
    with open('/tmp/COPN') as copnfile:
        copnreader = csv.reader(copnfile)
        PLMNs = tuple(copn[0] for copn in copnreader)

# array that should be pushed to nanomsg
cell_infos = []

# read data from stdin
cell_info_reader = csv.reader(sys.stdin)
# form the event from all the info collected
if os.path.exists("/run/modem_type") and subprocess.check_output(['cat', '/run/modem_type']) == "ec20":
    for cell_info in cell_info_reader:
        temp_cell_info = {}
        if(cell_info[0]=="servingcell"):
            if(cell_info[2]=="GSM"):
                temp_cell_info['MCC'] = int(cell_info[3])
                temp_cell_info['MNC'] = int(cell_info[4])
                if cell_info[5] == "-":
                    print("Found invalid record", cell_info)
                    continue
                temp_cell_info['LAC'] = int(cell_info[5], 16)
                temp_cell_info['CID'] = int(cell_info[6], 16)
                temp_cell_info['Sig_Str'] = - int(cell_info[10], 10)
                
                band_var = cell_info[2]
                if (band_var=="LTE" or band_var=="GSM" or band_var=="WCDMA"):
                    temp_cell_info['Band']=band_var
                else:
                    continue

                temp_cell_info['GPRS'] = False
                cell_infos.append(temp_cell_info)
                
            elif(cell_info[2]=="LTE"):
                temp_cell_info['MCC'] = int(cell_info[4])
                temp_cell_info['MNC'] = int(cell_info[5])
                if cell_info[5] == "-":
                    print("Found invalid record", cell_info)
                    continue
                temp_cell_info['LAC'] = int(cell_info[12], 16)
                temp_cell_info['CID'] = int(cell_info[7], 16)
                temp_cell_info['Sig_Str'] = - int(cell_info[13], 10)

                band_var = cell_info[2]
                if (band_var=="LTE" or band_var=="GSM" or band_var=="WCDMA"):
                    temp_cell_info['Band']=band_var
                else:
                    continue

                temp_cell_info['GPRS'] = False
                cell_infos.append(temp_cell_info)
        
        elif(cell_info[0]=="neighbourcell"):
            if(cell_info[1]=="GSM"):
                temp_cell_info['MCC'] = int(cell_info[2])
                temp_cell_info['MNC'] = int(cell_info[3])
                if cell_info[4] == "-":
                    print("Found invalid record", cell_info)
                    continue
                temp_cell_info['LAC'] = int(cell_info[4], 16)
                temp_cell_info['CID'] = int(cell_info[5], 16)
                temp_cell_info['Sig_Str'] = - int(cell_info[8], 10)

                band_var = cell_info[1]
                if (band_var=="LTE" or band_var=="GSM" or band_var=="WCDMA"):
                    temp_cell_info['Band']=band_var
                else:
                    continue

                temp_cell_info['GPRS'] = False
                cell_infos.append(temp_cell_info)
else:
    gsm_results = next(cell_info_reader)
    umts_results = next(cell_info_reader)

    _scan_info = gsm_results[1:]
    for i in range(0, len(_scan_info), 6):
        temp_cell_info = {}

        # The following algo is taken from
        # `http://www.etsi.org/deliver/etsi_ts/124300_124399/124301/10.03.00_60/ts_124301v100300p.pdf`
        # Refer to section 9.9.3.12
        _plmn = _scan_info[i+2]
        temp_cell_info['MCC'] = int(_plmn[1] + _plmn[0] + _plmn[3], 10)
        mnc = int(_plmn[5] + _plmn[4] + (_plmn[2] if _plmn[2] != 'f' else ''), 10)
        if _plmn[2] != 'f' and PLMNs is not None and mnc not in PLMNs:
            mnc2 = int(_plmn[2] + _plmn[5] + _plmn[4], 10)
            if mnc2 in PLMNs:
                mnc = mnc2

        temp_cell_info['MNC'] = mnc
        temp_cell_info['LAC'] = int(_scan_info[i+3], 16)
        temp_cell_info['CID'] = int(_scan_info[i+4], 16)
        temp_cell_info['Sig_Str'] = 110 - int(_scan_info[i+5], 10)
        temp_cell_info['Band'] = 'GSM'
        temp_cell_info['GPRS'] = False
        cell_infos.append(temp_cell_info)

    _scan_info = umts_results[1:]
    for i in range(0, len(_scan_info), 7):
        temp_cell_info = {}

        # The following algo is taken from
        # `http://www.etsi.org/deliver/etsi_ts/124300_124399/124301/10.03.00_60/ts_124301v100300p.pdf`
        # Refer to section 9.9.3.12
        _plmn = _scan_info[i+1]
        temp_cell_info['MCC'] = int(_plmn[1] + _plmn[0] + _plmn[3], 10)
        mnc = int(_plmn[5] + _plmn[4] + (_plmn[2] if _plmn[2] != 'f' else ''), 10)
        if _plmn[2] != 'f' and PLMNs is not None and mnc not in PLMNs:
            mnc2 = int(_plmn[2] + _plmn[5] + _plmn[4], 10)
            if mnc2 in PLMNs:
                mnc = mnc2

        temp_cell_info['MNC'] = mnc
        temp_cell_info['LAC'] = int(_scan_info[i+2], 16)
        temp_cell_info['CID'] = int(_scan_info[i+3], 16)
        temp_cell_info['Sig_Str'] = 115 - int(_scan_info[i+5], 10)
        temp_cell_info['Band'] = 'WCDMA'
        temp_cell_info['GPRS'] = False
        cell_infos.append(temp_cell_info)

# pack the array to msgp
res_list = []
tmp_cell_infos = copy.deepcopy(cell_infos)

for data in tmp_cell_infos:
    data['Sig_Str'] = 0

for i in range(len(tmp_cell_infos)):
    if tmp_cell_infos[i] not in tmp_cell_infos[i + 1:]:
        res_list.append(cell_infos[i])

for i in res_list:
    print(i)

body = msgpack.packb(EVENT_VERSION)+ msgpack.packb(EVENT_TYPE_CELL) + msgpack.packb({'Cell_Info': res_list, 'Installing': False})

push_socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
push_socket.connect(socket_addr)
push_socket.sendall(body)
push_socket.close()
