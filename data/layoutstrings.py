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
    # translators: very short label of the Alt Gr key
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
    # translators: description of unicode character U+2602
    _("Umbrella"),
    # translators: description of unicode character U+2606
    _("White star"),
    # translators: description of unicode character U+260F
    _("White telephone"),
    # translators: description of unicode character U+2615
    _("Hot beverage"),
    # translators: description of unicode character U+2620
    _("Skull and crossbones"),
    # translators: description of unicode character U+2622
    _("Radioactive sign"),
    # translators: description of unicode character U+262E
    _("Peace symbol"),
    # translators: description of unicode character U+262F
    _("Yin yang"),
    # translators: description of unicode character U+2639
    _("Frowning face"),
    # translators: description of unicode character U+263A
    _("Smiling face"),
    # translators: description of unicode character U+263C
    _("White sun with rays"),
    # translators: description of unicode character U+263E
    _("Last quarter moon"),
    # translators: description of unicode character U+2640
    _("Female sign"),
    # translators: description of unicode character U+2642
    _("Male sign"),
    # translators: description of unicode character U+2661
    _("White heart suit"),
    # translators: description of unicode character U+2662
    _("White diamond suit"),
    # translators: description of unicode character U+2664
    _("White spade suit"),
    # translators: description of unicode character U+2667
    _("White club suit"),
    # translators: description of unicode character U+266B
    _("Beamed eighth note"),
    # translators: description of unicode character U+2709
    _("Envelope"),
    # translators: description of unicode character U+270C
    _("Victory hand"),
    # translators: description of unicode character U+270D
    _("Writing hand"),
    # translators: description of unicode character U+1F604
    _("Smiling face with open mouth and smiling eyes"),
    # translators: description of unicode character U+1F607
    _("Smiling face with halo"),
    # translators: description of unicode character U+1F608
    _("Smiling face with horns"),
    # translators: description of unicode character U+1F609
    _("Winking face"),
    # translators: description of unicode character U+1F60A
    _("Smiling face with smiling eyes"),
    # translators: description of unicode character U+1F60B
    _("Face savouring delicious food"),
    # translators: description of unicode character U+1F60D
    _("Smiling face with heart-shaped eyes"),
    # translators: description of unicode character U+1F60E
    _("Smiling face with sunglasses"),
    # translators: description of unicode character U+1F60F
    _("Smirking face"),
    # translators: description of unicode character U+1F610
    _("Neutral face"),
    # translators: description of unicode character U+1F612
    _("Unamused face"),
    # translators: description of unicode character U+1F616
    _("Confounded face"),
    # translators: description of unicode character U+1F618
    _("Face throwing a kiss"),
    # translators: description of unicode character U+1F61A
    _("Kissing face with closed eyes"),
    # translators: description of unicode character U+1F61C
    _("Face with stuck-out tongue and winking eye"),
    # translators: description of unicode character U+1F61D
    _("Face with stuck-out tongue and tightly closed eyes"),
    # translators: description of unicode character U+1F61E
    _("Disappointed face"),
    # translators: description of unicode character U+1F620
    _("Angry face"),
    # translators: description of unicode character U+1F621
    _("Pouting face"),
    # translators: description of unicode character U+1F622
    _("Crying face"),
    # translators: description of unicode character U+1F623
    _("Persevering face"),
    # translators: description of unicode character U+1F629
    _("Weary face"),
    # translators: description of unicode character U+1F62B
    _("Tired face"),
    # translators: description of unicode character U+1F632
    _("Astonished face"),
    # translators: description of unicode character U+1F633
    _("Flushed face"),
    # translators: description of unicode character U+1F635
    _("Dizzy face"),
]

raise Exception("This module should not be executed.  It should only be"
        " parsed by i18n tools such as intltool.")
