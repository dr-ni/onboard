#!/usr/bin/python
import virtkey
v = virtkey.virtkey()

for r in v.layout_get_keys("Keypad"):
	for k in r:
			print k['name']
	

