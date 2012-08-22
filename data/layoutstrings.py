#!/usr/bin/python3
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
    # translators: very short label of the left Alt key
    _("Alt"),
    # translators: very short label of the Alt Gr key key
    _("Alt Gr"),
    # translators: very short label of the CAPS LOCK key
    _("CAPS"),
    # translators: very short label of the Ctrl key
    _("Ctrl"),
    # translators: very short label of the DELETE key
    _("Del"),
    _("Double click"),
    _("Drag click"),
    # translators: very short label of the numpad END key
    _("End"),
    # translators: very short label of the numpad ENTER key
    _("Ent"),
    # translators: very short label of the ESCAPE key
    _("Esc"),
    _("Function keys"),
    _("Number block and function keys"),
    _("Hide Onboard"),
    # translators: very short label of the HOME key
    _("Hm"),
    # translators: very short label of the INSERT key
    _("Ins"),
    _("Main keyboard"),
    # translators: very short label of the Menu key
    _("Menu"),
    _("Middle click"),
    _("Move Onboard"),
    # translators: very short label of the NUMLOCK key
    _("Nm&#10;Lk"),
    _("Number block and snippets"),
    # translators: very short label of the PAUSE key
    _("Pause"),
    # translators: very short label of the PAGE DOWN key
    _("Pg&#10;Dn"),
    # translators: very short label of the PAGE UP key
    _("Pg&#10;Up"),
    # translators: very short label of the Preferences button
    _("Preferences"),
    # translators: very short label of the PRINT key
    _("Prnt"),
    # translators: very short label of the Quit button
    _("Quit"),
    # translators: very short label of the RETURN key
    _("Return"),
    _("Right click"),
    # translators: very short label of the SCROLL key
    _("Scroll"),
    _("Snippets"),
    _("Space"),
    _("Toggle click helpers"),
    # translators: very short label of the TAB key
    _("Tab"),
    # translators: very short label of the default SUPER key
    _("Win"),
]

raise Exception("This module should not be executed.  It should only be"
        " parsed by i18n tools such as intltool.")
