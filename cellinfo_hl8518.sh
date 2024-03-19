#!/bin/bash

set -euo pipefail

BINDIR=$(dirname "$0")
modemTimeout=5
MODEM_TYPE_FILE="/run/modem_type"

NOW="$(date +%s)"
if \
	[ -e /run/installation_mode ] \
	|| ( [ -e /run/last_installer_disconnect ] \
		&& [ "$(date --reference /run/last_installer_disconnect +%s)" -gt $((${NOW} - 60 * 60)) ] ) \
	|| [ -e /run/applying-ota ]; then
	systemctl restart --no-block cellinfo-postpone.timer
	exit
else
	systemctl stop cellinfo-postpone.timer
fi

exec {MODEMLOCKFILE}<>"/tmp/GSM1.lock"
sh -c 'sleep 2; systemctl try-restart hl8518' &
flock $MODEMLOCKFILE

echo "${CELLINFO_SCAN_TIME:=240}" >/dev/null
echo "${CELLINFO_GRAB_NETWORK_WAIT_TIME:=10}" >/dev/null
echo "${CELLINFO_SLEEP_TIME:=480}" >/dev/null

powerCycle() {
	# Use stop & start instead of restart
	systemctl stop hl8518-device
	systemctl start hl8518-device
}

gatherCellInfo() {
	echo -ne 'AT\nAT\nAT+COPN\n' | timeout 10 stdbuf -oL -eL atinout - "$MODEM" -  | grep '^+COPN: ' | cut -c8- > /tmp/COPN
	echo -ne 'AT\nAT\nAT+COPS=2\nAT\n' | timeout 10 stdbuf -oL -eL atinout - "$MODEM" -
	sleep "${CELLINFO_GRAB_NETWORK_WAIT_TIME}"  # Just let the modem calm down
	if [ -e "$MODEM_TYPE_FILE" ] && [ x"$(cat $MODEM_TYPE_FILE)" == x"ec20" ] 
	then
		echo -ne 'AT\nAT+QCOPS=7,1\n' | timeout "$(($CELLINFO_SCAN_TIME+10))" stdbuf -oL -eL atinout - "$MODEM" - | tee cellinfo.log1
	else
		echo -ne 'AT\nAT+KNETSCAN=1,,7,0,'"$CELLINFO_SCAN_TIME"'\n'  | timeout "$(($CELLINFO_SCAN_TIME+10))" stdbuf -oL -eL atinout - "$MODEM" - | tee cellinfo.log1
	fi

	# Re-enable network registration on the Modem once cell-tower information is captured
	echo -ne "AT\nAT\nAT\n" | timeout $modemTimeout atinout - "$MODEM" - >/dev/null || true
	echo -ne 'AT\nAT\nAT+COPS=0\nAT\n' | timeout 10 stdbuf -oL -eL atinout - "$MODEM" - || true
	echo -ne "AT\nAT\nAT\n" | timeout $modemTimeout atinout - "$MODEM" - >/dev/null || true
}

#     COMMAND   |          MODEM       |     FILTER GSM RESULTS    |        EXTRACT MNC, MCC, LAC, CID, SS        |    REMOVE DUPLICATES
timeout "${CELLINFO_GRAB_NETWORK_WAIT_TIME}" cat "$MODEM" || true # Just let the modem calm down

if ! gatherCellInfo; then powerCycle; gatherCellInfo; fi

# We are only looking for info related to GSM band. So, as per the SIERRA
# doc, first response consists of this info.
if [ -e "$MODEM_TYPE_FILE" ] && [ x"$(cat $MODEM_TYPE_FILE)" == x"ec20" ] 
then
	cat cellinfo.log1 | grep '^+QCOPS:' | awk -F': ' '{print $2}' | tee cellinfo.log2 
else
	cat cellinfo.log1 | grep '^+KNETSCAN:' | awk '{print $2}' | tee cellinfo.log2 
fi

cat cellinfo.log2 | python2 "${0/%.sh/.py}"

exit
