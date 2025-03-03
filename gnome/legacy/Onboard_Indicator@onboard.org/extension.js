/*
 * Copyright © 2016 marmuta <marmvta@gmail.com>
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
const { GObject, St } = imports.gi;
const Main = imports.ui.main;
const Keyboard = imports.ui.keyboard.Keyboard;
const Gio = imports.gi.Gio;
const GLib = imports.gi.GLib;
const Lang = imports.lang;
const Shell = imports.gi.Shell;
const EdgeDragAction = imports.ui.edgeDragAction;

const PanelMenu = imports.ui.panelMenu;
const PopupMenu = imports.ui.popupMenu;

const this_extension = imports.misc.extensionUtils.getCurrentExtension();
const Convenience = this_extension.imports.convenience;
const USE_GOBJECT = typeof GObject.registerClass !== 'undefined';


let _onboard;
let _indicator;
let _gesture = null;
let Schema;

let OnboardIndicator;
let Onboard;

if (USE_GOBJECT) {
/**
 * Panel indicator (icon + popup menu) for Onboard.
 * Short left-click: toggle Onboard
 * Long left-click: open menu
 * Right-click: open menu
 * Short touch: toggle Onboard
 * Long touch: open menu
 */
    OnboardIndicator = GObject.registerClass(
        class OnboardIndicator extends PanelMenu.Button {
        _init() {
            // Prevent auto menu opening on left-click
            super._init(0.0, _('Onboard Indicator'));
            
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
    
    
            this.exitAction = this.menu.addAction(_('Exit Onboard'), () => {
                if(_onboard) {
    
                    if (_onboard.isNotRunning()) {
                        // Onboard is NOT running, so start it
                        _onboard.show();
                        _onboard.launch();
                        this.exitAction.label.text = _('Exit Onboard');
                    } else {
                        // Onboard IS running, so exit it
                        _onboard.kill();
                        this.exitAction.label.text = _('Start Onboard');
                    }
                }
            });
            this._updateExitActionLabel();
    
            // Connect signals for mouse & touch events
            this.connect('button-press-event', this._onButtonPress.bind(this));
            this.connect('button-release-event', this._onButtonRelease.bind(this));
            this.connect('touch-event', this._onTouchEvent.bind(this));
        }
        // Function to check and dynamically update the text when Onboard status changes
        _updateExitActionLabel() {
            if (_onboard && _onboard._isRunning) {
                this.exitAction.label.text = _('Exit Onboard');
            } else {
                this.exitAction.label.text  = _('Start Onboard');
            }
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
    
            if (_onboard) {
                // Toggle visibility
                _onboard.toggleVisible();
                // Make sure Onboard is running
                _onboard.launch();
            }
        }
    }
    );
    Onboard = GObject.registerClass(
        class Onboard extends GObject.Object {
            _init() {
                super._init();

                this._commandQueue = null;  // Queue to store the last command if the proxy is not connected
                this._isRunning = false;  // Flag to track Onboard's running status
                this._proxy = null;       // The DBus proxy for Onboard
                this.OnboardProxy = Gio.DBusProxy.makeProxyWrapper(`
        <node>
            <interface name="org.onboard.Onboard.Keyboard">
                <method name="ToggleVisible"/>
                <method name="Show"/>
                <method name="Hide"/>
            </interface>
        </node>
        `);

                // Call initProxy once with a slight delay to avoid startup conflicts
                GLib.timeout_add(GLib.PRIORITY_DEFAULT, 500, () => {
                    this._launch();

                    this.connectProxy(0);
                    return false; // Ensures timeout only runs once
                });
                // Store the original GNOME keyboard methods
                this._oldKeyboardShow = null;
                this._oldKeyboardHide = null;
            }

            // Check if Onboard process is running
            _isOnboardRunning() {
                try {
                    const [success, stdout, stderr] = GLib.spawn_command_line_sync('pgrep onboard');
                    return success && stdout.length > 0;
                } catch (e) {
                    return false;
                }
            }

            connectProxy(retries = 0) {

                let maxRetries = 5;
            
                try {
                    this.proxy = new this.OnboardProxy(Gio.DBus.session,
                        'org.onboard.Onboard',
                        '/org/onboard/Onboard/Keyboard');

                    this._isRunning = true;   // Onboard is running
                    this.enable();
                    print("Connected to Onboard DBus successfully.");
                } catch (e) {
                    if (retries < maxRetries) {
                        print(`DBus connection failed, retrying in 1 second... (${retries + 1}/${maxRetries})`);
            
                        // Wait 1 second, then retry
                        GLib.timeout_add(GLib.PRIORITY_DEFAULT, 200, () => {
                            this.connectProxy(retries + 1);
                            return false;  // Ensures the timeout only runs once
                        });
                    } else {
                        print("Failed to connect to Onboard DBus after multiple attempts.");
                    }
                }
            }

            // Disconnect the DBus proxy when Onboard exits
            disconnectProxy() {
                this._isRunning = false;
                this._proxy = null;
                _indicator._updateExitActionLabel();
                print("Onboard process ended and proxy disconnected.");
            }

            enable() {
                // Launch Onboard if not already active
                // this.launch();

                if (this._commandQueue!=null) {
                    const commandQueue = this._commandQueue;
                    this._commandQueue = null;
                        // Call this with a delay to avoid startup conflicts
                                GLib.timeout_add(GLib.PRIORITY_DEFAULT, 200, () => {
                                        if (commandQueue === 'show') {
                                            this.show();
                                        } else if (commandQueue === 'hide') {
                                            this.hide();
                                        } else if (commandQueue === 'toggleVisible') {
                                            this.toggleVisible();
                                        }
                                    return false; // Ensures timeout only runs once
                                });
                }
                // Backup the original GNOME keyboard show/hide methods
                this._oldKeyboardShow = Keyboard.prototype['_show'];
                this._oldKeyboardHide = Keyboard.prototype['_hide'];

                // Replace them with our overrides
                Keyboard.prototype['_show'] = this._overrideShow(this);
                Keyboard.prototype['_hide'] = this._overrideHide(this);
                // Listen for Onboard process changes to update the menu dynamically
                this.proxy.connect('g-name-owner-changed', () => {
                    _indicator._updateExitActionLabel();
                });
            }

            disable() {
                // Restore original keyboard methods
                if (this._oldKeyboardShow)
                    Keyboard.prototype['_show'] = this._oldKeyboardShow;
                if (this._oldKeyboardHide)
                    Keyboard.prototype['_hide'] = this._oldKeyboardHide;

                this.kill()
            }

            // Launch Onboard if it is not running
            launch() {
                if (this.isNotRunning()) {
                    this._launch();

                    // Call initProxy once with a slight delay to avoid startup conflicts
                    GLib.timeout_add(GLib.PRIORITY_DEFAULT, 200, () => {
                        this.connectProxy(0);
                        return false; // Ensures timeout only runs once
                    });
                }
            }

            // Launch Onboard if it is not running
            _launch() {
                if(!this._isRunning && !this._isOnboardRunning()) {
                    this._isRunning=true;
                    print("Onboard is not running launch it.");
                    _indicator._updateExitActionLabel();
                    GLib.spawn_command_line_async('onboard', () => {
                        print("Onboard process ended.");
                        this.disconnectProxy();  // Disconnect proxy after Onboard exits
                    });
                } else {
                    this._isRunning=true;
                }
            }


            // Kill Onboard
            kill() {
                this.disconnectProxy();  // Ensure proxy is disconnected
                // this.proxy.disconnect('g-name-owner-changed');
                GLib.spawn_command_line_async('killall onboard');
            }

            // Launch Onboard if it is not running
            isNotRunning() {
                return !this.proxy || !this.proxy.g_name_owner;
            }

            show() {
                if (this.isNotRunning()) {
                    this._commandQueue = "show";
                } else {
                    this.proxy.ShowSync();
                }
            }

            hide() {
                if (this.isNotRunning()) {
                    this._commandQueue = "hide";
                } else {
                    this.proxy.HideSync();
                }
            }

            toggleVisible() {
                if (this.isNotRunning()) {
                    this._commandQueue = "toggleVisible";
                } else {
                    this.proxy.ToggleVisibleRemote();
                }
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
    );
} else {
    OnboardIndicator = new Lang.Class({
        Name: 'OnboardIndicator',
        Extends: PanelMenu.Button,

        _init: function() {
            this.parent(0.0, _('Onboard'));

            this._last_event_time = 0;

            this._hbox = new St.BoxLayout({ style_class: 'panel-status-menu-box' });
            this._hbox.add_child(new St.Icon({icon_name: 'onboard-symbolic',
                                            style_class: 'system-status-icon',
                                            }));
            this.actor.add_child(this._hbox);

            this.menu.addAction(_('Preferences'), function(event) {
                GLib.spawn_command_line_async('onboard-settings', null);
            });

            this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

            this.menu.addAction(_('Help'), function(event) {
                GLib.spawn_command_line_async('/usr/bin/yelp help:onboard', null);
            });
        },

        _onEvent: function(actor, event) {
            if (event.type() == Clutter.EventType.TOUCH_BEGIN ||
                event.type() == Clutter.EventType.BUTTON_PRESS &&
                event.get_button() == 1)
            {
                // TOUCH_BEGIN and BUTTON_PRESS may come together.
                // Act only on the first one.
                if (event.get_time() - this._last_event_time > 500) {
                    _onboard.launch(); // make sure it's running
                    _onboard.ToggleVisible();
                    this._last_event_time = event.get_time();
                }
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


    Onboard = new Lang.Class({
        Name: 'Onboard',

        _init: function() {
            // Call initProxy once with a slight delay to avoid startup conflicts
            GLib.timeout_add(GLib.PRIORITY_DEFAULT, 500, () => {
                this.initProxy(0);
                return false; // Ensures timeout only runs once
            });
            this._oldKeyboardShow = null;
            this._oldKeyboardHide = null;
        },

        initProxy(retries = 0) {
            let maxRetries = 5;
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
        
            try {
                this.proxy = new OnboardProxy(Gio.DBus.session,
                    'org.onboard.Onboard',
                    '/org/onboard/Onboard/Keyboard');
                this.enable();
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
        },        

        enable: function() {
            // Start Onboard to overcome --not-show-in=GNOME
            // in onboard-autostart.desktop.
            this.launch();

            function KeyboardShow(outer_this) {
                return (function(monitor) {
                    if (!this._keyboardRequested)
                        return;

                    Main.layoutManager.keyboardIndex = monitor;

                    // In the normal desktop?
                    if (Main.actionMode == Shell.ActionMode.NORMAL)
                    {
                        // Keep built-in keyboard hidden
                        this._hideSubkeys();
                        Main.layoutManager.hideKeyboard();
                        this._keyboardVisible = true;
                    }
                    // In overview or modal (password) dialog
                    else
                    {
                        // hide Onboard
                        outer_this.Hide();

                        // Show built-in keyboard
                        this._redraw();
                        Main.layoutManager.showKeyboard();
                    }
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
        },

        disable: function() {
            Keyboard.prototype['_show'] = this._oldKeyboardShow;
            Keyboard.prototype['_hide'] = this._oldKeyboardHide;

            // Kill Onboard
            GLib.spawn_command_line_async('killall onboard', null);
        },

        // Show on user request - either Onboard or the built-in keyboard.
        ShowAnyKeyboard: function() {
            // Show built-in keyboard where appropriate. Won't show Onboard
            // because it uses its own auto-show.
            Main.keyboard._keyboardRequested = true;
            Main.keyboard._keyboardVisible = false;
            Main.keyboard.Show(global.get_current_time());

            // Show Onboard
            if (Main.actionMode == Shell.ActionMode.NORMAL)
            {
                this.Show();
            }
        },

        launch: function() {
            if (!this.proxy.g_name_owner)  // not yet running?
                GLib.spawn_command_line_async('onboard', null);
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
}
function enable_show_gesture(enable) {
    if (enable)
    {
        if (_gesture == null)
        {
            _gesture = new EdgeDragAction.EdgeDragAction(
                    St.Side.BOTTOM, Shell.ActionMode.NORMAL);
            _gesture.connect('activated', Lang.bind(this, function() {
                _onboard.ShowAnyKeyboard();
            }));
            global.stage.add_action(_gesture);
        }
    }
    else
    {
        if (_gesture != null)
        {
            global.stage.remove_action(_gesture);
            _gesture = null;
        }
    }
}

function update_show_gesture(dummy) {
    let enable = Schema.get_boolean('enable-show-gesture');
    enable_show_gesture(enable);
}

function init() {
    Convenience.initTranslations();
    Schema = Convenience.getSettings();
}

function enable() {
    // Update schema-version
    let schema_version = Schema.get_string('schema-version');
    if (!schema_version) {
        Schema.set_string('schema-version', '1.0');

        // enable auto-show on first start
        let auto_show = new Gio.Settings({schema_id: 'org.onboard.auto-show'});
        if (auto_show)
            auto_show.set_boolean('enabled', true);
    }

    _onboard = new Onboard();

    Main.onboard = _onboard;   // debug
    _onboard.Schema = Schema;

    _indicator = new OnboardIndicator();
    Main.panel.addToStatusArea('onboard-menu', _indicator);

    update_show_gesture();

    Schema.connect('changed::enable-show-gesture', update_show_gesture);
}

function disable() {
    //Schema.disconnect(enable_show_gesture);
    enable_show_gesture(false);
    _onboard.disable();
    _onboard = null;
    _indicator.destroy();
     Schema.run_dispose();
}

