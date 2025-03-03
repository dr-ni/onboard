const { GObject, Gtk, Gio } = imports.gi;
const Gettext = imports.gettext.domain('onboard');
const _ = Gettext.gettext;

const this_extension = imports.misc.extensionUtils.getCurrentExtension();
const Convenience = this_extension.imports.convenience;

let Schema;

// Check if `GObject.registerClass` exists (GNOME 3.32+)
const USE_GOBJECT = typeof GObject.registerClass !== 'undefined';

var OnboardIndicatorWidget;

if (USE_GOBJECT) {
    // GNOME 3.32+ (GTK 4)
    OnboardIndicatorWidget = GObject.registerClass(
        class OnboardIndicatorWidget extends Gtk.Grid {
            _init(params) {
                super._init(params);
                this.margin = 24;
                this.row_spacing = 6;
                this.orientation = Gtk.Orientation.VERTICAL;

                let check = new Gtk.CheckButton({
                    label: _('Drag from bottom edge of the screen to show the keyboard'),
                    margin_top: 1
                });

                Schema.bind('enable-show-gesture', check, 'active',
                    Gio.SettingsBindFlags.DEFAULT);

                this.attach(check, 0, 0, 1, 1); // Use `attach()` instead of `add()`
            }
        }
    );

} else {
    // GNOME 3.16 - 3.30 (GTK 3)
    OnboardIndicatorWidget = new GObject.Class({
        Name: 'OnboardIndicatorWidget',
        GTypeName: 'OnboardIndicatorWidget',
        Extends: Gtk.Grid,

        _init: function(params) {
            this.parent(params);
            this.margin = 24;
            this.row_spacing = 6;
            this.orientation = Gtk.Orientation.VERTICAL;

            let check = new Gtk.CheckButton({
                label: _('Drag from bottom edge of the screen to show the keyboard'),
                margin_top: 1
            });

            Schema.bind('enable-show-gesture', check, 'active',
                Gio.SettingsBindFlags.DEFAULT);

            this.attach(check, 0, 0, 1, 1); // `attach()` is better for GTK3+GTK4
        }
    });
}

function init() {
    Convenience.initTranslations();
    Schema = Convenience.getSettings();
}

function buildPrefsWidget() {
    let widget = new OnboardIndicatorWidget();
    widget.set_visible(true); // `show_all()` is removed in GTK4
    return widget;
}
