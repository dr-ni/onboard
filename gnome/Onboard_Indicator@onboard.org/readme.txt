# Onboard Indicator Extension — Installation & Debugging

Below are the steps and commands you can use to debug the Onboard Indicator extension in a nested GNOME Shell environment:

1. **Copy changed files to the Onboard gnome shell directory**  
   ```bash
   sudo cp extension.js /usr/share/gnome-shell/extensions/Onboard_Indicator@onboard.org/extension.js
   ```
   - **Note:** You need to install the Onboard debs, usb build_debs.sh and apt_install_debs.sh 

2. **Start a new D-Bus session**  
   ```bash
   dbus-run-session bash
   ```
   - Runs a `bash` shell in a fresh D-Bus session, isolating changes from your main session.

3. **Launch Onboard manually**  
   ```bash
   onboard &
   ```
   - Starts the Onboard in the D-Bus session

4. **Run GNOME Shell in a nested Wayland session**  
   ```bash
   env MUTTER_DEBUG_DUMMY_MODE_SPECS=1248x1024 gnome-shell --nested --wayland
   ```
   - Sets up a dummy resolution (e.g., `1248x1024`).  
   - Launches GNOME Shell nested in its own window using Wayland.

5. **Filter GNOME Shell logs to check Onboard events**  
   ```bash
   env MUTTER_DEBUG_DUMMY_MODE_SPECS=1248x1024 gnome-shell --nested --wayland ... 2>&1 | grep onboard
   ```
   - Pipes GNOME Shell’s output to `grep onboard`.  
   - Useful for isolating log lines related to Onboard or the extension.

