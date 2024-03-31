#!/usr/bin/env python3
# -*- coding: utf8 -*-
# MIT License
#
# Copyright (c) 2024 Ravener
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import sys
from pathlib import Path

import gi

from card_reader import (
    BLOCK_SIZE,
    FIRST,
    get_title,
    parse_header,
    read_block,
    verify_file,
)

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GObject, Gtk

MENU_XML = """
<?xml version="1.0" encoding="UTF-8"?>
<interface>
  <menu id="app-menu">
    <section>
      <item>
        <attribute name="action">app.about</attribute>
        <attribute name="label" translatable="yes">_About</attribute>
      </item>
      <item>
        <attribute name="action">app.quit</attribute>
        <attribute name="label" translatable="yes">_Quit</attribute>
        <attribute name="accel">&lt;Primary&gt;Q</attribute>
    </item>
    </section>
  </menu>
</interface>
"""


class CardEntry(GObject.GObject):
    def __init__(self, file_name, size, blocks, title):
        super().__init__()

        self.file_name = file_name
        self.size = size
        self.blocks = blocks
        self.title = title


def bind_name(factory, item):
    file_name = item.get_item().file_name
    region = ""

    if file_name.startswith("BI"):
        region = "🇯🇵 "
    elif file_name.startswith("BE"):
        region = "🇪🇺 "
    elif file_name.startswith("BA"):
        region = "🇺🇸 "

    label = Gtk.Label.new(region + file_name)
    label.set_halign(Gtk.Align.START)
    item.set_child(label)


def bind_size(factory, item):
    label = Gtk.Label.new(str(int(item.get_item().size)) + " KB")
    # label.set_hexpand(True)
    label.set_halign(Gtk.Align.START)
    item.set_child(label)


def bind_title(factory, item):
    label = Gtk.Label.new(item.get_item().title)
    # label.set_hexpand(True)
    label.set_halign(Gtk.Align.START)
    item.set_child(label)


def bind_blocks(factory, item):
    label = Gtk.Label.new(str(item.get_item().blocks))
    # label.set_hexpand(True)
    label.set_halign(Gtk.Align.START)
    item.set_child(label)


class PSXWindow(Adw.ApplicationWindow):
    def __init__(self, application):
        super().__init__(application=application)

        self.set_default_size(800, 500)
        self.set_title("PSX Card Reader")

        self.vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(self.vbox)
        self.headerbar = Adw.HeaderBar()
        self.titlebar = Adw.WindowTitle(
            title="PSX Card Reader", subtitle="No File Open"
        )
        self.headerbar.set_title_widget(self.titlebar)
        self.vbox.append(self.headerbar)

        # Menu Button
        self.menu_button = Gtk.MenuButton()
        self.menu_button.set_icon_name("open-menu-symbolic")
        menu_model = Gtk.Builder.new_from_string(MENU_XML, -1).get_object("app-menu")
        self.menu_button.set_menu_model(menu_model)
        self.headerbar.pack_end(self.menu_button)

        # Open Button
        button_content = Adw.ButtonContent(
            icon_name="document-open-symbolic", label="Open"
        )
        self.open_button = Gtk.Button(child=button_content)
        self.open_button.add_css_class("raised")
        self.open_button.connect("clicked", self.on_open)
        self.headerbar.pack_start(self.open_button)

        # Placeholder page
        suggest_open_button = Gtk.Button(label="Open")
        suggest_open_button.add_css_class("suggested-action")
        suggest_open_button.add_css_class("pill")
        suggest_open_button.connect("clicked", self.on_open)
        clamp = Adw.Clamp(child=suggest_open_button, maximum_size=30)
        self.status_page = Adw.StatusPage(
            title="Open a File",
            description="No files opened, open a memory card file to get started.",
            icon_name="media-memory-sd-symbolic",
            child=clamp,
        )
        self.status_page.set_vexpand(True)
        # Main content container, this will hold the status at startup and allow us to easily
        # swap it with real content later.
        self.bin = Gtk.ScrolledWindow()
        self.bin.set_child(self.status_page)
        self.vbox.append(self.bin)

    def on_open(self, widget):
        self.file_chooser = Gtk.FileChooserNative.new(
            "Open File",
            self,
            Gtk.FileChooserAction.OPEN,
        )
        file_filter = Gtk.FileFilter.new()
        file_filter.set_name("Raw Memory Card Files (*.mcd)")
        file_filter.add_suffix("mcd")
        self.file_chooser.add_filter(file_filter)
        self.file_chooser.connect("response", self.on_file)
        self.file_chooser.show()

    def display_card(self, data):
        directories = parse_header(read_block(data, 0))
        selection = Gtk.SingleSelection()
        store = Gio.ListStore.new(CardEntry)
        selection.set_model(store)

        total_size = 8 * 1024

        for i, directory in enumerate(directories):
            if directory.state == FIRST:
                name = directory.file_name
                size = directory.file_size / 1024
                blocks = directory.file_size // BLOCK_SIZE
                title = get_title(data, i)

                total_size += directory.file_size
                store.append(CardEntry(name, size, blocks, title))

        column_view = Gtk.ColumnView()
        column_view.set_vexpand(True)

        def create_column(name, callback):
            factory = Gtk.SignalListItemFactory()
            factory.connect("bind", callback)

            column = Gtk.ColumnViewColumn.new(name, factory)
            column.set_expand(True)
            column_view.append_column(column)

        create_column("File Name", bind_name)
        create_column("Size", bind_size)
        create_column("Blocks", bind_blocks)
        create_column("Title", bind_title)

        column_view.set_model(selection)
        self.bin.set_child(column_view)

    def on_file(self, widget, response):
        if response == Gtk.ResponseType.ACCEPT:
            file = self.file_chooser.get_file()
            print(f"got file {file.get_basename()}")

            # TODO: Find out how to do this via GFile
            data = Path(file.get_path()).read_bytes()

            # Verify if the card is good.
            if not verify_file(data):
                dialog = Adw.MessageDialog.new(
                    self,
                    "Invalid Memory Card",
                    "File is not a correct memory card or was corrupted",
                )
                dialog.add_response("ok", "Okay")
                dialog.show()
            else:
                # Update titlebar to reflect the current open file.
                self.titlebar.set_subtitle(file.get_basename())
                self.display_card(data)


class PSXCardReader(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="io.github.ravener.psx-card-reader",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )

        # Application Actions
        self.create_action("about", self.on_about)
        self.create_action("quit", self.on_quit, ["<primary>q"])

    def do_activate(self) -> None:
        active_window = self.props.active_window
        if active_window:
            active_window.present()
        else:
            self.win = PSXWindow(application=self)
            self.win.present()

    def create_action(self, name, callback, shortcuts=None):
        """Add an application action.

        Args:
            name: the name of the action
            callback: the function to be called when the action is
              activated
            shortcuts: an optional list of accelerators
        """
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        if shortcuts:
            self.set_accels_for_action(f"app.{name}", shortcuts)

    def on_about(self, widget, _):
        about = Adw.AboutWindow(
            transient_for=self.props.active_window,
            application_name="PSX Card Reader",
            application_icon="media-memory-sd-symbolic",
            developer_name="Ravener",
            version="1.0.0",
            developers=["Ravener"],
            copyright="© 2023 Ravener",
            issue_url="https://github.com/ravener/psx-card-reader/issues",
            website="https://github.com/ravener/psx-card-reader",
        )

        about.present()

    def on_quit(self, widget, _):
        self.quit()


if __name__ == "__main__":
    app = PSXCardReader()
    app.run(sys.argv)
