#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import with_statement

from Onboard.KeyboardSVG import KeyboardSVG
from Onboard import utils
from virtkey import virtkey
from xml.dom import minidom
import os
import sys
import string

LAYOUT_DIR = "layouts"

def test_load_save():
    keyboard = KeyboardSVG(os.path.join(LAYOUT_DIR, "Default.onboard"))
    layout_xml = utils.create_layout_XML("Default", virtkey(), keyboard)
    assert(layout_xml != None)
    
    for name, xml in layout_xml.items():
        xml = minidom.parseString(utils.toprettyxml(xml))
        with open(os.path.join(LAYOUT_DIR, name)) as orig_xml_file:
            orig_xml = minidom.parse(orig_xml_file)
            _xml_equal(xml.documentElement, orig_xml.documentElement)
            """
            if (xml != orig_xml):
                orig_file = open(name + ".orig", "w")
                orig_file.write(orig_xml)
                orig_file.close()
                err_file = open(name + ".err", "w")
                err_file.write(xml)
                err_file.close()
            assert(xml == orig_xml)
            """

def _sort_nodes(a, b):
    return cmp(a.attributes["id"].value, b.attributes["id"].value)

def _xml_equal(a, b):
    assert a.tagName == b.tagName

    a_attributes = set(a.attributes.keys())
    b_attributes = set(b.attributes.keys())
    assert a_attributes == b_attributes, \
        "{0} differs {1}".format(
            a.tagName, a_attributes.symmetric_difference(b_attributes))

    for item_a, item_b in zip(sorted(a.attributes.items()),
                              sorted(b.attributes.items())):
        assert item_a == item_b, repr(item_a) + " : " + repr(item_b)


    for node in a.childNodes + b.childNodes:
        if node.nodeType == node.TEXT_NODE:
            node.data = string.strip(node.data)
    a.normalize()
    b.normalize()

    assert len(a.childNodes) == len(b.childNodes), \
        "{0} tag has {1} children instead of {2}".format(
            a.tagName, len(a.childNodes), len(b.childNodes))
    for ac, bc in zip(sorted(a.childNodes, _sort_nodes),
                      sorted(b.childNodes, _sort_nodes)):
        assert ac.nodeType == bc.nodeType
        assert ac.nodeType != ac.TEXT_NODE or ac.data == bc.data
        if ac.nodeType == ac.ELEMENT_NODE:
            _xml_equal(ac, bc)

"""
from StringIO import StringIO
import lxml.etree as ET
def _c14n_xml(xml):
    et = ET.parse(StringIO(xml))
    output = StringIO()
    et.write_c14n(output)
    return output.getvalue()
"""
