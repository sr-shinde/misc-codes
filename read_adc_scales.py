#!/usr/bin/python
import os

sample_size = 60
gap = 0
val_store = [0] * sample_size

avg_gap = 0

for i in range(sample_size):
    tv_vals = os.popen("powerpcb_comm TV_CURR_VALS").read()

    min_val = tv_vals[9:11] + tv_vals[6:8]
    min_val = int(min_val, 16)

    max_val =  tv_vals[3:5] + tv_vals[0:2]
    max_val = int(max_val, 16)

#    print(f"min val: {min_val}")
#    print(f"max val: {max_val}")

    gap = (max_val - min_val)
    val_store[i] = gap
    
    print(gap)

for i in range(sample_size):
    avg_gap = avg_gap + val_store[i]

avg_gap = avg_gap/sample_size
print(f"Average: {avg_gap}")
