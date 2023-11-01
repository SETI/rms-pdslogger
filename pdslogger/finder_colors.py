################################################################################
# finder_colors.py
#
# Mark Showalter, SETI Institute, April 2017
################################################################################

# import os
# import subprocess
#
# COLOR_VALUES = {
#     'none'   : 0,
#     'orange' : 1,
#     'red'    : 2,
#     'yellow' : 3,
#     'blue'   : 4,
#     'violet' : 5,
#     'purple' : 5,
#     'green'  : 6,
#     'gray'   : 7,
#     'grey'   : 7,
# }
#
# def set_color(filepath, color):
#     filepath = os.path.abspath(filepath)
#     color = color.lower()
#     script = ('tell application "Finder" to set label index of ' +
#               '(POSIX file "%s" as alias) to %d' % (filepath,
#                                                     COLOR_VALUES[color]))
#     cmd = ['osascript', '-e', script]
#
# #     _ = subprocess.Popen(['osascript', '-e', script], stdout=subprocess.PIPE)
#     _ = subprocess.call(['osascript', '-e', script])

import sys
import xattr
from struct import unpack, pack

if sys.version_info >= (3,0):
    BYTES32 = bytes(32)
else:
    BYTES32 = chr(0)*32

COLORS = ['none', 'gray', 'green', 'violet', 'blue', 'yellow', 'red', 'orange']
FINDER_KEY = u'com.apple.FinderInfo'

def set_color(filename, color_name):
    if sys.platform != 'darwin': return

    attrs = xattr.xattr(filename)
    finder_attrs = attrs.copy().get(FINDER_KEY, BYTES32)
    flags = list(unpack(32*'B', finder_attrs))
    flags[9] = COLORS.index(color_name) * 2
    finder_attrs = pack(32*'B', *flags)
    attrs.set(FINDER_KEY, finder_attrs)
