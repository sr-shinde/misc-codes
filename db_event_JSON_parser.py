#!/usr/bin/python

#use requirements.txt to install these dependancies
#Environment details are mentioned in file, environment.md

#SQLite version 0.0.1
import sqlite3

#msgpack version 1.0.0
import msgpack

#Functions to display or suppress debug messages
VERBOSE=False
def dprint(debugMsg):
    if VERBOSE:
        print(debugMsg)


#add DB filename in the bracket. Assumes the file to be present in the working directory
conn = sqlite3.connect('/var/data/events.db')
dprint("Opened database successfully\n")

for event_type in range(1,42):
    print("\n\n****************************************************************************")
    print("Current event type: ", event_type)
    print("****************************************************************************")

    #[WIP remove unecessary columns for the sake of execution speed]
    cursor = conn.execute(f"SELECT boot_seq, event_id, event_type, uptime_sec, uptime_nsec, body FROM events WHERE event_type = {event_type} LIMIT 3")

    for row in cursor:
        # print("----------------------------------------------------------------------------")
        # print("ID = ", row[1])
        # print("Type = ", row[2])

        # writes data to file, this is later read by the Unpacker 
        # To-DO: inefficient method, change it. Currently implemented because the Unpacker needs
        # object with read() method support.
        with open("data.msgpack", "wb") as dataFile:
            dataFile.write(row[5])

        #unpacks the multiple msgpack objects and returns a list of them
        with open("data.msgpack", "rb") as file:
            unp = msgpack.Unpacker(file)

            for data in unp:
                print(data)
                print("----------------------------------------------------------------------------")
        
#            print("\n")

dprint("\n\nOperation done successfully")

#Do not forget this!
conn.close()
