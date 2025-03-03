'use strict';

/*
 * Copyright © 2016 marmuta
 * Copyright © 2016 Simon Schumann
 *
 * DBus proxy and default keyboard hiding based on ideas by Simon Schumann.
 * https://github.com/schuhumi/gnome-shell-extension-onboard-integration
 *
 * EdgeDragAction gesture based on code by Simon Schumann.
 * https://github.com/schuhumi/gnome-shell-extension-slide-for-keyboard
 *
 * This file is part of Onboard.
 *
 * Onboard is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 3 of the License, or
 * any later version.
 *
 * Onboard is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program. If not, see <http://www.gnu.org/licenses/>.
 */

// GJS / GNOME Shell imports (ES module paths)
import Clutter from 'gi://Clutter';
import St from 'gi://St';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import GObject from 'gi://GObject';

// Shell UI modules
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as EdgeDragAction from 'resource:///org/gnome/shell/ui/edgeDragAction.js';
import { Keyboard } from 'resource:///org/gnome/shell/ui/keyboard.js';

// Extension base class + gettext
import { Extension, gettext as _ } from 'resource:///org/gnome/shell/extensions/extension.js';

/**
 * DBus proxy class for Onboard (virtual keyboard).
 */
class Onboard {
    constructor() {
        const IOnboardKeyboard = `
<node>
  <interface name="org.onboard.Onboard.Keyboard">
    <method name="ToggleVisible"/>
    <method name="Show"/>
    <method name="Hide"/>
  </interface>
</node>
`;
        // Create the DBus proxy
        this.initProxy();

        // Store the original GNOME keyboard methods
        this._oldKeyboardShow = null;
        this._oldKeyboardHide = null;
    }
    initProxy(retries = 0) {
        let maxRetries = 5;
        const OnboardProxy = Gio.DBusProxy.makeProxyWrapper(IOnboardKeyboard);
    
        try {
            this.proxy = new OnboardProxy(Gio.DBus.session,
                'org.onboard.Onboard',
                '/org/onboard/Onboard/Keyboard');
            print("Connected to Onboard DBus successfully.");
        } catch (e) {
            if (retries < maxRetries) {
                print(`DBus connection failed, retrying in 1 second... (${retries + 1}/${maxRetries})`);
    
                // Start Onboard only on the first attempt
                if (retries === 0) {
                    GLib.spawn_command_line_async('onboard');
                }
    
                // Wait 1 second, then retry
                GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1000, () => {
                    this.initProxy(retries + 1);
                    return false;  // Ensures the timeout only runs once
                });
            } else {
                print("Failed to connect to Onboard DBus after multiple attempts.");
            }
        }
    }
    enable() {
        // Launch Onboard if not already active
        this.launch();

        // Backup the original GNOME keyboard show/hide methods
        this._oldKeyboardShow = Keyboard.prototype['_show'];
        this._oldKeyboardHide = Keyboard.prototype['_hide'];

        // Replace them with our overrides
        Keyboard.prototype['_show'] = this._overrideShow(this);
        Keyboard.prototype['_hide'] = this._overrideHide(this);
    }

    disable() {
        // Restore original keyboard methods
        if (this._oldKeyboardShow)
            Keyboard.prototype['_show'] = this._oldKeyboardShow;
        if (this._oldKeyboardHide)
            Keyboard.prototype['_hide'] = this._oldKeyboardHide;

        // Kill Onboard
        GLib.spawn_command_line_async('killall onboard');
    }

    // Launch Onboard if it is not running
    launch() {
        if (!this.proxy.g_name_owner)
            GLib.spawn_command_line_async('onboard');
    }

    show() {
        this.proxy.ShowSync();
    }

    hide() {
        this.proxy.HideSync();
    }

    toggleVisible() {
        this.proxy.ToggleVisibleRemote();
    }

    // Show "either Onboard or GNOME's internal keyboard" depending on context
    showAnyKeyboard() {
        Main.keyboard._keyboardRequested = true;
        Main.keyboard._keyboardVisible = false;
        Main.keyboard.Show(global.get_current_time());

        if (Main.actionMode === Shell.ActionMode.NORMAL)
            this.show();
    }

    // Override for the _show() method in GNOME's Keyboard class
    _overrideShow(outerThis) {
        return function (monitor) {
            if (!this._keyboardRequested)
                return;

            Main.layoutManager.keyboardIndex = monitor;

            if (Main.actionMode === Shell.ActionMode.NORMAL) {
                // Hide the built-in keyboard
                this._hideSubkeys();
                Main.layoutManager.hideKeyboard();
                this._keyboardVisible = true;
            } else {
                // In overview or password dialogs -> hide Onboard, show GNOME keyboard
                outerThis.hide();
                this._redraw();
                Main.layoutManager.showKeyboard();
            }
            this._destroySource();
        };
    }

    // Override for the _hide() method in GNOME's Keyboard class
    _overrideHide(_outerThis) {
        return function () {
            if (this._keyboardRequested)
                return;

            this._hideSubkeys();
            Main.layoutManager.hideKeyboard();
            this._createSource();
        };
    }
}

/**
 * Panel indicator (icon + popup menu) for Onboard.
 * Short left-click: toggle Onboard
 * Long left-click: open menu
 * Right-click: open menu
 * Short touch: toggle Onboard
 * Long touch: open menu
 */
class OnboardIndicator extends PanelMenu.Button {
    _init() {
        // Prevent auto menu opening on left-click
        super._init(0.0, _('Onboard Indicator'));
				log("onboard init")
        // Track press times for mouse/touch
        this._mousePressTime = 0;
        this._touchPressTime = 0;
        this._lastToggleTime = 0;



        // Timer-IDs für langes Drücken
        this._mouseLongPressTimeoutId = null;
        this._touchLongPressTimeoutId = null;
        // Flag, ob das lange Drücken bereits "ausgelöst" wurde
        this._mouseLongPressActivated = false;
        this._touchLongPressActivated = false;
        
        // Create the icon in the panel
        let box = new St.BoxLayout({ style_class: 'panel-status-menu-box' });
        let icon = new St.Icon({
            icon_name: 'onboard-symbolic',
            style_class: 'system-status-icon',
        });
        box.add_child(icon);
        this.add_child(box);

        // Build the popup menu: Preferences, Help, Exit, etc.
        this.menu.addAction(_('Preferences'), () => {
            GLib.spawn_command_line_async('onboard-settings');
        });

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        this.menu.addAction(_('Help'), () => {
            GLib.spawn_command_line_async('/usr/bin/yelp help:onboard');
        });

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        this.menu.addAction(_('Exit Onboard'), () => {
            GLib.spawn_command_line_async('killall onboard');
        });

        // Connect signals for mouse & touch events
        this.connect('button-press-event', this._onButtonPress.bind(this));
        this.connect('button-release-event', this._onButtonRelease.bind(this));
        this.connect('touch-event', this._onTouchEvent.bind(this));
    }

    /**
     * Mouse button pressed event.
     */
    _onButtonPress(_actor, event) {
        // Only handle left mouse button (button = 1)
        if (event.get_button() !== 1)
            return Clutter.EVENT_PROPAGATE;

        // Store the press time
        this._mousePressTime = event.get_time();
        this._mouseLongPressActivated = false;

        // Set a 1-second timeout for the long-press action
        // If the user keeps holding the mouse button for 1 second,
        // we open the menu without requiring a release event.
        if (this._mouseLongPressTimeoutId) {
            GLib.source_remove(this._mouseLongPressTimeoutId);
            this._mouseLongPressTimeoutId = null;
        }
        this._mouseLongPressTimeoutId = GLib.timeout_add(
            GLib.PRIORITY_DEFAULT,
            1000, // 1 second
            () => {
                this._mouseLongPressActivated = true;
                this.menu.open();
                this._mouseLongPressTimeoutId = null;
                return GLib.SOURCE_REMOVE;
            }
        );
        // toggle the menu if not the menu
        this.menu.close();
        return Clutter.EVENT_PROPAGATE;
    }
    /**
     * Mouse button released event.
     */
    _onButtonRelease(_actor, event) {
        if (event.type() !== Clutter.EventType.BUTTON_RELEASE)
            return Clutter.EVENT_PROPAGATE;

        if (event.get_button() !== 1)
            return Clutter.EVENT_PROPAGATE;

        // Cancel the long-press timeout if it's still pending
        if (this._mouseLongPressTimeoutId) {
            GLib.source_remove(this._mouseLongPressTimeoutId);
            this._mouseLongPressTimeoutId = null;
        }

        // Determine how long the mouse was held
        let duration = event.get_time() - this._mousePressTime;

        // If the duration was < 1 second and we did NOT trigger the long press,
        // treat it as a short click → toggle Onboard
        if (duration < 500 && !this._mouseLongPressActivated) {
            this._toggleOnboard();
        } else {
            this.menu.toggle();
        }
        // If it was >= 1 second, the menu was already opened by the timeout

        return Clutter.EVENT_PROPAGATE;
    }



    /**
     * Touch events (finger down/up).
     */
    _onTouchEvent(_actor, event) {
        const type = event.type();

        if (type === Clutter.EventType.TOUCH_BEGIN) {
            // Finger placed on the indicator
            this._touchPressTime = event.get_time();
            this._touchLongPressActivated = false;

            // Start the 1-second timeout for a long press
            if (this._touchLongPressTimeoutId) {
                GLib.source_remove(this._touchLongPressTimeoutId);
                this._touchLongPressTimeoutId = null;
            }
            this._touchLongPressTimeoutId = GLib.timeout_add(
                GLib.PRIORITY_DEFAULT,
                1000, // 1 second
                () => {
                    this._touchLongPressActivated = true;
                    this.menu.open();
                    this._touchLongPressTimeoutId = null;
                    return GLib.SOURCE_REMOVE;
                }
            );

        } else if (type === Clutter.EventType.TOUCH_END) {
            // Finger lifted
            if (this._touchLongPressTimeoutId) {
                GLib.source_remove(this._touchLongPressTimeoutId);
                this._touchLongPressTimeoutId = null;
            }

            let duration = event.get_time() - this._touchPressTime;

            // If it was a short press (<1s) and no long-press action triggered,
            // toggle Onboard
            if (duration < 500 && !this._touchLongPressActivated) {
                this._toggleOnboard();
            }
            // If >=1s, the menu was already opened

        }
        return Clutter.EVENT_PROPAGATE;
    }


    /**
     * Toggles Onboard: starts it if not running, or hides/shows if it is.
     */
    _toggleOnboard() {
        // Prevent spamming toggles more than once within 500 ms
        let now = Date.now();
        if (now - this._lastToggleTime < 500)
            return;

        this._lastToggleTime = now;

        if (globalThis.OnboardExtension?._onboard) {
            // Make sure Onboard is running
            globalThis.OnboardExtension._onboard.launch();
            // Toggle visibility
            globalThis.OnboardExtension._onboard.toggleVisible();
        }
    }
}

// Register the class with GObject so it has a GType.
const OnboardIndicatorObj = GObject.registerClass(OnboardIndicator);

/**
 * Main Extension class (ES module style).
 */
export default class OnboardExtension extends Extension {
    constructor(metadata) {
        super(metadata);
        this._onboard = null;
        this._indicator = null;
        this._gesture = null;
        this._settingsChangedId = null;
    }

    enable() {
        // Load GSettings (based on "settings-schema" in metadata.json)
        const settings = this.getSettings();

        // Example logic: set schema-version if empty, enable "auto-show"
        let schemaVersion = settings.get_string('schema-version');
        if (!schemaVersion) {
            settings.set_string('schema-version', '1.0');
            let autoShow = new Gio.Settings({ schema_id: 'org.onboard.auto-show' });
            if (autoShow)
                autoShow.set_boolean('enabled', true);
        }

        // Create and enable the Onboard instance
        this._onboard = new Onboard();
        this._onboard.enable();

        // Create the indicator and add it to the panel
        this._indicator = new OnboardIndicatorObj();
        Main.panel.addToStatusArea('onboard-menu', this._indicator, 1);

        // Listen for changes to "enable-show-gesture"
        this._updateGesture(settings.get_boolean('enable-show-gesture'));
        this._settingsChangedId = settings.connect('changed::enable-show-gesture', () => {
            this._updateGesture(settings.get_boolean('enable-show-gesture'));
        });

        // Make it accessible globally (optional)
        globalThis.OnboardExtension = this;
    }

    disable() {
        // Remove the edge drag gesture
        this._updateGesture(false);

        // Disconnect from GSettings
        const settings = this.getSettings();
        if (this._settingsChangedId) {
            settings.disconnect(this._settingsChangedId);
            this._settingsChangedId = null;
        }

        // Disable Onboard logic
        if (this._onboard) {
            this._onboard.disable();
            this._onboard = null;
        }

        // Remove the indicator
        if (this._indicator) {
            this._indicator.destroy();
            this._indicator = null;
        }

        globalThis.OnboardExtension = null;
    }

    /**
     * Enable or disable the bottom-edge gesture (drag from bottom to show keyboard).
     */
    _updateGesture(enable) {
        if (enable) {
            if (!this._gesture) {
                this._gesture = new EdgeDragAction.EdgeDragAction(
                    St.Side.BOTTOM,
                    Shell.ActionMode.NORMAL
                );
                log('Edge gesture init');
                this._gesture.connect('activated', () => {
                    log('Edge drag activated');

                    this._onboard?.showAnyKeyboard();
                });
                global.stage.add_action(this._gesture);
                
            }
        } else {
            if (this._gesture) {
                global.stage.remove_action(this._gesture);
                this._gesture = null;
            }
        }
    }
}
