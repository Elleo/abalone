#!/usr/bin/env python3
import os.path
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from xdg import XDG_DATA_HOME


class Trainer:

    def __init__(self):
        self.builder = Gtk.Builder()
        self.builder.add_from_file("trainer.glade")
        self.builder.connect_signals(self)
        self.data_dir = os.path.join(XDG_DATA_HOME, "abalone")

        self.window = self.builder.get_object("trainer")
        self.window.show_all()

    def on_trainer_close(self, *args):
        Gtk.main_quit()

    def on_trainer_apply(self, *args):
        print(args)

    def on_trainer_prepare(self, assistant, page):        
        print(page)

if __name__ == "__main__":
    trainer = Trainer()	
    Gtk.main()
