 /*
 * Copyright © 2016 marmuta <marmvta@gmail.com> 
 * Copyright © 2025 Lukas Gottschall - new gnome shell
 * DBus proxy and default keyboard hiding based on ideas by Simon Schumann.
 * https://github.com/schuhumi/gnome-shell-extension-onboard-integration
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
// prefs.js – modernes ES-Modul für GNOME Shell Preferences

import Gio from 'gi://Gio';
import Adw from 'gi://Adw';

import {
    ExtensionPreferences,
    gettext as _
} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

export default class OnboardIndicatorPrefs extends ExtensionPreferences {

    fillPreferencesWindow(window) {
        const page = new Adw.PreferencesPage({
            title: _('Onboard Indicator Settings'),
            icon_name: 'dialog-information-symbolic',
        });
        window.add(page);

        const group = new Adw.PreferencesGroup({
            title: _('Behavior'),
        });
        page.add(group);

        const gestureRow = new Adw.SwitchRow({
            title: _('Drag from bottom edge to show keyboard'),
            subtitle: _('Enable show gesture for Onboard'),
        });
        group.add(gestureRow);
        const settings = this.getSettings('org.gnome.shell.extensions.onboard-indicator');
        settings.bind('enable-show-gesture', gestureRow, 'active', Gio.SettingsBindFlags.DEFAULT);
    }
}
