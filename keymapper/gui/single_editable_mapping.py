#!/usr/bin/python3
# -*- coding: utf-8 -*-
# key-mapper - GUI for device specific keyboard mappings
# Copyright (C) 2021 sezanzeb <proxima@sezanzeb.de>
#
# This file is part of key-mapper.
#
# key-mapper is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# key-mapper is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with key-mapper.  If not, see <https://www.gnu.org/licenses/>.


"""The basic editor with one row per mapping."""


from gi.repository import Gtk, GLib, Gdk

from keymapper.system_mapping import system_mapping
from keymapper.gui.custom_mapping import custom_mapping
from keymapper.key import Key
from keymapper.gui.reader import reader


store = Gtk.ListStore(str)


def populate_store():
    """Fill the dropdown for key suggestions with values."""
    for name in system_mapping.list_names():
        store.append([name])

    extra = [
        "mouse(up, 1)",
        "mouse(down, 1)",
        "mouse(left, 1)",
        "mouse(right, 1)",
        "wheel(up, 1)",
        "wheel(down, 1)",
        "wheel(left, 1)",
        "wheel(right, 1)",
    ]

    for key in extra:
        # add some more keys to the dropdown list
        store.append([key])


populate_store()


class SingleEditableMapping:
    """A base class for editing a single mapping,

    Manages a text input to show the configured output, a ToggleButton to activate key
    recording and a delete button. After finishing recording keys, it will
    automatically focus the text input.
    """

    """To be overwritten by inheriting class"""

    def get_key(self):
        """Get the Key object, or None if no code is mapped on this row."""
        raise NotImplementedError

    def get_symbol(self):
        """Get the assigned symbol from the text input."""
        raise NotImplementedError

    def display_key(self, key):
        """Show what the user is currently pressing in ther user interface."""
        raise NotImplementedError

    def get_recording_toggle(self):
        """Return the Gtk.ToggleButton that indicates if keys are being recorded."""
        raise NotImplementedError

    """Connect your widget events to those functions"""

    def on_text_input_change(self, *_):
        """When the output symbol for that keycode is typed in."""
        key = self.get_key()
        symbol = self.get_symbol()
        if symbol is not None and key is not None:
            custom_mapping.change(new_key=key, symbol=symbol, previous_key=None)

    def on_text_input_unfocus(self, *_):
        """Save the preset and correct the input casing."""
        symbol = self.get_symbol() or ""
        correct_case = system_mapping.correct_case(symbol)
        if symbol != correct_case:
            self.text_input.set_text(correct_case)
        self.user_interface.save_preset()

    def on_delete_button_clicked(self, *_):
        """Destroy the row and remove it from the config."""
        key = self.get_key()
        if key is not None:
            custom_mapping.clear(key)

        self.text_input.set_text("")

        self.delete_callback(self)

    """Base functionality"""

    def __init__(self, delete_callback, user_interface):
        """Construct an editable mapping."""
        self.device = user_interface.group
        self.user_interface = user_interface

        # TODO use glib events instead of parameter:
        self.delete_callback = delete_callback

        self.text_input = None

        # keys were not pressed yet
        self.input_has_arrived = False

        # Do this after the constructor of inheriting classes has finished.
        # TODO this is stupid
        GLib.idle_add(self.connect_events)

    def connect_events(self):
        # the click event to activate recording should not be recorded
        toggle = self.get_recording_toggle()
        toggle.connect("focus-in-event", lambda *_: reader.clear())
        toggle.connect("focus-out-event", lambda *_: toggle.set_active(False))

    def is_waiting_for_input(self):
        """Check if the user is interacting with the ToggleButton for key recording."""
        return self.get_recording_toggle().is_focus()

    def consume_newest_keycode(self, key):
        """To capture events from keyboards, mice and gamepads.

        Parameters
        ----------
        key : Key or None
            If None will unfocus the input widget
            # TODO wtf? switch_focus_if_complete uses self.get_key, but
               set_key is called after it
        """
        self.switch_focus_if_complete()

        if key is None:
            return

        if not self.is_waiting_for_input():
            return

        self.set_key(key)

    def switch_focus_if_complete(self):
        """If keys are released, it will switch to the text_input.

        States:
        1. not doing anything, waiting for the user to start using it
        2. user focuses it, no keys pressed
        3. user presses keys
        4. user releases keys. no keys are pressed, just like in step 2, but this time
        the focus needs to switch.
        """
        if not self.is_waiting_for_input():
            self.reset()
            return

        all_keys_released = reader.get_unreleased_keys() is None
        if all_keys_released and self.input_has_arrived and self.get_key():
            # A key was pressed and then released.
            # Switch to the symbol. idle_add this so that the
            # keycode event won't write into the symbol input as well.
            window = self.user_interface.window
            GLib.idle_add(lambda: window.set_focus(self.text_input))

        if not all_keys_released:
            # currently the user is using the widget, and certain keys have already
            # reached it.
            self.input_has_arrived = True
            return

        self.reset()

    def set_key(self, new_key):
        """Check if a keycode has been pressed and if so, display it.

        Parameters
        ----------
        new_key : Key or None
        """
        if new_key is not None and not isinstance(new_key, Key):
            raise TypeError("Expected new_key to be a Key object")

        # the newest_keycode is populated since the ui regularly polls it
        # in order to display it in the status bar.
        previous_key = self.get_key()

        # no input
        if new_key is None:
            return

        # it might end up being a key combination, wait for more
        self.input_has_arrived = True

        # keycode didn't change, do nothing
        if new_key == previous_key:
            return

        self.display_key(new_key)

        symbol = self.get_symbol()

        # the symbol is empty and therefore the mapping is not complete
        if symbol is None:
            return

        # else, the keycode has changed, the symbol is set, all good
        custom_mapping.change(new_key=new_key, symbol=symbol, previous_key=previous_key)

    def match(self, _, key, tree_iter):
        """Search the avilable names."""
        value = store.get_value(tree_iter, 0)
        return key in value.lower()

    def reset(self, *_):
        self.input_has_arrived = False
