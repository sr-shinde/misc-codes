#!/env/bin/python

import serial
import serial.tools.list_ports
import time
import re
import io
import struct
from PIL import Image, ImageDraw, ImageFont, ImageOps
from datetime import datetime
import os
import smbus2

# For handling I2C related operations
I2C_CHANNEL = 1
DRV_ADDRESS = 0x3C
LED_REG_BASE = 0x2A
PWM_REG_BASE = 0x05
UPDATE_REG_ADDRESS = 0x25

charToChannelNum = {
'A': 7,
'B': 6,
'C': 5,
'D': 4,
'E': 3,
'F': 2,
'G': 8,
'H': 15,
'I': 14,
'J': 13,
'K': 12,
'L': 11,
'1': 19,
'2': 22,
'3': 23,
'4': 26,
'5': 21,
'ABS': 20,
'ABS1': 25,
'GSM': 18,
'TVP': 17,
'WMK': 16,
}

# For handling display with VID F003
F003_EOF = b'\n'
F003_REMOTE_DATA = re.compile(r'\$9001"([0-9]+)"0&\r\n$')
F003_LF = '\n'

def detectCOMPort(vid: str, pid: str):
    """
    Return COM port identifier for the port with provided (vid, pid), NULL if
    not detected.

    If multiple devices with same (vid, pid) connected, the first matches
    device is returned.
    """
    for port in serial.tools.list_ports.comports():
        if port.pid == pid and port.vid == vid:
            return port.device


def openSerialPort(comport: str, baud = 230400):
    '''
    Open the serial port and return the handle.

    Throws serial.SerialException
    '''
    ser = serial.Serial(port = comport,
                        baudrate = baud,
                        timeout=0,
                        write_timeout=1)
    if not ser.is_open:
        ser.open()
        ser.reset_input_buffer()
        ser.reset_output_buffer()
    return ser


class Display():

    def __init__(self, ser: serial.Serial, vid: str, pid: str):
        self.ser = ser
        self.vid = vid
        self.pid = pid


    def Close(self):
        self.ser.close()


    def Flush(self):
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()


    def Clear(self):
        pass


    def SetBrightness(self, n):
        pass


class DisplayF002(Display):
    '''
    Display handler for 0xf002
    '''

    def __init__(self, ser, vid, pid):
        super().__init__(ser, vid, pid)
        self.spacing = 4
        self.width = 4
        self.fontsize = 28
        self.Regular_ttf = './fonts/SourceCodePro/SourceCodePro-Regular.ttf'
        self.W, self.H = (256, 64) # image size
        self.background = (0) # black
        self.fill = "white"
        try:
            self.LED_display = smbus2.SMBus(I2C_CHANNEL)

            # Enabling the LED driver output
            self.LED_display.write_byte_data(DRV_ADDRESS, 0x00, 0x01)
            print("LED driver init success!")
        except Exception as e:
            print(e)
            pass

    def i2c_led_clearChar(self, c):
        print(f"Clearing char: {c}")
        try:
            # Power OFF the LED
            reg_address = LED_REG_BASE+charToChannelNum[c]
            self.LED_display.write_byte_data(DRV_ADDRESS, reg_address, 0x00)

            self.LED_display.write_byte_data(DRV_ADDRESS, UPDATE_REG_ADDRESS, 0x00)
        except Exception as e:
            print(e)
            pass

        #time.sleep(0.12)
        return


    def i2c_led_lightChar(self, c):
        print(f"Lighting char: {c}")
        try:
            # Set LED PWM to the full intensity
            reg_address = PWM_REG_BASE+charToChannelNum[c]
            self.LED_display.write_byte_data(DRV_ADDRESS, reg_address, 0xFF)

            # Power ON the LED
            reg_address = LED_REG_BASE+charToChannelNum[c]
            self.LED_display.write_byte_data(DRV_ADDRESS, reg_address, 0x01)

            self.LED_display.write_byte_data(DRV_ADDRESS, UPDATE_REG_ADDRESS, 0x00)
        except Exception as e:
            print(e)
            pass

        #time.sleep(0.12)
        return

    def i2c_led_send(self, top: str, bottom: str):
        if len(top) != 12 or len(bottom) != 6:
            raise Exception("Invalid input format")

        for i, c in enumerate(top):
            expected = chr(65+i)
            if c != expected:
                if c == "-" or c == "*":
                    continue
                else:
                    self.i2c_led_clearChar(expected)
            else:
                self.i2c_led_lightChar(expected)

        for i, c in enumerate(bottom):
            expected = chr(49+i)
            if i == 5:
                if c != "1" and c != "0" and c != "-" and c != ";" and c != "o" and c != "f":
                    raise Exception(f"NANANANANANANANA .... Got: {c}")
                if c == "0" or c == ";" or c in ["o", "f"]:
                    self.i2c_led_clearChar("ABS")
                    self.i2c_led_clearChar("ABS1")
                elif c == "1":
                    self.i2c_led_lightChar("ABS")
                    self.i2c_led_lightChar("ABS1")
                break
            if c != expected:
                if c == "-" or c == "*":
                    continue
                else:
                    self.i2c_led_clearChar(expected)
            else:
                self.i2c_led_lightChar(expected)

    def i2c_clear_display(self):
        for char in charToChannelNum:
            self.i2c_led_clearChar(char)

    def ReadRemoteCmd(self):
        '''
        Extract IR command from the remote

        The IR Code is of the format
        1 1 T A4 A3 A2 A1 A0 C5 C4 C3 C2 C1 C0 1 1
        '''
        data = self.ser.read(2)
        if not data:
            return None

        rc5pCode = (data[1]<<8) + data[0]
        return rc5pCode


    def bmp_to_arraybyte(self, imgByteArray):
        contents = imgByteArray

        # Get the size of this image
        data = [contents[2], contents[3], contents[4], contents[5]]
        fileSize = struct.unpack("I", bytearray(data))

        # Get the header offset amount
        data = [contents[10], contents[11], contents[12], contents[13]]
        offset = struct.unpack("I", bytearray(data))

        # Get the number of colors used
        data = [contents[46], contents[47], contents[48], contents[49]]
        colorsUsed = struct.unpack("I", bytearray(data))

        # Create color definition array and init the array of color values
        colorIndex = bytearray(colorsUsed[0])
        for i in range(colorsUsed[0]):
            colorIndex.append(0)

        # Assign the colors to the arraySiz
        startOfDefinitions = 54
        for i in range(colorsUsed[0]):
            colorIndex[i] = contents[startOfDefinitions + (i * 4)]

        # Make a string to hold the output of our script
        arraySize = (len(contents) - offset[0]) / 2
        # Header
        outputArray = [int(0x1f), int(0x28),int(0x66), int(0x12)]

        # Start coverting spots to values
        # Start at the offset and go to the end of the file
        for i in range(offset[0], fileSize[0], 2):
            colorCode1 = contents[i]
            # Look up this code in the table
            actualColor1 = colorIndex[colorCode1]

            colorCode2 = contents[i + 1]
            # Look up this code in the table
            actualColor2 = colorIndex[colorCode2]

            # Take two bytes, squeeze them to 4 bits
            # Then combine them into one byte
            compressedByte = (actualColor1 >> 4) | (actualColor2 & 0xF0)

            # Nibble swap
            swaped_nibbles = (compressedByte & 0x0F)<<4 | (compressedByte & 0xF0)>>4

            # Add this value to the array
            outputArray.append(swaped_nibbles)

        binary_format = bytearray(outputArray)
        return binary_format

    def graphic(self):

        path = '/opt/fluctus/display-handler/v_bmp'
        dir_list = os.listdir(path)

        print("Files and directories in '", path, "' :")

        for x in range(25):
            z = str(dir_list[x])

            image = Image.open("v_bmp/" + z).convert('L')
            flipped_image = ImageOps.flip(image)

            byteArray = io.BytesIO()
            flipped_image.save(byteArray, format="bmp")
            byteArray = byteArray.getvalue()
            data = self.bmp_to_arraybyte(byteArray)
            self.PowerOn()
            i = 0
            while True:
                start = i*1024
                end = (i+1)*1024
                info = data[start:end]
                self.ser.write(info)
                if not info:
                    break
                i = i+1
                time.sleep(0.005)
            time.sleep(0.1)

        return

    def scroll(self, top: str, bottom: str):
        # get a font
        font = ImageFont.truetype(self.Regular_ttf, self.fontsize)

        # make a blank image for the text, initialized to transparent text color
        image = Image.new('L', (self.W, self.H), self.background) # 'L' = 8-bit pixels, black and white, black background

        # get a drawing context
        draw = ImageDraw.Draw(image)

        # w, h = font.getsize(input_text)
        char_width = font.getsize("A")[0]



        for i, c in enumerate(top):
            position = 18-i
            offset = position*self.spacing + (position - 1)*char_width
            # print(f"Writing {c} at position: {position} with offset: {offset}")
            draw.text((offset, 0), c, fill=self.fill, font=font)
            # time.sleep(0.5)



        for i, c in enumerate(bottom):
            position = 18-i

            offset = position*self.spacing + (position - 1)*char_width
            # print(f"Writing {c} at position: {position} with offset: {offset}")
            draw.text((offset, 32), c, fill=self.fill, font=font)




        # Convert into grayscale - bit depth will become 24 to 8
        image.convert(mode='L', colors=16)

        # Flip image top to bottom
        flipped_image = ImageOps.flip(image)

        byteArray = io.BytesIO()
        flipped_image.save(byteArray, format="bmp")
        byteArray = byteArray.getvalue()
        data = self.bmp_to_arraybyte(byteArray)
        self.PowerOn()
        i = 0
        while True:
            start = i*1024
            end = (i+1)*1024
            info = data[start:end]
            self.ser.write(info)
            if not info:
                break
            i = i+1
            time.sleep(0.005)
        return

    def Send(self, top: str, bottom: str, mode="viewership"):
        # get a font
        font = ImageFont.truetype(self.Regular_ttf, self.fontsize)

        # make a blank image for the text, initialized to transparent text color
        image = Image.new('L', (self.W, self.H), self.background) # 'L' = 8-bit pixels, black and white, black background

        # get a drawing context
        draw = ImageDraw.Draw(image)

        # w, h = font.getsize(input_text)
        char_width = font.getsize("A")[0]
        # print(f"Character width is: {char_width}")

        if mode == "viewership":
            if len(top) != 12 or len(bottom) != 6:
                raise Exception(f"Improper data format. Got {top}, {bottom}")

            # Send data to the LED driver
            # self.i2c_led_send(top, bottom)

            for i, c in enumerate(top):
                position = i+1
                offset = position*self.spacing + (position - 1)*char_width
                # print(f"Writing {c} at position: {position} with offset: {offset}")
                draw.text((offset, 0), c, fill=self.fill, font=font)

            for i, c in enumerate(bottom):
                position = i+1
                if i == 5:
                    offset = position*self.spacing + (position - 1)*char_width*2
                    offset += 10
                    if c == "1":
                        c = "ABS"
                    elif c == ";":
                        c = "   "
                    elif c == "o":
                        c = "T:1"
                    elif c == "f":
                        c = "T:0"
                    else:
                        c = "***"
                else:
                    if c == str(i + 1):
                        offset = position*self.spacing + (position - 1)*char_width*2
                        # print(f"Writing {c} at position: {position} with offset: {offset}")
                        draw.text((offset, 32), "G", fill=self.fill, font=font)
                        offset+=self.spacing*4
                    else:
                        offset = position*self.spacing + (position - 1)*char_width*2
                # print(f"Writing {c} at position: {position} with offset: {offset}")
                draw.text((offset, 32), c, fill=self.fill, font=font)

            #self.i2c_led_send(top, bottom)


        # Display the messages with different text attributes(Size, height, width, etc.)
        elif mode == "messaging":
            for i, c in enumerate(top):
                position = i+1
                offset = position*0 + (position - 1)*char_width
                # print(f"Writing {c} at position: {position} with offset: {offset}")
                draw.text((offset, 0), c, fill=self.fill, font=font)

            for i, c in enumerate(bottom):
                position = i+1
                offset = position*0 + (position - 1)*char_width
                # print(f"Writing {c} at position: {position} with offset: {offset}")
                draw.text((offset, 32), c, fill=self.fill, font=font)

        elif mode == "screensaver":
            now = datetime.now()
            current_time = now.strftime("%I:%M %p")
            current_day =  now.strftime("%A|%d %b %y")

            # current_day = "Thursday|20 Jun 23"

            # This is done to align date string in the center
            # static offset=16, Max day length=17, char width = 13
            text_offset = 16+(((17-len(current_day))*13)//2)

            font = ImageFont.truetype(self.Regular_ttf, 30)
            char_width = font.getsize("A")[0]

            for i, c in enumerate(current_time):
                position = i+1
                offset = position*0 + (position - 1)*char_width
                # print(f"Writing {c} at position: {position} with offset: {offset}")
                draw.text((offset+55, 0), c, fill=self.fill, font=font)

            font = ImageFont.truetype(self.Regular_ttf, 22)
            char_width = font.getsize("A")[0]

            for i, c in enumerate(current_day):
                # current_day = current_day.rjust(20-len(current_day), ' ')
                position = i+1
                offset = (position)*0 + (position -1)*char_width
                # print(f"Writing {c} at position: {position} with offset: {offset}")
                draw.text((offset+text_offset, 34), c, fill=self.fill, font=font)

            shape = [(0, 0), (255, 63)]
            draw.rectangle(shape, outline = "white")

        # Convert into grayscale - bit depth will become 24 to 8
        image.convert(mode='L', colors=16)
        #image.save("/tmp/array",format="hex")

        # Flip image top to bottom
        flipped_image = ImageOps.flip(image)
        image.save("/tmp/array",format="bmp")

        byteArray = io.BytesIO()
        flipped_image.save(byteArray, format="bmp")
        byteArray = byteArray.getvalue()

        data = self.bmp_to_arraybyte(byteArray)
        self.PowerOn()

        i = 0
        while True:
            start = i*1024
            end = (i+1)*1024
            info = data[start:end]
            self.ser.write(info)
            if not info:
                break
            i = i+1
            time.sleep(0.005)

        time.sleep(0.2)
        return


    def Clear(self):
        self.Flush()
        self.ser.write(bytearray([int(0x1F), int(0x28), int(0x61), int(0x40), int(0)]))
        time.sleep(0.1)
        self.i2c_clear_display()


    def SetBrightness(self, n):
        self.Flush()
        self.ser.write(bytearray([int(0x1F), int(0x58), int(n)]))


    def PowerOn(self):
        self.Flush()
        self.ser.write(bytearray([int(0x1F), int(0x28), int(0x61), int(0x40), int(1)]))
        time.sleep(0.1)


class DisplayF003(Display):
    '''
    Display handler for 0xf003
    '''

    def __init__(self, ser, vid, pid):
        super().__init__(ser, vid, pid)
        self.display_info_top = [False]*12
        self.display_info_bottom = [False]*6
        print(f"Display {hex(self.pid)} initialized")



    def read(self):
        char = None
        data = b''

        # The protocol implemented is quite odd - hence this is the simplest
        # approach
        while char != F003_EOF:
            char = self.ser.read(1)
            if not char:
                break
            data = data + char

        return data


    def ReadRemoteCmd(self):
        '''
        Extract IR command from the remote

        The IR Code is of the format (** The display implementors modify the
        data received from remote **)
        0 0 T A4 A3 A2 A1 A0 C5 C4 C3 C2 C1 C0 1 1

        The overall format is
        $9001"<IR code upto 5 digits>"0&
        '''
        while True:
            data = self.read()

            if not data:
                return None

            irResp = F003_REMOTE_DATA.search(data.decode())
            if not irResp:
                continue
            else:
                break

        # The display firmware strips the upper two bits. We put them back in so
        # our common function does not have to change.
        rc5pCode = int(irResp.group(1)) | 0xC000
        return rc5pCode


    def clearChar(self, c):
        if len(c) == 1:
            if 0 <= ord(c)-65 <= 11:
                if self.display_info_top[ord(c)-65]:
                    self.display_info_top[ord(c)-65] = False
                else:
                    return
            else:
                if self.display_info_bottom[ord(c)-49]:
                    self.display_info_bottom[ord(c)-49] = False
                else:
                    return
        print(f"Clearing char: {c}")
        cmd = f'$9003"{c}"1&{F003_LF}'
        self.ser.write(cmd.encode())
        time.sleep(0.12)
        return


    def lightChar(self, c):
        if len(c) == 1:
            if 0 <= ord(c)-65 <= 11:
                if not self.display_info_top[ord(c)-65]:
                    self.display_info_top[ord(c)-65] = True
                else:
                    return
            else:
                if not self.display_info_bottom[ord(c)-49]:
                    self.display_info_bottom[ord(c)-49] = True
                else:
                    return
        print(f"Lighting char: {c}")
        cmd = f'$9002"{c}"1&{F003_LF}'
        self.ser.write(cmd.encode())
        time.sleep(0.12)
        return

    def Send(self, top: str, bottom: str):
        if len(top) != 12 or len(bottom) != 6:
            raise Exception("Invalid input format")

        print(f"Flusing buffers for {hex(self.vid)}, {hex(self.pid)}")
        self.Flush()

        for i, c in enumerate(top):
            expected = chr(65+i)
            if c != expected:
                if c == "-" or c == "*":
                    continue
                else:
                    self.clearChar(expected)
            else:
                self.lightChar(expected)

        for i, c in enumerate(bottom):
            expected = chr(49+i)
            if i == 5:
                if c != "1" and c != "0" and c != "-" and c != ";" and c != "o" and c != "f":
                    raise Exception(f"NANANANANANANANA .... Got: {c}")
                if c == "0" or c == ";" or c in ["o", "f"]:
                    self.clearChar("ABS")
                elif c == "1":
                    self.lightChar("ABS")
                break
            if c != expected:
                if c == "-" or c == "*":
                    continue
                else:
                    self.clearChar(expected)
            else:
                self.lightChar(expected)

        print(f"Current info: {self.display_info_top}, {self.display_info_bottom}")


    def Clear(self):
        self.Flush()
        cmd = f'$9009"ALLOFF"1&{F003_LF}'
        self.ser.write(cmd.encode())
        self.display_info_top = [False]*12
        self.display_info_bottom = [False]*6
        time.sleep(0.1)

    def SetBrightness(self, n):
        self.Flush()
        cmd = f'$9005"{n}"1&{F003_LF}'
        self.ser.write(cmd.encode())
        time.sleep(0.1)



def init() -> (Display):
    display = None
    ir_display = None
    deviceList = [[0x2047, 0xf002],
                  [0x2047, 0xf001],
                  [0x1A86, 0x7523],
                  [0x10C4, 0xEA60]]

    for vid, pid in deviceList:
        comport = detectCOMPort(vid, pid)
        if not comport:
            continue
        #ser = openSerialPort(comport)
        if pid in [0xf002, 0xf001, 0x7523]:
            ser = openSerialPort(comport)
            display = DisplayF002(ser, vid, pid)
        if pid == 0xEA60:
            ser = openSerialPort(comport, baud = 115200)
            ir_display = DisplayF003(ser, vid, pid)

    return display, ir_display
