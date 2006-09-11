#!/usr/bin/python
import virtkey
v = virtkey.virtkey()
print v.layout_get_keys("Alpha")
print v.layout_get_section_size("Alpha")
