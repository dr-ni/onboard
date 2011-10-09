#!/usr/bin/python
#
# This file contains a copy of the strings of the layout files (.onboard files)
# that needs translation. As the current build system cannot extract the
# strings that need translation directly from the layout files, it gets them
# from this file.
#
# Please, keep the strings alphabetically sorted; it will be easier to check
# whether a given string is already present.


from gettext import gettext as _

TRANSLATABLE_LAYOUT_STRINGS = [
    _("Activate Hover Click"),
    _("Alphanumeric keys"),
    _("Alt"),
    _("Alt Gr"),
    _("CAPS"),
    _("Ctrl"),
    _("Del"),
    _("Double click"),
    _("Drag click"),
    _("End"),
    _("Ent"),
    _("ESC"),
    _("Function keys"),
    _("Function keys and number block"),
    _("Hide Onboard"),
    _("Hm"),
    _("Ins"),
    _("Main keyboard"),
    _("Menu"),
    _("Middle click"),
    _("Move Onboard window"),
    _("Nm&#10;Lk"),
    _("Number block and snippets"),
    _("Pause"),
    _("Pg&#10;Dn"),
    _("Pg&#10;Up"),
    _("Preferences"),
    _("Prnt"),
    _("Quit"),
    _("Return"),
    _("Right click"),
    _("Scroll"),
    _("Settings"),
    _("Snippets"),
    _("Space"),
    _("Toggle click helpers"),
    _("Tab"),
    _("Win"),
]

raise Exception("This module should not be executed.  It should only be"
        " parsed by i18n tools such as intltool.")
