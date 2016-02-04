/*
 * Copyright © 2016 marmuta <marmvta@gmail.com>
 * Copyright © 2016 Simon Schumann
 *
 * DBus proxy and default keyboard hiding based on ideas by Simon Schumann.
 * https://github.com/schuhumi/gnome-shell-extension-onboard-integration
 *
 * This file is part of Onboard.
 *
 * Onboard is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 3 of the License, or
 * (at your option) any later version.

 * Onboard is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program. If not, see <http://www.gnu.org/licenses/>.
 */

const Clutter = imports.gi.Clutter;
const St = imports.gi.St;
const Main = imports.ui.main;
const Tweener = imports.ui.tweener;
const Keyboard = imports.ui.keyboard.Keyboard;
const Gio = imports.gi.Gio;
const GLib = imports.gi.GLib;
const Lang = imports.lang;
const Shell = imports.gi.Shell;

const PanelMenu = imports.ui.panelMenu;
const PopupMenu = imports.ui.popupMenu;

let _onboard;


const OnboardIndicator = new Lang.Class({
    Name: 'OnboardIndicator',
    Extends: PanelMenu.Button,

    _init: function() {
        this.parent(0.0, _('Onboard'));

        this._hbox = new St.BoxLayout({ style_class: 'panel-status-menu-box' });
        this._hbox.add_child(new St.Icon({icon_name: 'onboard-panel',
                                          style_class: 'system-status-icon',
                                         }));
        this.actor.add_child(this._hbox);

        this.menu.addAction(_('Preferences'), function(event) {
            GLib.spawn_command_line_async('onboard-settings', null);
        });
    },

    _onEvent: function(actor, event) {
        if (event.type() == Clutter.EventType.BUTTON_PRESS &&
            event.get_button() == 1)
        {
            _onboard.ToggleVisible();
            return Clutter.EVENT_PROPAGATE;
        }
        else
            return this.parent(actor, event);
    },

    _onPreferencesActivate: function(item) {
    },

    destroy: function() {
        this.parent();
    },
});


const Onboard = new Lang.Class({
    Name: 'Onboard',

    _init: function() {
        const IOnboardKeyboard = '<node> \
          <interface name="org.onboard.Onboard.Keyboard"> \
            <method name="ToggleVisible"> \
            </method> \
            <method name="Show"> \
            </method> \
            <method name="Hide"> \
            </method> \
          </interface> \
        </node>';

        const OnboardProxy = Gio.DBusProxy.makeProxyWrapper(IOnboardKeyboard);
        this.proxy = new OnboardProxy(Gio.DBus.session,
                                      'org.onboard.Onboard',
                                      '/org/onboard/Onboard/Keyboard');
        this._oldKeyboardShow = null;
        this._oldKeyboardHide = null;
    },

    enable: function() {
        function KeyboardShow(outer_this) {
            return (function(monitor) {
                if (!this._keyboardRequested)
                    return;

                Main.layoutManager.keyboardIndex = monitor;
                // keep the default keyboard hidden
                this._hideSubkeys();
                Main.layoutManager.hideKeyboard();
                this._keyboardVisible = true;
                this._destroySource();
            });
        };

        function KeyboardHide(outer_this) {
            return (function() {
                if (this._keyboardRequested)
                    return;

                // still keep default keyboard hidden
                this._hideSubkeys();
                Main.layoutManager.hideKeyboard();
                this._createSource();
            });
        };

        this._oldKeyboardShow = Keyboard.prototype['_show'];
        this._oldKeyboardHide = Keyboard.prototype['_hide'];
        Keyboard.prototype['_show'] = KeyboardShow(this);
        Keyboard.prototype['_hide'] = KeyboardHide(this);

        // Start Onboard
        GLib.spawn_command_line_async('onboard', null);
    },

    disable: function() {
        Keyboard.prototype['_show'] = this._oldKeyboardShow;
        Keyboard.prototype['_hide'] = this._oldKeyboardHide;

        // Kill Onboard
        GLib.spawn_command_line_async('killall onboard', null);
    },

    Show: function() {
        this.proxy.ShowSync();
    },
    Hide: function() {
        this.proxy.HideSync();
    },
    ToggleVisible: function() {
        this.proxy.ToggleVisibleRemote();
    },
});


function init() {
}

let _indicator;

function enable() {
    _onboard = new Onboard();
    _onboard.enable();

    //Main.onboard = _onboard;   // debug

    _indicator = new OnboardIndicator();
    Main.panel.addToStatusArea('onboard-menu', _indicator);
}

function disable() {
    _onboard.disable();
    _onboard = null;
    _indicator.destroy();
}

