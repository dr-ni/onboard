
/*
 * Copyright © 2006-2008 Chris Jones <tortoise@tortuga>
 * Copyright © 2010, 2013 marmuta <marmvta@gmail.com>
 * Copyright © 2013 Gerd Kohlberger <lowfi@chello.at>
 *
 * This file is part of Onboard.
 *
 * Onboard is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 3 of the License, or
 * (at your option) any later version.
 *
 * Onboard is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program. If not, see <http://www.gnu.org/licenses/>.
 */

#include <gdk/gdkx.h>
#include <gdk/gdkkeysyms.h>

#include <X11/keysym.h>
#include <X11/XKBlib.h>
#include <X11/extensions/XTest.h>
#include <X11/extensions/XKBrules.h>

#include "osk_virtkey_x.h"

#define N_MOD_INDICES (Mod5MapIndex + 1)

typedef struct VirtkeyX VirtkeyX;

struct VirtkeyX {
    VirtkeyBase base;

    Display   *xdisplay;
    KeySym    *keysyms;
    XkbDescPtr kbd;

    KeyCode    modifier_table[N_MOD_INDICES];
    int        n_keysyms_per_keycode;
    int        shift_mod_index;
    int        alt_mod_index;
    int        meta_mod_index;
};

static int
virtkey_x_get_current_group (VirtkeyBase *base)
{
    VirtkeyX* this = (VirtkeyX*) base;
    XkbStateRec state;

    if (XkbGetState (this->xdisplay, XkbUseCoreKbd, &state) != Success)
    {
        PyErr_SetString (OSK_EXCEPTION, "XkbGetState failed");
        return -1;
    }
    return state.locked_group;
}

static char*
virtkey_x_get_current_group_name (VirtkeyBase* base)
{
    VirtkeyX* this = (VirtkeyX*) base;
    char* result = NULL;
    int group;

    if (!this->kbd->names || !this->kbd->names->groups)
    {
        PyErr_SetString (OSK_EXCEPTION, "no group names available");
        return NULL;
    }

    group = virtkey_x_get_current_group(base);
    if (group < 0)
        return NULL;

    if (this->kbd->names->groups[group] != None)
    {
        char *name = XGetAtomName (this->xdisplay,
                                   this->kbd->names->groups[group]);
        if (name)
        {
            result = strdup(name);
            XFree (name);
        }
    }

    return result;
}


static KeyCode
keysym_to_keycode(XkbDescPtr kbd, KeySym keysym, int group, unsigned *mod_mask)
{
    KeyCode result = 0;
    KeyCode keycode = 0;
    int num_groups;
    int key_group;
    int num_levels;
    int level;

    for (keycode = kbd->min_key_code; keycode < kbd->max_key_code; keycode++)
    {
        num_groups = XkbKeyNumGroups(kbd, keycode);
        key_group = group;

        if (num_groups == 0)
        {
            key_group = 0;
        }
        else if (num_groups == 1)
        {
            key_group = 0;
        }
        else if (key_group >= num_groups)
        {
            unsigned int group_info = XkbKeyGroupInfo(kbd, keycode);

            switch (XkbOutOfRangeGroupAction(group_info))
            {
                case XkbClampIntoRange:
                    key_group = num_groups - 1;
                    break;

                case XkbRedirectIntoRange:
                    key_group = XkbOutOfRangeGroupNumber(group_info);
                    if (key_group >= num_groups)
                        key_group = 0;
                    break;

                case XkbWrapIntoRange:
                default:
                    key_group %= num_groups;
                    break;
            }
        }

        num_levels = XkbKeyGroupWidth(kbd, keycode, key_group);
        for (level = 0; level < num_levels; level++)
        {
            KeySym ks = XkbKeySymEntry(kbd, keycode, level, group);
            if (ks == keysym)
            {
                int i;
                XkbKeyTypePtr key_type = XkbKeyKeyType(kbd, keycode, group);
                int map_count = key_type->map_count;

                #ifdef DEBUG_OUTPUT
                printf("kc %d level %d ks %ld key_type->num_levels %d, key_type->map_count %d, mods m %d r %d v %d\n",
                        keycode, level, ks, key_type->num_levels, key_type->map_count, key_type->mods.mask, key_type->mods.real_mods, key_type->mods.vmods);
                for (i = 0; i < map_count; i++)
                {
                    XkbKTMapEntryPtr entry = key_type->map + i;
                    printf("xxx i %d: level %d entry->level %d entry->modsmask %d \n",
                            i, level, entry->level, entry->mods.mask);
                }
                #endif

                if (level == 0)
                {
                    result = keycode;
                    *mod_mask = 0;
                }
                else
                {
                    for (i = 0; i < map_count; i++)
                    {
                        XkbKTMapEntryPtr entry = key_type->map + i;
                        if (entry->level == level)
                        {
                            result = keycode;
                            *mod_mask = entry->mods.mask;
                            break;
                        }
                    }
                }

                break;
            }
        }

        if (result)
            break;
    }

    return result;
}

static int
virtkey_x_get_keycode_from_keysym (VirtkeyBase* base, int keysym, unsigned int *mod_mask)
{
    static int modified_key = 0;
    KeyCode keycode;
    VirtkeyX* this = (VirtkeyX*) base;
    int group = virtkey_x_get_current_group(base);
    if (group < 0)
        return 0;

    keycode = keysym_to_keycode(this->kbd, keysym, group, mod_mask);

    if (!keycode)
    {
        int index;
        /* Change one of the last 10 keysyms to our converted utf8,
         * remapping the x keyboard on the fly. This make assumption
         * the last 10 arn't already used.
         */
        modified_key = (modified_key + 1) % 10;

        /* Point at the end of keysyms, modifier 0 */
        index = (this->kbd->max_key_code - this->kbd->min_key_code - modified_key - 1) *
                 this->n_keysyms_per_keycode;

        this->keysyms[index] = keysym;

        XChangeKeyboardMapping (this->xdisplay,
                                this->kbd->min_key_code,
                                this->n_keysyms_per_keycode,
                                this->keysyms,
                                this->kbd->max_key_code - this->kbd->min_key_code);
        XSync (this->xdisplay, False);
        /* From dasher src:
         * There's no way whatsoever that this could ever possibly
         * be guaranteed to work (ever), but it does.
         *
         * The below is lightly safer:
         *
         * keycode = XKeysymToKeycode(fk->xdisplay, keysym);
         *
         * but this appears to break in that the new mapping is not immediatly
         * put to work. It would seem a MappingNotify event is needed so
         * Xlib can do some changes internally? (xlib is doing something
         * related to above?)
         */
        keycode = this->kbd->max_key_code - modified_key - 1;
    }

    return keycode;
}

static void
virtkey_x_get_label_from_keycode(VirtkeyBase* base,
    int keycode, int modmask, int group,
    char* label, int max_label_size)
{
    VirtkeyX* this = (VirtkeyX*) base;
    unsigned int mods;
    int label_size;
    KeySym keysym;
    XKeyPressedEvent ev;

    memset(&ev, 0, sizeof(ev));
    ev.type = KeyPress;
    ev.display = this->xdisplay;

    mods = XkbBuildCoreState (modmask, group);

    ev.state = mods;
    ev.keycode = keycode;
    label_size = XLookupString(&ev, label, max_label_size, &keysym, NULL);
    label[label_size] = '\0';

    if (keysym)
    {
        strncpy(label, virtkey_get_label_from_keysym(keysym), max_label_size);
        label[max_label_size] = '\0';
    }
}

static int
virtkey_x_get_keysym_from_keycode(VirtkeyBase* base,
                                  int keycode, int modmask, int group)
{
    KeySym keysym;
    unsigned int mods_rtn;

    VirtkeyX* this = (VirtkeyX*) base;

    XkbTranslateKeyCode (this->kbd,
                         keycode,
                         XkbBuildCoreState (modmask, group),
                         &mods_rtn,
                         &keysym);
    return keysym;
}

/**
 * Reads the contents of the root window property _XKB_RULES_NAMES.
 */
static char**
virtkey_x_get_rules_names(VirtkeyBase* base, int* numentries)
{
    VirtkeyX* this = (VirtkeyX*) base;
    XkbRF_VarDefsRec vd;
    char *tmp = NULL;
    char** results;
    const int n = 5;

    if (!XkbRF_GetNamesProp (this->xdisplay, &tmp, &vd))
        return NULL;

    results = malloc(sizeof(char*) * n);
    if (!results)
        return NULL;

    *numentries = n;

    if (tmp)
    {
        results[0] = strdup(tmp);
        XFree (tmp);
    }
    else
        results[0] = strdup("");

    if (vd.model)
    {
        results[1] = strdup(vd.model);
        XFree (vd.model);
    }
    else
        results[1] = strdup("");

    if (vd.layout)
    {
        results[2] = strdup(vd.layout);
        XFree (vd.layout);
    }
    else
        results[2] = strdup("");

    if (vd.variant)
    {
        results[3] = strdup(vd.variant);
        XFree (vd.variant);
    }
    else
        results[3] = strdup("");

    if (vd.options)
    {
        results[4] = strdup(vd.options);
        XFree (vd.options);
    }
    else
        results[4] = strdup("");

    return results;
}

/*
 * Return a string representative of the whole layout including all groups.
 * Caller takes ownership, call free() on the result.
 */
static char*
virtkey_x_get_layout_as_string (VirtkeyBase* base)
{
    VirtkeyX* this = (VirtkeyX*) base;
    char* result = NULL;
    char* symbols;

    if (!this->kbd->names || !this->kbd->names->symbols)
    {
        PyErr_SetString (OSK_EXCEPTION, "no symbols names available");
        return NULL;
    }

    symbols = XGetAtomName (this->xdisplay, this->kbd->names->symbols);
    if (symbols)
    {
        result = strdup(symbols);
        XFree (symbols);
    }

    return result;
}

void
virtkey_x_set_modifiers (VirtkeyBase* base,
                         int mod_mask, bool lock, bool press)
{
    VirtkeyX* this = (VirtkeyX*) base;
    if (lock)
        XkbLockModifiers (this->xdisplay, XkbUseCoreKbd,
                            mod_mask, press ? mod_mask : 0);
    else
        XkbLatchModifiers (this->xdisplay, XkbUseCoreKbd,
                            mod_mask, press ? mod_mask : 0);

    XSync (this->xdisplay, False);
}

static int
virtkey_x_init_keyboard (VirtkeyX *self)
{
    self->kbd = XkbGetKeyboard (self->xdisplay,
                              XkbCompatMapMask | XkbNamesMask | XkbGeometryMask,
                              XkbUseCoreKbd);
#ifndef NDEBUG
    /* test missing keyboard (LP:#526791) keyboard on/off every 10 seconds */
    if (getenv ("VIRTKEY_DEBUG"))
    {
        if (self->kbd && time(NULL) % 20 < 10)
        {
            XkbFreeKeyboard (self->kbd, XkbAllComponentsMask, True);
            self->kbd = NULL;
        }
    }
#endif
    if (!self->kbd)
    {
        PyErr_SetString (OSK_EXCEPTION, "XkbGetKeyboard failed.");
        return -1;
    }
    if (XkbGetNames (self->xdisplay, XkbAllNamesMask, self->kbd) != Success)
    {
        PyErr_SetString (OSK_EXCEPTION, "XkbGetNames failed.");
        return -1;
    }

    return 0;
}

static int
virtkey_x_init (VirtkeyBase *base)
{
    VirtkeyX* this = (VirtkeyX*) base;
    XModifierKeymap *modifiers;
    int mod_index, mod_key;

    GdkDisplay* display = gdk_display_get_default ();
    if (!GDK_IS_X11_DISPLAY (display)) // Wayland, MIR?
    {
        PyErr_SetString (OSK_EXCEPTION, "not an X display");
        return -1;
    }
    this->xdisplay = GDK_DISPLAY_XDISPLAY (display);

    if (virtkey_x_init_keyboard (this) < 0)
        return -1;

    /* init modifiers */
    this->keysyms = XGetKeyboardMapping (this->xdisplay,
                                       this->kbd->min_key_code,
                                       this->kbd->max_key_code - this->kbd->min_key_code + 1,
                                       &this->n_keysyms_per_keycode);

    modifiers = XGetModifierMapping (this->xdisplay);
    for (mod_index = 0; mod_index < 8; mod_index++)
    {
        this->modifier_table[mod_index] = 0;

        for (mod_key = 0; mod_key < modifiers->max_keypermod; mod_key++)
        {
            int keycode = modifiers->modifiermap[mod_index *
                                                 modifiers->max_keypermod +
                                                 mod_key];
            if (keycode)
            {
                this->modifier_table[mod_index] = keycode;
                break;
            }
        }
    }

    XFreeModifiermap (modifiers);

    for (mod_index = Mod1MapIndex; mod_index <= Mod5MapIndex; mod_index++)
    {
        if (this->modifier_table[mod_index])
        {
            KeySym ks = XkbKeycodeToKeysym (this->xdisplay,
                                            this->modifier_table[mod_index],
                                            0, 0);

            /* Note: ControlMapIndex is already defined by xlib */
            switch (ks) {
                case XK_Meta_R:
                case XK_Meta_L:
                    this->meta_mod_index = mod_index;
                    break;

                case XK_Alt_R:
                case XK_Alt_L:
                    this->alt_mod_index = mod_index;
                    break;

                case XK_Shift_R:
                case XK_Shift_L:
                    this->shift_mod_index = mod_index;
                    break;
            }
        }
    }

    return 0;
}

static int
virtkey_x_reload (VirtkeyBase* base)
{
    VirtkeyX* this = (VirtkeyX*) base;

    if (this->kbd)
    {
        XkbFreeKeyboard (this->kbd, XkbAllComponentsMask, True);
        this->kbd = NULL;
    }

    if (virtkey_x_init_keyboard (this) < 0)
        return -1;

    return 0;
}

static void
virtkey_x_destruct (VirtkeyBase *base)
{
    VirtkeyX* this = (VirtkeyX*) base;

    if (this->kbd)
        XkbFreeKeyboard (this->kbd, XkbAllComponentsMask, True);

    if (this->keysyms)
        XFree (this->keysyms);
}

VirtkeyBase*
virtkey_x_new(void)
{
   VirtkeyBase* this = (VirtkeyBase*) malloc(sizeof(VirtkeyX));
   this->init = virtkey_x_init;
   this->destruct = virtkey_x_destruct;
   this->reload = virtkey_x_reload;
   this->get_current_group = virtkey_x_get_current_group;
   this->get_current_group_name = virtkey_x_get_current_group_name;
   this->get_label_from_keycode = virtkey_x_get_label_from_keycode;
   this->get_keysym_from_keycode = virtkey_x_get_keysym_from_keycode;
   this->get_keycode_from_keysym = virtkey_x_get_keycode_from_keysym;
   this->get_rules_names = virtkey_x_get_rules_names;
   this->get_layout_as_string = virtkey_x_get_layout_as_string;
   this->set_modifiers = virtkey_x_set_modifiers;
   return this;
}

