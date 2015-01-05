#!/usr/bin/python3

# Copyright © 2014, marmuta <marmvta@gmail.com>
#
# This file is part of Onboard.
#
# Onboard is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# Onboard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import os
import sys
import time
import tempfile
import subprocess
import unittest
from contextlib import contextmanager, ExitStack

import dbus
from dbus.mainloop.glib import DBusGMainLoop

from gi.repository import GLib

from Onboard.utils import Rect
from Onboard.LanguageSupport import LanguageDB
from Onboard.definitions import Handle


DBUS_NAME  = "org.onboard.Onboard"


class _TestGUIBase(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory(prefix="test_onboard_")
        self._dir = self._tmp_dir.name
        self._user_dir = os.path.join(self._dir, "onboard")
        self._model_dir = os.path.join(self._user_dir, "models")

        # setup a fresh dconf database
        self._dconf_db_name = "_onboard_test_db"
        self._dconf_db_fn = os.path.join(self.get_config_home(),
                                         "dconf", self._dconf_db_name)
        self._dconf_profile_fn = os.path.join(self._dir, "dconf_profile")
        self._write_file(self._dconf_profile_fn,
                         ["user-db:" + self._dconf_db_name])
        self._dconf_reset() # clear everything

        self._bus = dbus.SessionBus(mainloop=DBusGMainLoop())

    def tearDown(self):
        os.remove(self._dconf_db_fn)
        self._tmp_dir.cleanup()

    def assertRectInRange(self, r_result, r_expect, tolerance=0):
        for attr in Rect.attributes:
            with self.subTest(attribute=attr):
                expected = getattr(r_expect, attr)
                result =   getattr(r_result, attr)
                self.assertInRange(result,
                                   expected-tolerance,
                                   expected+tolerance,
                                   "Rect."+attr)

    def assertInRange(self, value, begin, end, variable):
        self.assertTrue(begin <= value <= end,
                    "{}={} not in range {}..{}" \
                    .format(variable, value, begin, end))

    def _key_center(self, rwin, key_id):
        frame = 5
        h_key = (rwin.h - 2*frame) / 5
        w_key = h_key
        if key_id == "move":
            x = rwin.x + rwin.w - w_key/2
            y = rwin.y + frame + 1.5*h_key

        return int(x), int(y)

    def _get_window_rect(self):
        return Rect(
            self._gsettings_get("org.onboard.window.landscape", "x"),
            self._gsettings_get("org.onboard.window.landscape", "y"),
            self._gsettings_get("org.onboard.window.landscape", "width"),
            self._gsettings_get("org.onboard.window.landscape", "height"))

    def _set_window_rect(self, r):
        self._gsettings_set("org.onboard.window.landscape", "x", r.x)
        self._gsettings_set("org.onboard.window.landscape", "y", r.y)
        self._gsettings_set("org.onboard.window.landscape", "width", r.w)
        self._gsettings_set("org.onboard.window.landscape", "height", r.h)

    def _get_icon_palette_rect(self):
        return Rect(
            self._gsettings_get("org.onboard.icon-palette.landscape", "x"),
            self._gsettings_get("org.onboard.icon-palette.landscape", "y"),
            self._gsettings_get("org.onboard.icon-palette.landscape", "width"),
            self._gsettings_get("org.onboard.icon-palette.landscape", "height"))

    def _set_icon_palette_rect(self, r):
        self._gsettings_set("org.onboard.icon-palette.landscape", "x", r.x)
        self._gsettings_set("org.onboard.icon-palette.landscape", "y", r.y)
        self._gsettings_set("org.onboard.icon-palette.landscape", "width", r.w)
        self._gsettings_set("org.onboard.icon-palette.landscape", "height", r.h)

    def _mousemove(self, x0, y0, x1, y1, step=5):
        xd = x1 - x0
        yd = y1 - y0
        n = int(max(abs(xd), abs(yd)) / step)
        for i in range(n):
            x = x0 + xd * i / (n-1)
            y = y0 + yd * i / (n-1)
            self._xte("mousemove", int(x), int(y))
            #time.sleep(0.1)

        # The last motion event seems to be only sent for the core
        # pointer device. -> Trigger a redundant motion event with the last
        # position to make sure there is an event coming from the XTest
        # slave device too. Else handles won't move all the way in the
        # move/resize tests.
        self._xte("mousemove", int(x1), int(y1))

    @contextmanager
    def _run_onboard(self, env={}, catch_output=False):
        with self._run_onboard_script("./onboard", env, catch_output) as p:
            self._wait_name_owner_changed(self._bus, DBUS_NAME)
            time.sleep(1)
            yield p
            p.terminate()

    @contextmanager
    def _run_onboard_settings(self, env={}, catch_output=False, delay=2.0):
        with self._run_onboard_script("./onboard-settings", env, catch_output) as p:
            time.sleep(delay)
            yield p
            p.terminate()
            #self._xte("key", "Escape")

    @contextmanager
    def _run_onboard_script(self, command, _env={}, catch_output=False):
        try:
            env = dict(os.environ)
            env["DCONF_PROFILE"] = self._dconf_profile_fn
            env["XDG_DATA_HOME"] = self._dir
            env["LANG"] = "en_US.UTF-8"
            env.update(_env)

            p = subprocess.Popen([command], env=env,
                                 stdout=subprocess.PIPE \
                                    if catch_output else None,
                                 stderr=subprocess.STDOUT \
                                    if catch_output else None,
                                 close_fds=True,
                                 )
            yield p

        finally:
            if catch_output:
                outs = p.stdout.read()

                # filter out annoying Gtk deprecation warnings we cannot remove yet
                blacklist = ["is deprecated and shouldn't be used anymore",
                            "builder.add_from_file",
                            "GtkDialog mapped without a transient parent",
                            ]
                for line in outs.decode("UTF-8").split("\n"):
                    if line and \
                    not any(s in line for s in blacklist):
                        print("outs:", line, file=sys.stderr)

    def _gsettings_set(self, schema, key, value):
        env = dict(os.environ)
        env["DCONF_PROFILE"] = self._dconf_profile_fn
        env["LANG"] = "en_US.UTF-8"

        if value is True:
            valstr = "true"
        elif value is False:
            valstr = "false"
        else:
            valstr = str(value)

        p = subprocess.Popen(["gsettings", "set",
                                schema, key, valstr], env=env)
        p.wait()

    def _gsettings_get(self, schema, key):
        env = dict(os.environ)
        env["DCONF_PROFILE"] = self._dconf_profile_fn
        env["LANG"] = "en_US.UTF-8"

        valstr = subprocess.check_output(["gsettings", "get",
                                         schema, key], env=env)
        valstr = valstr.decode("UTF-8").replace("\n", "")
        if valstr == "true":
            value = True
        elif valstr == "false":
            valstr = False
        else:
            try:
                value = int(valstr)
            except ValueError:
                try:
                    value = float(valstr)
                except ValueError:
                    value = valstr
        return value

    def _dconf_reset(self):
        env = dict(os.environ)
        env["DCONF_PROFILE"] = self._dconf_profile_fn
        env["LANG"] = "en_US.UTF-8"
        subprocess.check_call(["dconf", "reset", "-f","/"], env=env)

    def _xte(self, *params):
        env = dict(os.environ)
        env["LANG"] = "en_US.UTF-8"
        command = ["xte", " ".join(str(p) for p in params)]
        #print(command, file=sys.stderr)
        subprocess.check_call(command, env=env)

    @staticmethod
    def _wait_name_owner_changed(bus, name):

        def on_name_owner_changed(name, old, new):
            if not old:
                loop.quit()

        bus.add_signal_receiver(on_name_owner_changed,
                                "NameOwnerChanged",
                                dbus.BUS_DAEMON_IFACE,
                                arg0 = name)
        loop = GLib.MainLoop()
        loop.run()

    @staticmethod
    def get_config_home(file = None):
        """
        User specific config directory.
        """
        path = os.environ.get("XDG_CONFIG_HOME")
        if path and not os.path.isabs(path):
            path = None

        if not path:
            path = os.path.join(os.path.expanduser("~"), ".config")

        if file:
            path = os.path.join(path, file)

        return path

    @staticmethod
    def _write_file(fn, lines):
        with open(fn, mode="w", encoding="UTF-8") as f:
            for l in lines:
                f.write(l)

    @staticmethod
    def _touch(fn, size):
        with open(fn, mode="w") as f:
            if size:
                f.write("*"*size)


class TestWindowHandling(_TestGUIBase):

    def test_keyboard_moving_remembered_after_restart(self):
        r = self._get_window_rect()
        dx = 100
        dy = 200
        with self._run_onboard() as p:
            x, y = self._key_center(r, "move")
            self._xte("mousemove", x, y)
            self._xte("mousedown", 1)
            time.sleep(0.5)
            self._mousemove(x, y, x+dx, y+dy)
            time.sleep(0.5)
            self._xte("mouseup", 1)
            time.sleep(0.5)

        k = 20 # ignore a few lost pixels due to drag threshold and xte moving
        r_expect = r.offset(dx, dy)
        r_result = self._get_window_rect()
        self.assertEqual(r_expect.get_size(), r_result.get_size())
        self.assertTrue(r_expect.x-k <= r_result.x <= r_expect.x,
                        "expected={} result={}".format(r_expect.x, r_result.x))
        self.assertTrue(r_expect.y-k <= r_result.y <= r_expect.y,
                        "expected={} result={}".format(r_expect.y, r_result.y))

        # rect must not change after next restart
        with self._run_onboard() as p:
            pass
        self.assertEqual(str(r_result), str(self._get_window_rect()))

        # rect must not change after another restart
        with self._run_onboard() as p:
            pass
        self.assertEqual(str(r_result), str(self._get_window_rect()))

    def test_keyboard_resizing_remembered_after_restart(self):
        r = self._get_window_rect()
        dx = 100
        dy = 200
        dx_handle = 5
        dy_handle = 5
        with self._run_onboard() as p:
            x, y = r.right()-dx_handle, r.bottom()-dy_handle
            self._xte("mousemove", x, y)
            self._xte("mousedown", 1)
            time.sleep(0.5)
            self._mousemove(x, y, x+dx, y+dy)
            time.sleep(0.5)
            self._xte("mouseup", 1)
            time.sleep(0.5)

        k = 20 # ignore a few lost pixels due to drag threshold and xte moving
        r_expect = r.copy()
        r_expect.w = r.w + dx
        r_expect.h = r.h + dy
        r_result = self._get_window_rect()

        self.assertEqual(r_expect.left_top(), r_result.left_top())
        self.assertTrue(r_expect.w-k <= r_result.w <= r_expect.w,
                        "expected={} result={}".format(r_expect.w, r_result.w))
        self.assertTrue(r_expect.h-k <= r_result.h <= r_expect.h,
                        "expected={} result={}".format(r_expect.h, r_result.h))

        # rect must not change after next restart
        with self._run_onboard() as p:
            pass
        self.assertEqual(str(r_result), str(self._get_window_rect()))

        # rect must not change after another restart
        with self._run_onboard() as p:
            pass
        self.assertEqual(str(r_result), str(self._get_window_rect()))


    def test_icon_palette_moving_remembered_after_restart(self):
        self._gsettings_set("org.onboard", "start-minimized", True)
        self._gsettings_set("org.onboard.icon-palette", "in-use", True)

        r = self._get_icon_palette_rect()
        dx = 100
        dy = 200
        with self._run_onboard() as p:
            x, y = (int(val) for val in r.get_center())
            self._xte("mousemove", x, y)
            self._xte("mousedown", 1)
            time.sleep(0.5)
            self._mousemove(x, y, x+dx, y+dy)
            time.sleep(0.5)
            self._xte("mouseup", 1)
            time.sleep(0.5)

        k = 10 # ignore a few lost pixels due to drag threshold and xte moving
        r_expect = r.offset(dx, dy)
        r_result = self._get_icon_palette_rect()
        self.assertEqual(r_expect.get_size(), r_result.get_size())
        self.assertTrue(r_expect.x-k <= r_result.x <= r_expect.x,
                        "expected={} result={}".format(r_expect.x, r_result.x))
        self.assertTrue(r_expect.y-k <= r_result.y <= r_expect.y,
                        "expected={} result={}".format(r_expect.y, r_result.y))

        # rect must not change after next restart
        with self._run_onboard() as p:
            pass
        self.assertEqual(str(r_result), str(self._get_icon_palette_rect()))

        # rect must not change after another restart
        with self._run_onboard() as p:
            pass
        self.assertEqual(str(r_result), str(self._get_icon_palette_rect()))

    def test_icon_palette_resizing_remembered_after_restart(self):
        self._gsettings_set("org.onboard", "start-minimized", True)
        self._gsettings_set("org.onboard.icon-palette", "in-use", True)

        r = self._get_icon_palette_rect()
        dx = 100
        dy = 200
        dx_handle = 5
        dy_handle = 5
        with self._run_onboard() as p:
            x, y = r.right()-dx_handle, r.bottom()-dy_handle
            self._xte("mousemove", x, y)
            self._xte("mousedown", 1)
            time.sleep(0.5)
            self._mousemove(x, y, x+dx, y+dy)
            time.sleep(0.5)
            self._xte("mouseup", 1)
            time.sleep(0.5)

        k = 10 # ignore a few lost pixels due to drag threshold and xte moving
        r_expect = r.copy()
        r_expect.w = r.w + dx
        r_expect.h = r.h + dy
        r_result = self._get_icon_palette_rect()

        self.assertEqual(r_expect.left_top(), r_result.left_top())
        self.assertTrue(r_expect.w-k <= r_result.w <= r_expect.w,
                        "expected={} result={}".format(r_expect.w, r_result.w))
        self.assertTrue(r_expect.h-k <= r_result.h <= r_expect.h,
                        "expected={} result={}".format(r_expect.h, r_result.h))

        # rect must not change after next restart
        with self._run_onboard() as p:
            pass
        self.assertEqual(str(r_result), str(self._get_icon_palette_rect()))

        # rect must not change after another restart
        with self._run_onboard() as p:
            pass
        self.assertEqual(str(r_result), str(self._get_icon_palette_rect()))

    def test_icon_palette_resizing(self):
        self._gsettings_set("org.onboard", "start-minimized", True)
        self._gsettings_set("org.onboard.icon-palette", "in-use", True)
        self._gsettings_set("org.onboard.icon-palette.landscape", "x", 300)
        self._gsettings_set("org.onboard.icon-palette.landscape", "y", 300)
        #self._gsettings_set("org.onboard.universal-access", "drag-threshold", 0)
        self._test_window_resizing(self._get_icon_palette_rect,
                                   self._set_icon_palette_rect)

    def test_keyboard_window_resizing(self):
        self._gsettings_set("org.onboard.window.landscape", "x", 300)
        self._gsettings_set("org.onboard.window.landscape", "y", 300)
        #self._gsettings_set("org.onboard.universal-access", "drag-threshold", 0)
        self._test_window_resizing(self._get_window_rect,
                                   self._set_window_rect)

    def _test_window_resizing(self, get_window_rect, set_window_rect):
        dx = 100
        dy = 100
        tolerance = 15  # there's some loss due to drag-threshold and others
        r_default = get_window_rect()

        with self.subTest(comment="corners1"):
            set_window_rect(r_default)

            r = get_window_rect()
            with self._run_onboard() as p:
                self._move_handle_rel(Handle.NORTH_WEST, r, dx, dy)
                self._move_handle_rel(Handle.SOUTH_EAST, r, dx, dy)

            self.assertRectInRange(get_window_rect(),
                                r.inflate(dx, dy), tolerance)

            r = get_window_rect()
            with self._run_onboard() as p:
                self._move_handle_rel(Handle.NORTH_WEST, r, -dx, -dy)
                self._move_handle_rel(Handle.SOUTH_EAST, r, -dx, -dy)

            self.assertRectInRange(get_window_rect(),
                                r.deflate(dx, dy), tolerance)

        with self.subTest(comment="corners2"):
            set_window_rect(r_default)

            r = get_window_rect()
            with self._run_onboard() as p:
                self._move_handle_rel(Handle.SOUTH_WEST, r, dx, dy)
                self._move_handle_rel(Handle.NORTH_EAST, r, dx, dy)

            self.assertRectInRange(get_window_rect(),
                                r.inflate(dx, dy), tolerance)

            r = get_window_rect()
            with self._run_onboard() as p:
                self._move_handle_rel(Handle.SOUTH_WEST, r, -dx, -dy)
                self._move_handle_rel(Handle.NORTH_EAST, r, -dx, -dy)

            self.assertRectInRange(get_window_rect(),
                                r.deflate(dx, dy), tolerance)

        with self.subTest(comment="edges"):
            set_window_rect(r_default)
            r = get_window_rect()
            with self._run_onboard() as p:
                self._move_handle_rel(Handle.NORTH, r, dx, dy)
                self._move_handle_rel(Handle.EAST, r, dx, dy)
                self._move_handle_rel(Handle.SOUTH, r, dx, dy)
                self._move_handle_rel(Handle.WEST, r, dx, dy)

            self.assertRectInRange(get_window_rect(),
                                r.inflate(dx, dy), tolerance)

            r = get_window_rect()
            with self._run_onboard() as p:
                self._move_handle_rel(Handle.NORTH, r, -dx, -dy)
                self._move_handle_rel(Handle.EAST, r, -dx, -dy)
                self._move_handle_rel(Handle.SOUTH, r, -dx, -dy)
                self._move_handle_rel(Handle.WEST, r, -dx, -dy)

            self.assertRectInRange(get_window_rect(),
                                r.deflate(dx, dy), tolerance)

    def _move_handle_rel(self, handle, r, dx, dy):
        x0, y0, x1, y1 = self._get_handle_move_vector(handle, r, dx, dy)
        self._xte("mousemove", x0, y0)
        self._xte("mousedown", 1)
        time.sleep(0.3)
        self._mousemove(x0, y0, x1, y1)
        self._xte("mouseup", 1)
        time.sleep(0.3)

    def _get_handle_move_vector(self, handle, r, dx, dy):
        handle_offset = 4
        if handle in [Handle.NORTH,
                      Handle.NORTH_WEST,
                      Handle.NORTH_EAST]:
            y0 = r.y + handle_offset
            y1 = y0 - dy
        if handle in [Handle.WEST,
                      Handle.NORTH_WEST,
                      Handle.SOUTH_WEST]:
            x0 = r.x + handle_offset
            x1 = x0 - dx
        if handle in [Handle.EAST,
                      Handle.NORTH_EAST,
                      Handle.SOUTH_EAST]:
            x0 = r.right() - handle_offset
            x1 = x0 + dx
        if handle in [Handle.SOUTH,
                      Handle.SOUTH_WEST,
                      Handle.SOUTH_EAST]:
            y0 = r.bottom() - handle_offset
            y1 = y0 + dy

        if handle in [Handle.NORTH,
                      Handle.SOUTH]:
            x0 = int(r.get_center()[0])
            x1 = x0
        if handle in [Handle.WEST,
                      Handle.EAST]:
            y0 = int(r.get_center()[1])
            y1 = y0

        return x0, y0, x1, y1


class TestMisc(_TestGUIBase):

    def test_valid_test_environment(self):
        # write to dconf database to make sure it exists
        self._gsettings_set("org.onboard", "use-system-defaults", True)
        self.assertEqual(
            self._gsettings_get("org.onboard", "use-system-defaults"),
            True)
        self.assertTrue(os.path.exists(self._dconf_db_fn))

        # database must be reset to defaults
        self.assertEqual(str(self._get_window_rect()),
                         str(Rect(100, 50, 700, 205)))

    def test_startup_with_C_locale(self):
        # turn major features on
        self._gsettings_set("org.onboard.auto-show", "enabled", True)
        self._gsettings_set("org.onboard.typing-assistance.word-suggestions", "enabled", True)
        self._gsettings_set("org.onboard.icon-palette", "in-use", True)

        # no dialog on startup
        self._gsettings_set("org.gnome.desktop.interface", "toolkit-accessibility", True)

        with self._run_onboard(env={"LANG": "C"}) as p:
            pass

        with self._run_onboard_settings(env={"LANG": "C"}, catch_output=True) as p:
            pass

    @staticmethod
    def _get_languages():
        return LanguageDB.get_main_languages()

    def test_startup_with_various_languages_onboard(self):
        # turn major features on
        self._gsettings_set("org.onboard.auto-show", "enabled", True)
        self._gsettings_set("org.onboard.typing-assistance.word-suggestions", "enabled", True)
        self._gsettings_set("org.onboard.icon-palette", "in-use", True)

        # no dialog on startup
        self._gsettings_set("org.gnome.desktop.interface", "toolkit-accessibility", True)

        languages = self._get_languages()
        for language in languages:
            with self.subTest(language=language):
                with self._run_onboard({"LANGUAGE": language}) as p:
                    pass

    def test_startup_with_various_languages_onboard_settings(self):
        # turn major features on
        self._gsettings_set("org.onboard.auto-show", "enabled", True)
        self._gsettings_set("org.onboard.typing-assistance.word-suggestions", "enabled", True)
        self._gsettings_set("org.onboard.icon-palette", "in-use", True)

        # no dialog on startup
        self._gsettings_set("org.gnome.desktop.interface", "toolkit-accessibility", True)

        languages = self._get_languages()

        # run onboard-settings for all languages
        k = 4 # max parallel languages
        for i in range(0, len(languages), k):
            langs = languages[i:i+k]
            with self.subTest(languages=langs):
                with ExitStack() as stack:
                    for language in langs:
                        stack.enter_context(
                            self._run_onboard_settings(
                                env={"LANGUAGE": language},
                                catch_output=True,
                                delay=0.5))
                    time.sleep(2)


class TestNoSetup(unittest.TestCase):

    def test_apt_cache_unmet_onboard(self):
        result = subprocess.check_output(["apt-cache", "unmet", "onboard"])
        result = result.decode("UTF-8")
        self.assertEqual(result, "")


