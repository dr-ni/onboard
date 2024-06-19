
# D-Bus Service:
Once running, Onboard provides a D-Bus service at the bus name
'org.onboard.Onboard', that allows other processes to control 
the keyboard window.

## Interface 'org.onboard.Onboard.Keyboard':

### Show(), method:
- Show the keyboard window
- Return value: None

If auto-show is enabled, the window is locked visible, i.e.
auto-hiding is suspended until Onboard is hidden either manually
or by calling the D-Bus method "Hide". This is the same bahavior as if
Onboard was shown by user action, e.g. by status menu, floating icon
or by starting a second instance.

Example:

    dbus-send --type=method_call --print-reply --dest=org.onboard.Onboard /org/onboard/Onboard/Keyboard org.onboard.Onboard.Keyboard.Show

### Hide(), method
- Hide the keyboard window
- Return value: None

Example:

    dbus-send --type=method_call --print-reply --dest=org.onboard.Onboard /org/onboard/Onboard/Keyboard org.onboard.Onboard.Keyboard.Hide

### ToggleVisible(), method
- Show the keyboard window if it was hidden, else hide it.
- Return value: None

Example:

    dbus-send --type=method_call --print-reply --dest=org.onboard.Onboard /org/onboard/Onboard/Keyboard org.onboard.Onboard.Keyboard.ToggleVisible

### Visible, Boolean property, read-only
- True if the window is currently visible, False otherwise.
- Signal: org.freedesktop.DBus.Properties.PropertiesChanged

Example:

    dbus-send --type=method_call --print-reply --dest=org.onboard.Onboard /org/onboard/Onboard/Keyboard org.freedesktop.DBus.Properties.Get string:"org.onboard.Onboard.Keyboard" string:"Visible"

### AutoShowPaused, Boolean property, read-write
- True pauses auto-show and hides the keyboard.
- False resumes auto-show.

You are free to write to this property, e.g. when entering/leaving 
tablet mode of a convertible device (and Onboard's built-in detection
isn't sufficient).
This property is not persistent. It will be reset to 'false' each time
Onboard is restarted.

### Signal: org.freedesktop.DBus.Properties.PropertiesChanged

Example, reading:

    dbus-send --type=method_call --print-reply --dest=org.onboard.Onboard /org/onboard/Onboard/Keyboard org.freedesktop.DBus.Properties.Get string:"org.onboard.Onboard.Keyboard" string:"AutoShowPaused"

Example, writing:

    dbus-send --type=method_call --print-reply --dest=org.onboard.Onboard /org/onboard/Onboard/Keyboard org.freedesktop.DBus.Properties.Set string:"org.onboard.Onboard.Keyboard" string:"AutoShowPaused" variant:boolean:"true"

